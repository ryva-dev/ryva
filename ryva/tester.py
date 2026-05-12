from __future__ import annotations
import time
from pathlib import Path
from ryva.utils import load_manifest, load_yaml, console
from ryva.runner import run_agent
from rich.table import Table


def run_tests(root: Path, agent_name: str | None = None) -> bool:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})

    targets = {agent_name: agents[agent_name]} if agent_name and agent_name in agents else agents

    if not targets:
        console.print(f"[red]No agents found to test.[/red]")
        return False

    all_passed = True
    results = []

    for name, agent in targets.items():
        test_dir = root / "tests" / name
        if not test_dir.exists():
            console.print(f"[dim]No tests found for agent '{name}' at tests/{name}/[/dim]")
            continue

        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            test_type = test_data.get("type")
            cases = test_data.get("cases", [])

            for case in cases:
                case_name = case.get("name", test_file.stem)
                inp = case.get("input", {})
                expect = case.get("expect", {})

                passed, detail = _run_test_case(root, name, test_type, inp, expect, agent)
                results.append((name, case_name, test_type, passed, detail))
                if not passed:
                    all_passed = False

    _print_results(results)
    return all_passed


def _run_test_case(root, agent_name, test_type, input_data, expect, agent_def) -> tuple[bool, str]:
    try:
        if test_type == "schema":
            output = run_agent(root, agent_name, input_data)
            return _check_schema(output, expect)

        elif test_type == "latency_under_ms":
            threshold = expect.get("threshold", 5000)
            start = time.time()
            run_agent(root, agent_name, input_data)
            elapsed = int((time.time() - start) * 1000)
            passed = elapsed <= threshold
            return passed, f"{elapsed}ms (threshold: {threshold}ms)"

        elif test_type == "returns_non_empty":
            output = run_agent(root, agent_name, input_data)
            passed = bool(output) and output != {"raw_output": ""}
            return passed, "Output was non-empty" if passed else "Output was empty"

        elif test_type == "contains_key":
            key = expect.get("key")
            output = run_agent(root, agent_name, input_data)
            passed = key in output
            return passed, f"Key '{key}' {'found' if passed else 'not found'}"

        else:
            return False, f"Unknown test type: {test_type}"

    except Exception as e:
        return False, str(e)


def _check_schema(output: dict, expect: dict) -> tuple[bool, str]:
    for field_path, spec in expect.items():
        # strip "output." prefix if present
        keys = field_path.replace("output.", "").split(".")
        val = output
        for k in keys:
            if not isinstance(val, dict) or k not in val:
                return False, f"Missing field: {field_path}"
            val = val[k]

        expected_type = spec.get("type")
        if expected_type:
            type_map = {"str": str, "int": int, "float": float, "list": list, "dict": dict, "bool": bool}
            if expected_type in type_map and not isinstance(val, type_map[expected_type]):
                return False, f"Field '{field_path}' expected {expected_type}, got {type(val).__name__}"

        if "min_length" in spec and isinstance(val, str) and len(val) < spec["min_length"]:
            return False, f"Field '{field_path}' too short ({len(val)} < {spec['min_length']})"

        if "range" in spec and isinstance(val, (int, float)):
            lo, hi = spec["range"]
            if not (lo <= val <= hi):
                return False, f"Field '{field_path}' = {val} out of range [{lo}, {hi}]"

    return True, "All schema checks passed"


def _print_results(results: list):
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