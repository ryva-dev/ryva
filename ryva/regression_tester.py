from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from ryva.runner import run_agent
from ryva.utils import console, load_manifest, load_yaml


def run_regression_tests(
    root: Path,
    agent_name: str | None = None,
    baseline: str | None = None
) -> bool:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})

    targets = (
        {agent_name: agents[agent_name]}
        if agent_name and agent_name in agents
        else agents
    )

    if not targets:
        console.print("[red]No agents found.[/red]")
        return False

    all_passed = True
    results = []

    for name, agent in targets.items():
        baseline_path = _get_baseline_path(root, name, baseline)

        if not baseline_path.exists():
            console.print(
                f"[yellow]No baseline found for '{name}'. "
                f"Run `ryva baseline --agent {name}` to create one.[/yellow]"
            )
            continue

        baseline_data = json.loads(baseline_path.read_text())
        console.print(Panel(
            f"[bold cyan]Regression Test:[/bold cyan] [bold]{name}[/bold]\n"
            f"[dim]Baseline: {baseline_data.get('created_at', 'unknown')}[/dim]",
            expand=False
        ))

        for case in baseline_data.get("cases", []):
            passed, detail, delta = _run_regression_case(
                root, name, case
            )
            results.append((name, case["name"], passed, delta, detail))
            if not passed:
                all_passed = False

    if not results:
        console.print("[dim]No regression tests ran. Create baselines first with `ryva baseline`.[/dim]")
        return True

    _print_results(results)
    return all_passed


def create_baseline(
    root: Path,
    agent_name: str,
    label: str | None = None
) -> None:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})

    if agent_name not in agents:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        return

    # Load existing test cases
    test_dir = root / "tests" / agent_name
    if not test_dir.exists():
        console.print(f"[red]No tests found for '{agent_name}'.[/red]")
        return

    cases = []
    for test_file in test_dir.glob("*.yml"):
        test_data = load_yaml(test_file)
        for case in test_data.get("cases", []):
            inp = case.get("input", {})
            console.print(f"[dim]Running baseline case: {case.get('name')}...[/dim]")

            try:
                start = time.time()
                output = run_agent(root, agent_name, inp)
                elapsed = int((time.time() - start) * 1000)

                cases.append({
                    "name": case.get("name", test_file.stem),
                    "input": inp,
                    "baseline_output": output,
                    "baseline_latency_ms": elapsed,
                    "expect": case.get("expect", {})
                })
            except Exception as e:
                console.print(f"[yellow]Skipping case '{case.get('name')}': {e}[/yellow]")

    if not cases:
        console.print("[red]No baseline cases captured.[/red]")
        return

    baseline = {
        "agent": agent_name,
        "label": label or "baseline",
        "created_at": datetime.now(UTC).isoformat(),
        "cases": cases
    }

    baseline_path = _get_baseline_path(root, agent_name)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(json.dumps(baseline, indent=2))

    console.print(
        f"\n[bold green]✓ Baseline created[/bold green] for [cyan]{agent_name}[/cyan]\n"
        f"[dim]{len(cases)} cases saved to {baseline_path}[/dim]"
    )


def _get_baseline_path(
    root: Path,
    agent_name: str,
    label: str | None = None
) -> Path:
    name = f"{label or 'baseline'}.json"
    return root / "baselines" / agent_name / name


def _run_regression_case(
    root: Path,
    agent_name: str,
    case: dict
) -> tuple[bool, str, dict]:
    inp = case.get("input", {})
    baseline_output = case.get("baseline_output", {})
    baseline_latency = case.get("baseline_latency_ms", 0)
    expect = case.get("expect", {})

    try:
        start = time.time()
        current_output = run_agent(root, agent_name, inp)
        current_latency = int((time.time() - start) * 1000)

        delta = _compute_delta(baseline_output, current_output, baseline_latency, current_latency)

        issues = []

        # Check schema regression
        if expect:
            from ryva.tester import _check_schema
            passed_schema, schema_detail = _check_schema(current_output, expect)
            if not passed_schema:
                issues.append(f"Schema: {schema_detail}")

        # Check latency regression (>50% slower is a regression)
        if baseline_latency > 0:
            latency_ratio = current_latency / baseline_latency
            if latency_ratio > 1.5:
                issues.append(
                    f"Latency regression: {current_latency}ms vs {baseline_latency}ms baseline "
                    f"({latency_ratio:.1f}x slower)"
                )

        # Check output structure regression
        baseline_keys = set(baseline_output.keys()) if isinstance(baseline_output, dict) else set()
        current_keys = set(current_output.keys()) if isinstance(current_output, dict) else set()
        missing_keys = baseline_keys - current_keys
        if missing_keys:
            issues.append(f"Missing keys: {missing_keys}")

        passed = len(issues) == 0
        detail = "No regression" if passed else " | ".join(issues)

        return passed, detail, delta

    except Exception as e:
        return False, str(e)[:80], {}


def _compute_delta(
    baseline: dict,
    current: dict,
    baseline_latency: int,
    current_latency: int
) -> dict:
    latency_change = current_latency - baseline_latency
    latency_pct = (latency_change / baseline_latency * 100) if baseline_latency > 0 else 0

    baseline_keys = set(baseline.keys()) if isinstance(baseline, dict) else set()
    current_keys = set(current.keys()) if isinstance(current, dict) else set()

    return {
        "latency_ms_change": latency_change,
        "latency_pct_change": round(latency_pct, 1),
        "keys_added": list(current_keys - baseline_keys),
        "keys_removed": list(baseline_keys - current_keys),
    }


def _print_results(results: list):
    console.print()
    table = Table(
        title="Regression Test Results",
        show_header=True,
        header_style="bold"
    )
    table.add_column("Agent", style="cyan")
    table.add_column("Test Case")
    table.add_column("Status", justify="center")
    table.add_column("Latency Delta", justify="right")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _, _ in results if p)
    total = len(results)

    for agent, case, p, delta, detail in results:
        status = "[bold green]✓ NO REGRESSION[/bold green]" if p else "[bold red]✗ REGRESSION[/bold red]"
        latency_change = delta.get("latency_ms_change", 0)
        latency_pct = delta.get("latency_pct_change", 0)
        if latency_change > 0:
            latency_str = f"[yellow]+{latency_change}ms (+{latency_pct}%)[/yellow]"
        elif latency_change < 0:
            latency_str = f"[green]{latency_change}ms ({latency_pct}%)[/green]"
        else:
            latency_str = "[dim]—[/dim]"

        table.add_row(agent, case, status, latency_str, detail)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} regression tests passed[/bold {color}]")
