from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

from rich.table import Table

from ryva.utils import console, load_yaml


def run_ml_tests(root: Path, model_name: str | None = None) -> bool:
    models_dir = root / "models"
    if not models_dir.exists():
        console.print("[dim]No models/ directory found.[/dim]")
        return True

    # Find model definitions
    model_files = list(models_dir.glob("*.yml"))
    if not model_files:
        console.print("[dim]No model definitions found in models/[/dim]")
        return True

    targets = []
    for f in model_files:
        data = load_yaml(f)
        if model_name and data.get("name") != model_name:
            continue
        targets.append(data)

    if not targets:
        console.print(f"[red]Model '{model_name}' not found.[/red]")
        return False

    all_passed = True
    results = []

    for model_def in targets:
        name = model_def.get("name")
        test_dir = root / "tests" / "models" / name
        if not test_dir.exists():
            console.print(f"[dim]No tests found for model '{name}' at tests/models/{name}/[/dim]")
            continue

        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            test_type = test_data.get("type")
            cases = test_data.get("cases", [])

            for case in cases:
                case_name = case.get("name", test_file.stem)
                passed, detail = _run_ml_test_case(
                    root, model_def, test_type, case
                )
                results.append((name, case_name, test_type, passed, detail))
                if not passed:
                    all_passed = False

    _print_results(results)
    return all_passed


def _run_ml_test_case(
    root: Path, model_def: dict, test_type: str, case: dict
) -> tuple[bool, str]:
    try:
        model = _load_model(root, model_def)

        if test_type == "accuracy":
            return _test_accuracy(model, model_def, case)
        elif test_type == "schema":
            return _test_schema(model, case)
        elif test_type == "latency":
            return _test_latency(model, case)
        elif test_type == "drift":
            return _test_drift(model, model_def, case)
        elif test_type == "threshold":
            return _test_threshold(model, case)
        else:
            return False, f"Unknown ML test type: {test_type}"

    except Exception as e:
        return False, str(e)


def _load_model(root: Path, model_def: dict):
    implementation = model_def.get("implementation")
    function = model_def.get("function", "load")

    if not implementation:
        raise ValueError("Model definition missing 'implementation' field")

    impl_path = root / implementation
    if not impl_path.exists():
        raise FileNotFoundError(f"Model implementation not found: {impl_path}")

    console.print(
        f"[yellow]⚠ Executing model implementation:[/yellow] {impl_path}\n"
        "[dim]Model implementation files run as Python code. Only load implementations you trust.[/dim]"
    )
    spec = importlib.util.spec_from_file_location("ml_model", impl_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, function):
        return getattr(module, function)()
    elif hasattr(module, "model"):
        return module.model
    else:
        raise ValueError(f"No '{function}' function or 'model' variable found in {impl_path}")


def _test_accuracy(model, model_def: dict, case: dict) -> tuple[bool, str]:
    inputs = case.get("inputs", [])
    expected = case.get("expected", [])
    threshold = case.get("threshold", 0.8)

    if not inputs or not expected:
        return False, "Missing inputs or expected values"

    correct = 0
    for inp, exp in zip(inputs, expected):
        try:
            result = model.predict([inp] if not isinstance(inp, list) else [inp])
            pred = result[0] if hasattr(result, '__iter__') else result
            if str(pred) == str(exp):
                correct += 1
        except Exception as e:
            return False, f"Prediction failed: {e}"

    accuracy = correct / len(inputs)
    passed = accuracy >= threshold
    return passed, f"Accuracy: {accuracy:.2%} (threshold: {threshold:.2%})"


def _test_schema(model, case: dict) -> tuple[bool, str]:
    inp = case.get("input")
    expect = case.get("expect", {})

    if inp is None:
        return False, "Missing input"

    try:
        result = model.predict([inp] if not isinstance(inp, list) else [inp])
        output = result[0] if hasattr(result, '__iter__') else result
    except Exception as e:
        return False, f"Prediction failed: {e}"

    expected_type = expect.get("type")
    if expected_type:
        type_map = {"str": str, "int": int, "float": float, "list": list}
        if expected_type in type_map and not isinstance(output, type_map[expected_type]):
            return False, f"Expected {expected_type}, got {type(output).__name__}"

    if "range" in expect:
        lo, hi = expect["range"]
        if not (lo <= float(output) <= hi):
            return False, f"Output {output} out of range [{lo}, {hi}]"

    return True, "Schema check passed"


def _test_latency(model, case: dict) -> tuple[bool, str]:
    inp = case.get("input")
    threshold_ms = case.get("threshold_ms", 1000)

    if inp is None:
        return False, "Missing input"

    start = time.time()
    try:
        model.predict([inp] if not isinstance(inp, list) else [inp])
    except Exception as e:
        return False, f"Prediction failed: {e}"

    elapsed = int((time.time() - start) * 1000)
    passed = elapsed <= threshold_ms
    return passed, f"{elapsed}ms (threshold: {threshold_ms}ms)"


def _test_drift(model, model_def: dict, case: dict) -> tuple[bool, str]:
    baseline_path = case.get("baseline")
    inputs = case.get("inputs", [])
    threshold = case.get("threshold", 0.1)

    if not baseline_path or not inputs:
        return False, "Missing baseline or inputs"

    try:
        with open(baseline_path) as f:
            baseline = json.load(f)
    except Exception as e:
        return False, f"Could not load baseline: {e}"

    current_preds = []
    for inp in inputs:
        result = model.predict([inp] if not isinstance(inp, list) else [inp])
        pred = result[0] if hasattr(result, '__iter__') else result
        current_preds.append(pred)

    baseline_preds = baseline.get("predictions", [])
    if len(current_preds) != len(baseline_preds):
        return False, "Prediction count mismatch with baseline"

    drift = sum(
        1 for c, b in zip(current_preds, baseline_preds) if str(c) != str(b)
    ) / len(current_preds)

    passed = drift <= threshold
    return passed, f"Drift: {drift:.2%} (threshold: {threshold:.2%})"


def _test_threshold(model, case: dict) -> tuple[bool, str]:
    inp = case.get("input")
    metric = case.get("metric", "prediction")
    operator = case.get("operator", "gte")
    value = case.get("value", 0.5)

    if inp is None:
        return False, "Missing input"

    try:
        if hasattr(model, "predict_proba"):
            result = model.predict_proba([inp] if not isinstance(inp, list) else [inp])
            output = float(result[0][1])
        else:
            result = model.predict([inp] if not isinstance(inp, list) else [inp])
            output = float(result[0] if hasattr(result, '__iter__') else result)
    except Exception as e:
        return False, f"Prediction failed: {e}"

    ops = {
        "gte": output >= value,
        "lte": output <= value,
        "gt": output > value,
        "lt": output < value,
        "eq": output == value,
    }

    passed = ops.get(operator, False)
    return passed, f"{metric} = {output:.4f} ({operator} {value})"


def _print_results(results: list):
    console.print()
    table = Table(title="ML Model Test Results", show_header=True, header_style="bold")
    table.add_column("Model", style="cyan")
    table.add_column("Test Case")
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for model, case, typ, p, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        table.add_row(model, case, typ or "—", status, detail)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} ML tests passed[/bold {color}]")
