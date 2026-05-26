from __future__ import annotations

import json
import re
import time
from pathlib import Path

from rich.table import Table

from ryva.providers import get_provider
from ryva.utils import STOP_WORDS, console, load_yaml

_METRICS = (
    "length",
    "latency",
    "non_empty",
    "keyword_coverage",
    "semantic_similarity",
    "instruction_following",
    "format_compliance",
)


def run_finetune_tests(root: Path, agent_name: str | None) -> bool:
    test_dir = root / "tests" / "finetune"
    if not test_dir.exists():
        console.print("[yellow]No finetune tests found.[/yellow]")
        return True

    pattern = f"{agent_name}/**/*.yml" if agent_name else "**/*.yml"
    files = list(test_dir.glob(pattern))
    if not files:
        console.print("[yellow]No finetune test files found.[/yellow]")
        return True

    results = []
    for f in files:
        data = load_yaml(f)
        results.extend(_run_file(root, data))

    _print_results(results)
    return all(p for *_, p, _ in results)


def _run_file(root: Path, data: dict) -> list:
    import os

    base_model = data.get("base_model")
    fine_tuned_model = data.get("fine_tuned_model")
    provider_name = data.get("provider", "anthropic")
    system_prompt = data.get("system_prompt", "You are a helpful assistant.")
    cases = data.get("cases", [])

    provider = get_provider(provider_name, {
        "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),
    })

    results = []
    for case in cases:
        name = case.get("name", "unnamed")
        prompt = case.get("prompt", "")
        metric = case.get("metric", "non_empty")
        threshold = case.get("improvement_threshold", 0.0)

        base_score = _score(provider, base_model, system_prompt, prompt, metric, case)
        ft_score = _score(provider, fine_tuned_model, system_prompt, prompt, metric, case)

        delta = ft_score - base_score
        passed = delta >= threshold
        detail = (
            f"base={base_score:.3f} ft={ft_score:.3f} "
            f"delta={delta:+.3f} (need {threshold:+.3f})"
        )
        results.append((fine_tuned_model, name, metric, passed, detail))

    return results


def _score(
    provider,
    model: str,
    system: str,
    prompt: str,
    metric: str,
    case: dict,
) -> float:
    full_prompt = f"{system}\n\n{prompt}"
    start = time.time()
    try:
        text = provider.complete(full_prompt, model, 256)
        elapsed = time.time() - start
    except Exception:
        return 0.0

    if metric == "length":
        return min(len(text.split()) / 50.0, 1.0)

    elif metric == "latency":
        return max(0.0, 1.0 - (elapsed / 10.0))

    elif metric == "non_empty":
        return 1.0 if text.strip() else 0.0

    elif metric == "keyword_coverage":
        keywords = case.get("keywords", [])
        if not keywords:
            return 1.0
        text_lower = text.lower()
        found = sum(1 for k in keywords if k.lower() in text_lower)
        return found / len(keywords)

    elif metric == "semantic_similarity":
        expected = case.get("expected_output", "")
        if not expected:
            return 1.0
        answer_words = {w for w in text.lower().split() if w not in STOP_WORDS}
        expected_words = {w for w in expected.lower().split() if w not in STOP_WORDS}
        if not expected_words:
            return 1.0
        overlap = answer_words & expected_words
        precision = len(overlap) / len(answer_words) if answer_words else 0.0
        recall = len(overlap) / len(expected_words) if expected_words else 0.0
        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)

    elif metric == "instruction_following":
        must_include = case.get("must_include", [])
        must_exclude = case.get("must_exclude", [])
        text_lower = text.lower()
        checks = (
            [phrase.lower() in text_lower for phrase in must_include]
            + [phrase.lower() not in text_lower for phrase in must_exclude]
        )
        return sum(checks) / len(checks) if checks else 1.0

    elif metric == "format_compliance":
        fmt = case.get("expected_format", "")
        if fmt == "json":
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    json.loads(match.group())
                    return 1.0
                except json.JSONDecodeError:
                    pass
            return 0.0
        elif fmt == "list":
            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
            has_bullets = any(
                ln.startswith(("-", "*", "•")) or (ln[:2].rstrip(".").isdigit())
                for ln in lines
            )
            return 1.0 if has_bullets else 0.3
        return 1.0 if text.strip() else 0.0

    # Unknown metric — treat any non-empty response as passing
    return 1.0 if text.strip() else 0.0


def _print_results(results: list):
    table = Table(title="Fine-tune Evaluation Results", header_style="bold")
    table.add_column("Model", style="cyan")
    table.add_column("Test Case")
    table.add_column("Metric", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed_count = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for model, case, metric, p, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        table.add_row(model, case, metric, status, detail)

    console.print(table)
    color = "green" if passed_count == total else "red"
    console.print(f"\n[bold {color}]{passed_count}/{total} fine-tune eval tests passed[/bold {color}]")
