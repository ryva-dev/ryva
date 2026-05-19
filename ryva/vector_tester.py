from __future__ import annotations
import time
import importlib.util
from pathlib import Path
from ryva.utils import load_yaml, console
from rich.table import Table


def run_vector_tests(root: Path, store_name: str | None = None) -> bool:
    stores_dir = root / "vector_stores"
    if not stores_dir.exists():
        console.print("[dim]No vector_stores/ directory found.[/dim]")
        return True

    store_files = list(stores_dir.glob("*.yml"))
    if not store_files:
        console.print("[dim]No vector store definitions found.[/dim]")
        return True

    targets = []
    for f in store_files:
        data = load_yaml(f)
        if store_name and data.get("name") != store_name:
            continue
        targets.append(data)

    if not targets:
        console.print(f"[red]Vector store '{store_name}' not found.[/red]")
        return False

    all_passed = True
    results = []

    for store_def in targets:
        name = store_def.get("name")
        test_dir = root / "tests" / "vector_stores" / name
        if not test_dir.exists():
            console.print(f"[dim]No tests found for vector store '{name}'[/dim]")
            continue

        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            test_type = test_data.get("type")
            cases = test_data.get("cases", [])

            for case in cases:
                case_name = case.get("name", test_file.stem)
                passed, detail = _run_vector_test_case(
                    root, store_def, test_type, case
                )
                results.append((name, case_name, test_type, passed, detail))
                if not passed:
                    all_passed = False

    _print_results(results)
    return all_passed


def _run_vector_test_case(
    root: Path, store_def: dict, test_type: str, case: dict
) -> tuple[bool, str]:
    try:
        store = _load_store(root, store_def)

        if test_type == "relevance":
            return _test_relevance(store, case)
        elif test_type == "recall":
            return _test_recall(store, case)
        elif test_type == "latency":
            return _test_latency(store, case)
        elif test_type == "coverage":
            return _test_coverage(store, case)
        elif test_type == "top_k":
            return _test_top_k(store, case)
        else:
            return False, f"Unknown vector test type: {test_type}"

    except Exception as e:
        return False, str(e)


def _load_store(root: Path, store_def: dict):
    implementation = store_def.get("implementation")
    function = store_def.get("function", "load")

    if not implementation:
        raise ValueError("Vector store definition missing 'implementation'")

    impl_path = root / implementation
    if not impl_path.exists():
        raise FileNotFoundError(f"Implementation not found: {impl_path}")

    spec = importlib.util.spec_from_file_location("vector_store", impl_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, function):
        return getattr(module, function)()
    elif hasattr(module, "store"):
        return module.store
    else:
        raise ValueError(f"No '{function}' function or 'store' variable found")


def _test_relevance(store, case: dict) -> tuple[bool, str]:
    """Test that queries return relevant results above a score threshold."""
    query = case.get("query")
    threshold = case.get("threshold", 0.7)
    top_k = case.get("top_k", 5)
    expected_ids = case.get("expected_ids", [])

    if not query:
        return False, "Missing query"

    results = store.query(query, top_k=top_k)

    if not results:
        return False, "No results returned"

    # Check if top result meets relevance threshold
    top_score = results[0].get("score", 0) if isinstance(results[0], dict) else 0
    if top_score < threshold:
        return False, f"Top result score {top_score:.3f} below threshold {threshold}"

    # Check expected IDs are in results if provided
    if expected_ids:
        result_ids = [r.get("id") for r in results if isinstance(r, dict)]
        found = sum(1 for eid in expected_ids if eid in result_ids)
        recall = found / len(expected_ids)
        if recall < threshold:
            return False, f"Only found {found}/{len(expected_ids)} expected results"

    return True, f"Top score: {top_score:.3f} (threshold: {threshold})"


def _test_recall(store, case: dict) -> tuple[bool, str]:
    """Test recall@k — what % of relevant docs appear in top k results."""
    query = case.get("query")
    relevant_ids = case.get("relevant_ids", [])
    top_k = case.get("top_k", 10)
    threshold = case.get("threshold", 0.8)

    if not query or not relevant_ids:
        return False, "Missing query or relevant_ids"

    results = store.query(query, top_k=top_k)
    result_ids = [r.get("id") for r in results if isinstance(r, dict)]

    found = sum(1 for rid in relevant_ids if rid in result_ids)
    recall = found / len(relevant_ids)
    passed = recall >= threshold

    return passed, f"Recall@{top_k}: {recall:.2%} (threshold: {threshold:.2%})"


def _test_latency(store, case: dict) -> tuple[bool, str]:
    """Test that queries return within a latency threshold."""
    query = case.get("query")
    threshold_ms = case.get("threshold_ms", 500)
    top_k = case.get("top_k", 5)

    if not query:
        return False, "Missing query"

    start = time.time()
    store.query(query, top_k=top_k)
    elapsed = int((time.time() - start) * 1000)

    passed = elapsed <= threshold_ms
    return passed, f"{elapsed}ms (threshold: {threshold_ms}ms)"


def _test_coverage(store, case: dict) -> tuple[bool, str]:
    """Test that the store contains expected documents."""
    expected_ids = case.get("expected_ids", [])
    if not expected_ids:
        return False, "Missing expected_ids"

    found = 0
    for doc_id in expected_ids:
        try:
            result = store.get(doc_id)
            if result:
                found += 1
        except Exception:
            pass

    coverage = found / len(expected_ids)
    threshold = case.get("threshold", 1.0)
    passed = coverage >= threshold

    return passed, f"Coverage: {found}/{len(expected_ids)} ({coverage:.2%})"


def _test_top_k(store, case: dict) -> tuple[bool, str]:
    """Test that the top result for a query is the expected document."""
    query = case.get("query")
    expected_top_id = case.get("expected_top_id")

    if not query or not expected_top_id:
        return False, "Missing query or expected_top_id"

    results = store.query(query, top_k=1)
    if not results:
        return False, "No results returned"

    top_id = results[0].get("id") if isinstance(results[0], dict) else None
    passed = top_id == expected_top_id

    return passed, f"Top result: '{top_id}' (expected: '{expected_top_id}')"


def _print_results(results: list):
    console.print()
    table = Table(
        title="Vector Store Test Results",
        show_header=True,
        header_style="bold"
    )
    table.add_column("Store", style="cyan")
    table.add_column("Test Case")
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for store, case, typ, p, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        table.add_row(store, case, typ or "—", status, detail)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} vector tests passed[/bold {color}]")