from __future__ import annotations

import json
import re
from pathlib import Path

from rich.table import Table

from ryva.utils import console, load_manifest, load_yaml


def load_policies(root: Path, project: dict) -> list[dict]:
    """Load policies from project.yml and an optional policies.yml file."""
    policies = list(project.get("policies", []))
    policies_file = root / "policies.yml"
    if policies_file.exists():
        data = load_yaml(policies_file)
        policies.extend(data.get("policies", []))
    return policies


def check_output(output_text: str, policies: list[dict]) -> list[dict]:
    """Check a raw output string against all policies. Returns violation dicts."""
    violations = []
    for policy in policies:
        passed, detail = _apply_rule(policy.get("check", ""), output_text, policy)
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
        keywords = policy.get("keywords", [])
        case_sensitive = policy.get("case_sensitive", False)
        check_text = text if case_sensitive else text.lower()
        for kw in keywords:
            check_kw = kw if case_sensitive else kw.lower()
            if check_kw in check_text:
                return False, f"Forbidden keyword found: '{kw}'"
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
            data = json.loads(text)
            if field in data:
                return True, "OK"
            return False, f"Required JSON field missing: '{field}'"
        except json.JSONDecodeError:
            return False, "Output is not valid JSON"

    if rule_type == "json_field_forbidden":
        field = policy.get("field", "")
        forbidden_value = policy.get("value")
        try:
            data = json.loads(text)
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
