from __future__ import annotations

import time
from pathlib import Path

from rich.table import Table

from ryva.pipeline_runner import run_pipeline
from ryva.utils import console, load_manifest, load_yaml


def run_pipeline_tests(root: Path, pipeline_name: str | None = None) -> bool:
    manifest = load_manifest(root)
    pipelines = manifest.get("pipelines", {})

    targets = (
        {pipeline_name: pipelines[pipeline_name]}
        if pipeline_name and pipeline_name in pipelines
        else pipelines
    )

    if not targets:
        console.print("[red]No pipelines found.[/red]")
        return False

    all_passed = True
    results = []

    for name in targets:
        test_dir = root / "tests" / "pipelines" / name
        if not test_dir.exists():
            console.print(
                f"[dim]No pipeline tests found at tests/pipelines/{name}/[/dim]"
            )
            continue

        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            cases = test_data.get("cases", [])
            test_type = test_data.get("type", "pipeline")

            for case in cases:
                case_name = case.get("name", test_file.stem)
                inp = case.get("input", {})
                expect = case.get("expect", {})

                passed, detail = _run_pipeline_test_case(
                    root, name, test_type, inp, expect
                )
                results.append((name, case_name, test_type, passed, detail))
                if not passed:
                    all_passed = False

    _print_results(results)
    return all_passed


def _run_pipeline_test_case(
    root: Path,
    pipeline_name: str,
    test_type: str,
    input_data: dict,
    expect: dict
) -> tuple[bool, str]:
    try:
        if test_type == "pipeline":
            start = time.time()
            result = run_pipeline(root, pipeline_name, input_data)
            elapsed = int((time.time() - start) * 1000)
            return _check_pipeline_output(result, expect, elapsed)

        elif test_type == "pipeline_latency":
            threshold = expect.get("max_ms", 10000)
            start = time.time()
            run_pipeline(root, pipeline_name, input_data)
            elapsed = int((time.time() - start) * 1000)
            passed = elapsed <= threshold
            return passed, f"{elapsed}ms (threshold: {threshold}ms)"

        elif test_type == "pipeline_steps":
            result = run_pipeline(root, pipeline_name, input_data)
            return _check_step_outputs(result, expect)

        else:
            return False, f"Unknown pipeline test type: {test_type}"

    except Exception as e:
        return False, str(e)


def _check_pipeline_output(
    result: dict, expect: dict, elapsed: int
) -> tuple[bool, str]:
    output = result.get("output", {})
    steps = result.get("steps", {})

    for field_path, spec in expect.items():
        # Handle step output checks e.g. steps.research.output.report
        if field_path.startswith("steps."):
            parts = field_path.split(".")
            # steps.step_name.output.field
            if len(parts) >= 4:
                step_name = parts[1]
                field = parts[3]
                step_data = steps.get(step_name, {})
                val = step_data.get("output", {}).get(field)
            else:
                continue
        elif field_path.startswith("output."):
            key = field_path.replace("output.", "")
            val = output.get(key)
        elif field_path == "elapsed_ms":
            max_ms = spec.get("max", 999999)
            if elapsed > max_ms:
                return False, f"Pipeline took {elapsed}ms (max: {max_ms}ms)"
            continue
        else:
            val = output.get(field_path)

        if val is None:
            return False, f"Missing field: {field_path}"

        if isinstance(spec, dict):
            expected_type = spec.get("type")
            if expected_type:
                type_map = {
                    "str": str, "int": int, "float": float,
                    "list": list, "dict": dict, "bool": bool
                }
                if expected_type in type_map and not isinstance(val, type_map[expected_type]):
                    return False, f"Field '{field_path}' expected {expected_type}, got {type(val).__name__}"

            if "min_length" in spec and isinstance(val, str) and len(val) < spec["min_length"]:
                return False, f"Field '{field_path}' too short ({len(val)} < {spec['min_length']})"

            if "max_length" in spec and isinstance(val, str) and len(val) > spec["max_length"]:
                return False, f"Field '{field_path}' too long ({len(val)} > {spec['max_length']})"

            if "range" in spec and isinstance(val, (int, float)):
                lo, hi = spec["range"]
                if not (lo <= val <= hi):
                    return False, f"Field '{field_path}' = {val} out of range [{lo}, {hi}]"

    return True, "All pipeline checks passed"


def _check_step_outputs(result: dict, expect: dict) -> tuple[bool, str]:
    steps = result.get("steps", {})

    for step_name, step_expect in expect.items():
        if step_name not in steps:
            return False, f"Step '{step_name}' not found in results"

        step = steps[step_name]

        if "status" in step_expect:
            if step["status"] != step_expect["status"]:
                return False, f"Step '{step_name}' status was '{step['status']}', expected '{step_expect['status']}'"

        if "output" in step_expect:
            for field, spec in step_expect["output"].items():
                val = step.get("output", {}).get(field)
                if val is None:
                    return False, f"Step '{step_name}' missing output field '{field}'"

    return True, "All step checks passed"


def _print_results(results: list):
    console.print()
    table = Table(title="Pipeline Test Results", show_header=True, header_style="bold")
    table.add_column("Pipeline", style="cyan")
    table.add_column("Test Case")
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for pipeline, case, typ, p, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        table.add_row(pipeline, case, typ or "—", status, detail)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} pipeline tests passed[/bold {color}]")
