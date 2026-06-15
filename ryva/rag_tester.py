from __future__ import annotations

from pathlib import Path

from rich.table import Table

from ryva.utils import console, load_yaml


def run_rag_tests(root: Path, pipeline_name: str | None = None) -> bool:
    rag_dir = root / "rag_pipelines"
    if not rag_dir.exists():
        console.print("[dim]No rag_pipelines/ directory found.[/dim]")
        return True

    pipeline_files = list(rag_dir.glob("*.yml"))
    if not pipeline_files:
        console.print("[dim]No RAG pipeline definitions found.[/dim]")
        return True

    targets = []
    for f in pipeline_files:
        data = load_yaml(f)
        if pipeline_name and data.get("name") != pipeline_name:
            continue
        targets.append(data)

    if not targets:
        console.print(f"[red]RAG pipeline '{pipeline_name}' not found.[/red]")
        return False

    all_passed = True
    results = []

    for pipeline_def in targets:
        name = pipeline_def.get("name")
        test_dir = root / "tests" / "rag" / name
        if not test_dir.exists():
            console.print(f"[dim]No RAG tests found at tests/rag/{name}/[/dim]")
            continue

        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            cases = test_data.get("cases", [])

            for case in cases:
                case_name = case.get("name", test_file.stem)
                passed, detail, scores = _run_rag_case(
                    root, pipeline_def, case
                )
                results.append((name, case_name, passed, scores, detail))
                if not passed:
                    all_passed = False

    _print_results(results)
    return all_passed


def _run_rag_case(
    root: Path,
    pipeline_def: dict,
    case: dict
) -> tuple[bool, str, dict]:
    import importlib.util

    question = case.get("question", "")
    expected_answer = case.get("expected_answer", "")
    context_docs = case.get("context_docs", [])
    thresholds = case.get("thresholds", {})

    retrieval_threshold = thresholds.get("retrieval_relevance", 0.5)
    faithfulness_threshold = thresholds.get("faithfulness", 0.7)
    answer_threshold = thresholds.get("answer_quality", 0.7)

    scores = {
        "retrieval_relevance": 0.0,
        "faithfulness": 0.0,
        "answer_quality": 0.0,
        "context_utilization": 0.0
    }

    try:
        # Step 1: Load the retriever
        retriever_impl = pipeline_def.get("retriever", {}).get("implementation")
        retrieved_docs = []
        if retriever_impl:
            impl_path = root / retriever_impl
            if impl_path.exists():
                console.print(
                    f"[yellow]⚠ Executing retriever implementation:[/yellow] {impl_path}\n"
                    "[dim]Retriever files run as Python code. Only load implementations you trust.[/dim]"
                )
                spec = importlib.util.spec_from_file_location("retriever", impl_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                retrieved_docs = module.retrieve(question, top_k=pipeline_def.get("retriever", {}).get("top_k", 5))
        elif context_docs:
            retrieved_docs = context_docs

        # Step 2: Score retrieval relevance
        if retrieved_docs:
            scores["retrieval_relevance"] = _score_retrieval(question, retrieved_docs)

        # Step 3: Run the generator agent
        generator_agent = pipeline_def.get("generator", {}).get("agent")
        generated_answer = ""
        if generator_agent:
            from ryva.runner import run_agent
            gen_input = {
                "question": question,
                "context": "\n".join([
                    d.get("text", d) if isinstance(d, dict) else str(d)
                    for d in retrieved_docs
                ])
            }
            output = run_agent(root, generator_agent, gen_input)
            generated_answer = output.get("answer", output.get("raw_output", str(output)))

        # Step 4: Score faithfulness
        if generated_answer and retrieved_docs:
            scores["faithfulness"] = _score_faithfulness(
                generated_answer, retrieved_docs
            )

        # Step 5: Score answer quality
        if generated_answer and expected_answer:
            scores["answer_quality"] = _score_answer_quality(
                question, generated_answer, expected_answer
            )

        # Step 6: Score context utilization
        if generated_answer and retrieved_docs:
            scores["context_utilization"] = _score_context_utilization(
                generated_answer, retrieved_docs
            )

        # Check thresholds
        failed = []
        if scores["retrieval_relevance"] < retrieval_threshold:
            failed.append(f"retrieval {scores['retrieval_relevance']:.2f}<{retrieval_threshold}")
        if scores["faithfulness"] < faithfulness_threshold:
            failed.append(f"faithfulness {scores['faithfulness']:.2f}<{faithfulness_threshold}")
        if expected_answer and scores["answer_quality"] < answer_threshold:
            failed.append(f"quality {scores['answer_quality']:.2f}<{answer_threshold}")

        passed = len(failed) == 0
        detail = "All checks passed" if passed else f"Failed: {', '.join(failed)}"
        return passed, detail, scores

    except Exception as e:
        return False, str(e)[:80], scores


def _score_retrieval(question: str, docs: list) -> float:
    from ryva.embeddings import batch_similarity
    texts = [
        doc.get("text", str(doc)) if isinstance(doc, dict) else str(doc)
        for doc in docs
    ]
    scores = batch_similarity(question, texts)
    return sum(scores) / len(scores) if scores else 0.0


def _score_faithfulness(answer: str, docs: list) -> float:
    from ryva.embeddings import batch_similarity
    texts = [
        doc.get("text", str(doc)) if isinstance(doc, dict) else str(doc)
        for doc in docs
    ]
    scores = batch_similarity(answer, texts)
    return sum(scores) / len(scores) if scores else 0.0


def _score_answer_quality(question: str, answer: str, expected: str) -> float:
    from ryva.embeddings import semantic_similarity
    return semantic_similarity(answer, expected)


def _score_context_utilization(answer: str, docs: list) -> float:
    answer_lower = answer.lower()
    used = 0
    for doc in docs:
        text = doc.get("text", str(doc)).lower() if isinstance(doc, dict) else str(doc).lower()
        key_phrases = [p for p in text.split(".") if len(p.strip()) > 20]
        for phrase in key_phrases[:3]:
            words = phrase.strip().split()
            if len(words) >= 3:
                trigram = " ".join(words[:3])
                if trigram in answer_lower:
                    used += 1
                    break
    return min(used / max(len(docs), 1), 1.0)


def _print_results(results: list):
    console.print()
    table = Table(
        title="RAG Pipeline Test Results",
        show_header=True,
        header_style="bold"
    )
    table.add_column("Pipeline", style="cyan")
    table.add_column("Test Case")
    table.add_column("Status", justify="center")
    table.add_column("Retrieval", justify="center")
    table.add_column("Faithful", justify="center")
    table.add_column("Quality", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _, _ in results if p)
    total = len(results)

    def score_color(s, passed_case):
        if passed_case and s < 0.7:
            return "yellow"
        if s >= 0.7:
            return "green"
        elif s >= 0.4:
            return "yellow"
        return "red"

    for pipeline, case, p, scores, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        r = scores.get("retrieval_relevance", 0)
        f = scores.get("faithfulness", 0)
        q = scores.get("answer_quality", 0)
        table.add_row(
            pipeline, case, status,
            f"[{score_color(r, p)}]{r:.2f}[/{score_color(r, p)}]",
            f"[{score_color(f, p)}]{f:.2f}[/{score_color(f, p)}]",
            f"[{score_color(q, p)}]{q:.2f}[/{score_color(q, p)}]",
            detail
        )

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} RAG tests passed[/bold {color}]")
