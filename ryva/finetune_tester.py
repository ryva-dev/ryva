from __future__ import annotations
import os
import time
from pathlib import Path
import yaml
from rich.console import Console
from rich.table import Table
from ryva.providers import get_provider

console = Console()


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
        data = yaml.safe_load(f.read_text())
        results.extend(_run_file(root, data))

    _print_results(results)
    return all(p for *_, p, _ in results)


def _run_file(root: Path, data: dict) -> list:
    base_model = data.get("base_model")
    fine_tuned_model = data.get("fine_tuned_model")
    provider_name = data.get("provider", "anthropic")
    system_prompt = data.get("system_prompt", "You are a helpful assistant.")
    cases = data.get("cases", [])

    provider = get_provider(provider_name, {
        "api_key": os.environ.get("ANTHROPIC_API_KEY", "")
    })

    results = []
    for case in cases:
        name = case.get("name", "unnamed")
        prompt = case.get("prompt", "")
        metric = case.get("metric", "length")
        threshold = case.get("improvement_threshold", 0.0)

        base_score = _score(provider, base_model, system_prompt, prompt, metric)
        ft_score = _score(provider, fine_tuned_model, system_prompt, prompt, metric)

        delta = ft_score - base_score
        passed = delta >= threshold
        detail = f"base={base_score:.3f} ft={ft_score:.3f} delta={delta:+.3f} (need {threshold:+.3f})"
        results.append((fine_tuned_model, name, metric, passed, detail))

    return results


def _score(provider, model: str, system: str, prompt: str, metric: str) -> float:
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
    else:
        return 1.0 if text.strip() else 0.0


def _print_results(results: list):
    table = Table(title="Fine-tune Evaluation Results", header_style="bold")
    table.add_column("Model", style="cyan")
    table.add_column("Test Case")
    table.add_column("Metric", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for model, case, metric, p, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        table.add_row(model, case, metric, status, detail)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} fine-tune eval tests passed[/bold {color}]")