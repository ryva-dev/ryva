from __future__ import annotations

import json
import re
from pathlib import Path

from rich.table import Table

from ryva.utils import console, load_manifest, load_yaml

# Patterns that indicate a keyword is used in a negated / compliant context.
# {keyword} is substituted at check time; patterns are always matched case-insensitively.
_NEGATION_PATTERNS = [
    r"does not\b.{{0,30}}{keyword}",
    r"do not\b.{{0,30}}{keyword}",
    r"never\b.{{0,30}}{keyword}",
    r"\bno\b\s+{keyword}",
    r"\bnot\b.{{0,30}}{keyword}",
    r"\bwithout\b.{{0,30}}{keyword}",
    r"refus\w*.{{0,30}}{keyword}",
    r"prohibit\w*.{{0,30}}{keyword}",
    r"avoid\w*.{{0,30}}{keyword}",
    r"{keyword}\b.{{0,30}}\b(not|never|false|prohibited)",
    r"is\s+not\s+a\s+{keyword}",
]


def _is_affirmative_use(keyword: str, text: str, case_sensitive: bool = False) -> bool:
    """Return True only if keyword appears in an affirmative (non-negated) context.

    For each occurrence of the keyword, builds a 200-char context window and checks
    whether any negation pattern match *overlaps* with the current keyword span.
    This prevents a negation from one occurrence (e.g. "no diagnosis") from
    accidentally covering a separate affirmative occurrence later in the same text.
    Returns False only when every occurrence is covered by an overlapping negation.
    """
    check_kw = keyword if case_sensitive else keyword.lower()
    check_text = text if case_sensitive else text.lower()

    if check_kw not in check_text:
        return False

    kw_lower = keyword.lower()
    negation_regexes = [
        re.compile(pat.format(keyword=re.escape(kw_lower)), re.IGNORECASE)
        for pat in _NEGATION_PATTERNS
    ]

    for m in re.finditer(re.escape(check_kw), check_text):
        pos, kw_end = m.start(), m.end()
        ctx_start = max(0, pos - 100)
        ctx_end = min(len(check_text), kw_end + 100)
        context = check_text[ctx_start:ctx_end]
        rel_pos = pos - ctx_start
        rel_end = kw_end - ctx_start

        is_negated = False
        for r in negation_regexes:
            for neg_m in r.finditer(context):
                # The negation match must genuinely overlap with this keyword span
                if neg_m.start() <= rel_end and neg_m.end() >= rel_pos:
                    is_negated = True
                    break
            if is_negated:
                break

        if not is_negated:
            return True  # at least one affirmative occurrence

    return False  # every occurrence is negated


def _extract_string_values(data, depth: int = 0) -> list[str]:
    """Recursively extract string values from JSON data, skipping field names."""
    if depth > 10:
        return []
    if isinstance(data, str):
        return [data]
    if isinstance(data, dict):
        out = []
        for v in data.values():
            out.extend(_extract_string_values(v, depth + 1))
        return out
    if isinstance(data, list):
        out = []
        for item in data:
            out.extend(_extract_string_values(item, depth + 1))
        return out
    return []


def load_policies(root: Path, project: dict) -> list[dict]:
    """Load policies from project.yml and an optional policies.yml file."""
    policies = list(project.get("policies", []))
    policies_file = root / "policies.yml"
    if policies_file.exists():
        data = load_yaml(policies_file)
        policies.extend(data.get("policies", []))
    return policies


def _strip_fences(text: str) -> str:
    """Strip markdown code fences so JSON policy checks work on actual content."""
    match = re.search(r"^```(?:\w+)?\s*\n?(.*?)\n?```\s*$", text.strip(), re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def check_output(output_text: str, policies: list[dict]) -> list[dict]:
    """Check a raw output string against all policies. Returns violation dicts."""
    # Strip code fences before evaluation — prevents false positives when models
    # return valid JSON wrapped in markdown fences.
    clean_text = _strip_fences(output_text)
    violations = []
    for policy in policies:
        passed, detail = _apply_rule(policy.get("check", ""), clean_text, policy)
        if not passed:
            violations.append({
                "policy": policy.get("name", "unnamed"),
                "rule": policy.get("rule", ""),
                "severity": policy.get("severity", "error"),
                "detail": detail,
            })
    return violations


def _apply_rule(rule_type: str, text: str, policy: dict) -> tuple[bool, str]:
    if rule_type == "keyword_forbidden":
        # Support both 'keywords' (list) and 'keyword' (singular string)
        keywords = policy.get("keywords") or (
            [policy["keyword"]] if "keyword" in policy else []
        )
        case_sensitive = policy.get("case_sensitive", False)
        for kw in keywords:
            if _is_affirmative_use(kw, text, case_sensitive):
                return False, f"Forbidden keyword found: '{kw}'"
        return True, "OK"

    if rule_type == "forbidden_pattern":
        pattern = policy.get("pattern", "")
        flags = 0 if policy.get("case_sensitive", False) else re.IGNORECASE
        # When output is valid JSON, run the pattern against string values only
        # (not against field names) to avoid spurious matches on schema keys.
        clean = _strip_fences(text)
        try:
            parsed = json.loads(clean)
            check_text = " ".join(_extract_string_values(parsed))
        except (json.JSONDecodeError, TypeError):
            check_text = clean
        if re.search(pattern, check_text, flags):
            return False, f"Forbidden pattern matched: '{pattern}'"
        return True, "OK"

    if rule_type == "must_contain":
        needle = policy.get("text", "")
        case_sensitive = policy.get("case_sensitive", False)
        check_text = text if case_sensitive else text.lower()
        check_needle = needle if case_sensitive else needle.lower()
        if check_needle in check_text:
            return True, "OK"
        return False, f"Required text not found: '{needle}'"

    if rule_type == "must_contain_pattern":
        pattern = policy.get("pattern", "")
        flags = 0 if policy.get("case_sensitive", False) else re.IGNORECASE
        if re.search(pattern, text, flags):
            return True, "OK"
        return False, f"Pattern not matched: '{pattern}'"

    if rule_type == "max_length":
        max_len = policy.get("max", 10_000)
        if len(text) <= max_len:
            return True, "OK"
        return False, f"Output too long: {len(text)} chars (max {max_len})"

    if rule_type == "min_length":
        min_len = policy.get("min", 0)
        if len(text) >= min_len:
            return True, "OK"
        return False, f"Output too short: {len(text)} chars (min {min_len})"

    if rule_type == "json_field_required":
        field = policy.get("field", "")
        try:
            data = json.loads(_strip_fences(text))
            if field in data:
                return True, "OK"
            return False, f"Required JSON field missing: '{field}'"
        except json.JSONDecodeError:
            return False, "Output is not valid JSON"

    if rule_type == "json_field_forbidden":
        field = policy.get("field", "")
        forbidden_value = policy.get("value")
        try:
            data = json.loads(_strip_fences(text))
            if field not in data:
                return True, "OK"
            if forbidden_value is not None and data[field] != forbidden_value:
                return True, "OK"
            return False, f"Forbidden JSON field present: '{field}'"
        except json.JSONDecodeError:
            return True, "OK"

    return True, f"Unknown rule type '{rule_type}'"


def run_alignment_checks(root: Path, agent_name: str | None) -> bool:
    """Run alignment policy checks against agent test case outputs."""
    from ryva.runner import _resolve_prompt, _resolve_provider

    manifest = load_manifest(root)
    project = manifest.get("project", {})
    agents = manifest.get("agents", {})

    policies = load_policies(root, project)
    if not policies:
        console.print("[yellow]No policies defined.[/yellow]")
        console.print("[dim]Add a 'policies' list to project.yml or create policies.yml.[/dim]")
        return True

    targets = (
        {agent_name: agents[agent_name]}
        if agent_name and agent_name in agents
        else agents
    )

    results = []
    for name, agent in targets.items():
        tests_dir = root / "tests" / name
        if not tests_dir.exists():
            continue

        provider_name, model, provider = _resolve_provider(project, agent)

        for test_file in sorted(tests_dir.glob("*.yml")):
            data = load_yaml(test_file)
            for case in data.get("cases", []):
                case_name = case.get("name", test_file.stem)
                input_data = case.get("input", {})
                try:
                    prompt = _resolve_prompt(root, agent, input_data)
                    raw = provider.complete(prompt, model, 2048)
                    violations = check_output(raw, policies)
                    results.append((name, case_name, violations))
                except Exception as exc:
                    results.append((name, case_name, [{
                        "policy": "error",
                        "rule": "",
                        "severity": "error",
                        "detail": str(exc)[:80],
                    }]))

    if not results:
        console.print("[yellow]No test cases found to check against.[/yellow]")
        return True

    _print_results(results, policies)
    return all(
        all(v["severity"] != "error" for v in violations)
        for _, _, violations in results
    )


def _print_results(results: list, policies: list[dict]) -> None:
    table = Table(title="Alignment Check Results", header_style="bold")
    table.add_column("Agent", style="cyan")
    table.add_column("Case")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed_count = 0
    total = len(results)

    for agent, case_name, violations in results:
        errors = [v for v in violations if v["severity"] == "error"]
        warnings = [v for v in violations if v["severity"] == "warning"]

        if not violations:
            status = "[bold green]✓ PASS[/bold green]"
            detail = ""
            passed_count += 1
        elif not errors:
            status = "[bold yellow]⚠ WARN[/bold yellow]"
            detail = "; ".join(f"{v['policy']}: {v['detail']}" for v in warnings)
            passed_count += 1
        else:
            status = "[bold red]✗ FAIL[/bold red]"
            detail = "; ".join(f"{v['policy']}: {v['detail']}" for v in errors[:2])

        table.add_row(agent, case_name, status, detail[:80])

    console.print(table)
    color = "green" if passed_count == total else "red"
    console.print(f"\n[bold {color}]{passed_count}/{total} alignment checks passed[/bold {color}]")
    console.print(f"[dim]Checked against {len(policies)} policy rule(s)[/dim]")
