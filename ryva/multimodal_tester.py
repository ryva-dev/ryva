from __future__ import annotations

import importlib.util
import time
from pathlib import Path

from rich.table import Table

from ryva.utils import console, load_yaml


def run_multimodal_tests(root: Path, model_name: str | None = None) -> bool:
    models_dir = root / "multimodal"
    if not models_dir.exists():
        console.print("[dim]No multimodal/ directory found.[/dim]")
        return True

    model_files = list(models_dir.glob("*.yml"))
    if not model_files:
        console.print("[dim]No multimodal model definitions found.[/dim]")
        return True

    targets = []
    for f in model_files:
        data = load_yaml(f)
        if model_name and data.get("name") != model_name:
            continue
        targets.append(data)

    if not targets:
        console.print(f"[red]Multimodal model '{model_name}' not found.[/red]")
        return False

    all_passed = True
    results = []

    for model_def in targets:
        name = model_def.get("name")
        modality = model_def.get("modality", "vision")
        test_dir = root / "tests" / "multimodal" / name
        if not test_dir.exists():
            console.print(f"[dim]No tests found for multimodal model '{name}'[/dim]")
            continue

        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            test_type = test_data.get("type")
            cases = test_data.get("cases", [])

            for case in cases:
                case_name = case.get("name", test_file.stem)
                passed, detail = _run_multimodal_test(
                    root, model_def, modality, test_type, case
                )
                results.append((name, case_name, test_type, passed, detail))
                if not passed:
                    all_passed = False

    _print_results(results)
    return all_passed


def _run_multimodal_test(
    root: Path,
    model_def: dict,
    modality: str,
    test_type: str,
    case: dict
) -> tuple[bool, str]:
    try:
        if modality == "vision":
            return _run_vision_test(root, model_def, test_type, case)
        elif modality == "document":
            return _run_document_test(root, model_def, test_type, case)
        elif modality == "audio":
            return _run_audio_test(root, model_def, test_type, case)
        else:
            return False, f"Unknown modality: {modality}"
    except Exception as e:
        return False, str(e)


def _load_model(root: Path, model_def: dict):
    implementation = model_def.get("implementation")
    function = model_def.get("function", "load")

    if not implementation:
        raise ValueError("Missing 'implementation' field")

    impl_path = root / implementation
    if not impl_path.exists():
        raise FileNotFoundError(f"Implementation not found: {impl_path}")

    spec = importlib.util.spec_from_file_location("mm_model", impl_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if hasattr(module, function):
        return getattr(module, function)()
    elif hasattr(module, "model"):
        return module.model
    else:
        raise ValueError(f"No '{function}' function or 'model' variable found")


def _run_vision_test(
    root: Path, model_def: dict, test_type: str, case: dict
) -> tuple[bool, str]:
    model = _load_model(root, model_def)

    if test_type == "classification":
        image_path = case.get("image")
        expected = case.get("expected")
        threshold = case.get("threshold", 0.5)

        if not image_path:
            return False, "Missing image path"

        full_path = root / image_path
        if not full_path.exists():
            return False, f"Image not found: {full_path}"

        start = time.time()
        result = model.classify(str(full_path))
        elapsed = int((time.time() - start) * 1000)

        label = result.get("label", "")
        score = result.get("score", 0.0)

        if expected and label != expected:
            return False, f"Expected '{expected}', got '{label}' ({score:.3f})"
        if score < threshold:
            return False, f"Confidence {score:.3f} below threshold {threshold}"

        return True, f"Label: '{label}' ({score:.3f}) in {elapsed}ms"

    elif test_type == "detection":
        image_path = case.get("image")
        expected_labels = case.get("expected_labels", [])
        min_detections = case.get("min_detections", 1)

        if not image_path:
            return False, "Missing image path"

        full_path = root / image_path
        if not full_path.exists():
            return False, f"Image not found: {full_path}"

        result = model.detect(str(full_path))
        detections = result.get("detections", [])

        if len(detections) < min_detections:
            return False, f"Only {len(detections)} detections (min: {min_detections})"

        if expected_labels:
            found_labels = [d.get("label") for d in detections]
            missing = [label for label in expected_labels if label not in found_labels]
            if missing:
                return False, f"Missing expected labels: {missing}"

        return True, f"{len(detections)} object(s) detected"

    elif test_type == "latency":
        image_path = case.get("image")
        threshold_ms = case.get("threshold_ms", 1000)

        if not image_path:
            return False, "Missing image path"

        full_path = root / image_path
        if not full_path.exists():
            return False, f"Image not found: {full_path}"

        start = time.time()
        model.classify(str(full_path))
        elapsed = int((time.time() - start) * 1000)

        passed = elapsed <= threshold_ms
        return passed, f"{elapsed}ms (threshold: {threshold_ms}ms)"

    return False, f"Unknown vision test type: {test_type}"


def _run_document_test(
    root: Path, model_def: dict, test_type: str, case: dict
) -> tuple[bool, str]:
    model = _load_model(root, model_def)

    if test_type == "extraction":
        doc_path = case.get("document")
        expected_fields = case.get("expected_fields", [])
        threshold = case.get("threshold", 1.0)

        if not doc_path:
            return False, "Missing document path"

        full_path = root / doc_path
        if not full_path.exists():
            return False, f"Document not found: {full_path}"

        result = model.extract(str(full_path))

        found = sum(1 for f in expected_fields if f in result)
        recall = found / len(expected_fields) if expected_fields else 1.0

        passed = recall >= threshold
        return passed, f"Extracted {found}/{len(expected_fields)} fields ({recall:.2%})"

    elif test_type == "classification":
        doc_path = case.get("document")
        expected = case.get("expected")

        if not doc_path:
            return False, "Missing document path"

        full_path = root / doc_path
        if not full_path.exists():
            return False, f"Document not found: {full_path}"

        result = model.classify(str(full_path))
        label = result.get("label", "")

        passed = label == expected if expected else True
        return passed, f"Label: '{label}'"

    return False, f"Unknown document test type: {test_type}"


def _run_audio_test(
    root: Path, model_def: dict, test_type: str, case: dict
) -> tuple[bool, str]:
    model = _load_model(root, model_def)

    if test_type == "transcription":
        audio_path = case.get("audio")
        expected_text = case.get("expected_text", "")
        similarity_threshold = case.get("similarity_threshold", 0.8)

        if not audio_path:
            return False, "Missing audio path"

        full_path = root / audio_path
        if not full_path.exists():
            return False, f"Audio not found: {full_path}"

        result = model.transcribe(str(full_path))
        transcript = result.get("text", "")

        if expected_text:
            similarity = _text_similarity(transcript, expected_text)
            passed = similarity >= similarity_threshold
            return passed, f"Similarity: {similarity:.2%} (threshold: {similarity_threshold:.2%})"

        return bool(transcript), f"Transcript: '{transcript[:50]}...'"

    elif test_type == "latency":
        audio_path = case.get("audio")
        threshold_ms = case.get("threshold_ms", 2000)

        if not audio_path:
            return False, "Missing audio path"

        full_path = root / audio_path
        if not full_path.exists():
            return False, f"Audio not found: {full_path}"

        start = time.time()
        model.transcribe(str(full_path))
        elapsed = int((time.time() - start) * 1000)

        passed = elapsed <= threshold_ms
        return passed, f"{elapsed}ms (threshold: {threshold_ms}ms)"

    return False, f"Unknown audio test type: {test_type}"


def _text_similarity(a: str, b: str) -> float:
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _print_results(results: list):
    console.print()
    table = Table(
        title="Multimodal Test Results",
        show_header=True,
        header_style="bold"
    )
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
    console.print(f"\n[bold {color}]{passed}/{total} multimodal tests passed[/bold {color}]")
