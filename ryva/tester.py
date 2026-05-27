from __future__ import annotations

import asyncio
import time
from pathlib import Path

from rich.table import Table

from ryva.utils import console, load_manifest, load_yaml


def run_tests(
    root: Path,
    agent_name: str | None = None,
    concurrency: int = 10,
) -> bool:
    """Run agent tests concurrently. concurrency is capped at 20."""
    concurrency = max(1, min(concurrency, 20))
    return asyncio.run(_run_tests_async(root, agent_name, concurrency))


async def _run_tests_async(
    root: Path,
    agent_name: str | None,
    concurrency: int,
) -> bool:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})
    targets = (
        {agent_name: agents[agent_name]}
        if agent_name and agent_name in agents
        else agents
    )

    if not targets:
        console.print("[red]No agents found to test.[/red]")
        return False

    # Collect all jobs, preserving agent → file → case ordering for output
    jobs: list[tuple] = []
    for name, agent in targets.items():
        test_dir = root / "tests" / name
        if not test_dir.exists():
            console.print(
                f"[dim]No tests found for agent '{name}' at tests/{name}/[/dim]"
            )
            continue
        for test_file in sorted(test_dir.glob("*.yml")):
            test_data = load_yaml(test_file)
            test_type = test_data.get("type")
            for case in test_data.get("cases", []):
                jobs.append((
                    name,
                    case.get("name", test_file.stem),
                    test_type,
                    case.get("input", {}),
                    case.get("expect", {}),
                    agent,
                ))

    if not jobs:
        console.print("[dim]No test cases found.[/dim]")
        return True

    semaphore = asyncio.Semaphore(concurrency)
    # Track per-case elapsed times to compute sequential estimate
    individual_times: list[float] = [0.0] * len(jobs)

    async def run_one(idx: int, job: tuple):
        name, case_name, test_type, inp, expect, agent_def = job
        async with semaphore:
            t0 = time.perf_counter()
            passed, detail = await asyncio.to_thread(
                _run_test_case, root, name, test_type, inp, expect, agent_def
            )
            individual_times[idx] = time.perf_counter() - t0
            return (name, case_name, test_type, passed, detail)

    wall_start = time.perf_counter()
    results = await asyncio.gather(*(run_one(i, j) for i, j in enumerate(jobs)))
    wall_elapsed = time.perf_counter() - wall_start

    sequential_estimate = sum(individual_times)
    speedup = sequential_estimate / max(wall_elapsed, 0.001)

    _print_results(
        list(results),
        root,
        concurrency=concurrency,
        speedup=speedup,
        wall_elapsed=wall_elapsed,
    )
    return all(r[3] for r in results)


def _run_test_case(
    root: Path,
    agent_name: str,
    test_type: str | None,
    input_data: dict,
    expect: dict,
    agent_def: dict,
) -> tuple[bool, str]:
    from ryva.plugins import get_test_plugin, load_plugins
    from ryva.runner import run_agent
    load_plugins()

    try:
        plugin = get_test_plugin(test_type)
        if plugin:
            result = plugin(root, agent_name, input_data, expect, agent_def)
            return result.get("passed", False), result.get("detail", "")

        if test_type == "schema":
            output = run_agent(root, agent_name, input_data)
            return _check_schema(output, expect)

        if test_type == "latency_under_ms":
            threshold = expect.get("threshold", 5000)
            start = time.time()
            run_agent(root, agent_name, input_data)
            elapsed = int((time.time() - start) * 1000)
            passed = elapsed <= threshold
            return passed, f"{elapsed}ms (threshold: {threshold}ms)"

        if test_type == "returns_non_empty":
            output = run_agent(root, agent_name, input_data)
            passed = bool(output) and output != {"raw_output": ""}
            return passed, "non-empty" if passed else "empty output"

        if test_type == "contains_key":
            key = expect.get("key")
            output = run_agent(root, agent_name, input_data)
            passed = key in output
            return passed, f"key '{key}' {'found' if passed else 'not found'}"

        return False, f"Unknown test type: '{test_type}'"

    except Exception as e:
        return False, str(e)[:120]


def _check_schema(output: dict, expect: dict) -> tuple[bool, str]:
    for field_path, spec in expect.items():
        keys = field_path.replace("output.", "").split(".")
        val = output
        for k in keys:
            if not isinstance(val, dict) or k not in val:
                return False, f"Missing field: {field_path}"
            val = val[k]

        expected_type = spec.get("type")
        if expected_type:
            type_map = {
                "str": str, "int": int, "float": float,
                "list": list, "dict": dict, "bool": bool,
            }
            if expected_type in type_map and not isinstance(val, type_map[expected_type]):
                return False, (
                    f"Field '{field_path}' expected {expected_type}, "
                    f"got {type(val).__name__}"
                )

        if "min_length" in spec and isinstance(val, str) and len(val) < spec["min_length"]:
            return False, (
                f"Field '{field_path}' too short "
                f"({len(val)} < {spec['min_length']})"
            )

        if "range" in spec and isinstance(val, (int, float)):
            lo, hi = spec["range"]
            if not (lo <= val <= hi):
                return False, (
                    f"Field '{field_path}' = {val} out of range [{lo}, {hi}]"
                )

    return True, "All schema checks passed"


def _print_results(
    results: list,
    root: Path | None = None,
    concurrency: int = 1,
    speedup: float = 1.0,
    wall_elapsed: float = 0.0,
) -> None:
    console.print()
    table = Table(title="Test Results", show_header=True, header_style="bold")
    table.add_column("Agent", style="cyan")
    table.add_column("Test Case")
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for agent, case, typ, p, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        table.add_row(agent, case, typ or "—", status, detail)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} tests passed[/bold {color}]")

    if len(results) > 1 and speedup > 1.1:
        console.print(
            f"[dim]parallelism: {speedup:.1f}x faster than sequential "
            f"(concurrency={concurrency}, wall={wall_elapsed:.2f}s)[/dim]"
        )

    if root:
        try:
            from ryva.cost_tracker import get_cost_summary
            summary = get_cost_summary(root)
            if summary["total_cost"] > 0:
                console.print(
                    f"[dim]Test run cost: ~${summary['total_cost']:.6f} this month "
                    f"({summary['total_runs']} total runs)[/dim]"
                )
        except (FileNotFoundError, OSError):
            pass
