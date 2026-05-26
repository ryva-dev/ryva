from __future__ import annotations

import os
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ryva.providers import get_provider

console = Console()

BENCHMARKS = {
    "summarization": [
        {
            "name": "basic summarization",
            "input": "Artificial intelligence is transforming industries by automating tasks, improving decision-making, and enabling new capabilities that were previously impossible.",
            "check": lambda r: len(r.split()) < 20 and len(r) > 10,
            "description": "Produces a concise summary under 20 words",
        },
        {
            "name": "preserves key facts",
            "input": "The Eiffel Tower was built in 1889 in Paris, France. It stands 330 meters tall and was designed by Gustave Eiffel.",
            "check": lambda r: "1889" in r or "paris" in r.lower() or "eiffel" in r.lower(),
            "description": "Retains key facts from source",
        },
        {
            "name": "handles short input",
            "input": "AI is useful.",
            "check": lambda r: len(r) > 0,
            "description": "Handles very short input without error",
        },
    ],
    "qa": [
        {
            "name": "factual answer",
            "input": "What is the capital of France?",
            "check": lambda r: "paris" in r.lower(),
            "description": "Returns correct factual answer",
        },
        {
            "name": "math answer",
            "input": "What is 12 multiplied by 12?",
            "check": lambda r: "144" in r,
            "description": "Returns correct math answer",
        },
        {
            "name": "handles unknown",
            "input": "What is the population of the fictional city of Zyrex?",
            "check": lambda r: len(r) > 0,
            "description": "Responds gracefully to unknown questions",
        },
    ],
    "classification": [
        {
            "name": "positive sentiment",
            "input": "I absolutely love this product, it works great!",
            "check": lambda r: "positive" in r.lower(),
            "description": "Correctly identifies positive sentiment",
        },
        {
            "name": "negative sentiment",
            "input": "This is terrible, I hate it and want a refund.",
            "check": lambda r: "negative" in r.lower(),
            "description": "Correctly identifies negative sentiment",
        },
        {
            "name": "neutral sentiment",
            "input": "The package arrived on Tuesday.",
            "check": lambda r: "neutral" in r.lower(),
            "description": "Correctly identifies neutral sentiment",
        },
    ],
    "coding": [
        {
            "name": "python function",
            "input": "Write a python function that returns the sum of two numbers.",
            "check": lambda r: "def " in r and "return" in r,
            "description": "Produces valid Python function",
        },
        {
            "name": "explains code",
            "input": "Explain what this does: for i in range(10): print(i)",
            "check": lambda r: len(r) > 20,
            "description": "Provides meaningful code explanation",
        },
    ],
}


def run_benchmark(root: Path, benchmark_name: str | None, model: str | None, provider_name: str | None):
    from ryva.utils import load_manifest
    manifest = load_manifest(root)
    project = manifest.get("project", {})

    providers = project.get("providers", {})
    default_provider = provider_name or providers.get("default", "anthropic")
    provider_cfg = providers.get(default_provider, {})
    default_model = model or provider_cfg.get("model", "claude-sonnet-4-6")
    provider = get_provider(default_provider, {"api_key": os.environ.get("ANTHROPIC_API_KEY", "")})

    targets = {benchmark_name: BENCHMARKS[benchmark_name]} if benchmark_name and benchmark_name in BENCHMARKS else BENCHMARKS

    if benchmark_name and benchmark_name not in BENCHMARKS:
        console.print(f"[red]Benchmark '{benchmark_name}' not found.[/red]")
        console.print(f"Available: {', '.join(BENCHMARKS.keys())}")
        return

    all_results = []
    for bname, cases in targets.items():
        console.print(f"\n[bold cyan]Running benchmark: {bname}[/bold cyan]")
        for case in cases:
            try:
                response = provider.complete(case["input"], default_model, 512)
                passed = case["check"](response)
                detail = case["description"]
            except Exception as e:
                passed = False
                detail = f"error: {str(e)[:60]}"
            all_results.append((bname, case["name"], passed, detail))

    _print_results(all_results, default_model, default_provider)


def list_benchmarks():
    table = Table(title="Available Benchmarks", header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Cases", justify="right")
    table.add_column("Description")

    descriptions = {
        "summarization": "Tests text summarization quality and accuracy",
        "qa": "Tests question answering and factual recall",
        "classification": "Tests sentiment and category classification",
        "coding": "Tests code generation and explanation",
    }

    for name, cases in BENCHMARKS.items():
        table.add_row(name, str(len(cases)), descriptions.get(name, ""))

    console.print(table)


def _print_results(results: list, model: str, provider: str):
    table = Table(title=f"Benchmark Results — {model} ({provider})", header_style="bold")
    table.add_column("Benchmark", style="cyan")
    table.add_column("Test Case")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for bname, case, p, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        table.add_row(bname, case, status, detail)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} benchmark tests passed[/bold {color}]")
