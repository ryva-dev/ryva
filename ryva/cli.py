from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="ryva",
    help="The engineering framework for agentic AI.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()


def _resolve_root(root: Path | None) -> Path:
    """Return root dir; print a friendly message and exit 1 if project.yml is missing."""
    from ryva.utils import find_project_root
    try:
        return root or find_project_root()
    except FileNotFoundError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1)


@app.command()
def init(
    name: str = typer.Argument(..., help="Project name"),
    path: Path | None = typer.Option(None, help="Where to create the project"),
    template: str = typer.Option("default", "--template", help="Project template: default, healthcare"),
):
    """Initialize a new Ryva project."""
    from ryva.init_project import scaffold
    scaffold(name, path or Path.cwd() / name, template=template)


@app.command()
def compile(
    root: Path | None = typer.Option(None, "--root", help="Project root"),
    strict: bool = typer.Option(False, "--strict", help="Error on unknown config keys instead of warning"),
):
    """Compile and validate all agents, tools, and pipelines."""
    from ryva.compiler import compile_project
    r = _resolve_root(root)
    ok = compile_project(r, strict=strict)
    raise typer.Exit(0 if ok else 1)


@app.command()
def dag(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent name (omit for all)"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Show the dependency graph for agents."""
    from ryva.dag import show_dag
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_dag(r, agent)


@app.command()
def run(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent name"),
    pipeline: str | None = typer.Option(None, "--pipeline", "-p", help="Pipeline name"),
    input: str | None = typer.Option(None, "--input", "-i", help="JSON input string"),
    input_file: Path | None = typer.Option(None, "--input-file", "-f", help="Path to a JSON file containing the agent input"),
    input_dir: Path | None = typer.Option(None, "--input-dir", help="Directory of JSON input files — runs the agent against each file"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Run an agent or pipeline locally.

    Examples:
      ryva run --agent my_agent --input '{"text": "hello"}'
      ryva run --agent my_agent --input-file fixtures/input.json
      ryva run --agent my_agent --input-dir fixtures/
    """
    from ryva.pipeline_runner import run_pipeline
    from ryva.runner import run_agent
    r = _resolve_root(root)

    if sum(x is not None for x in [input, input_file, input_dir]) > 1:
        console.print("[red]Specify only one of --input, --input-file, or --input-dir[/red]")
        raise typer.Exit(1)

    if input_dir is not None:
        # Batch mode: run against every JSON file in the directory
        if not input_dir.is_dir():
            console.print(f"[red]--input-dir '{input_dir}' is not a directory[/red]")
            raise typer.Exit(1)
        files = sorted(input_dir.glob("*.json"))
        if not files:
            console.print(f"[red]No JSON files found in '{input_dir}'[/red]")
            raise typer.Exit(1)
        if not agent:
            console.print("[red]--input-dir requires --agent[/red]")
            raise typer.Exit(1)
        passed = 0
        for f in files:
            try:
                batch_input = json.loads(f.read_text())
            except json.JSONDecodeError as e:
                console.print(f"[red]  ✗ {f.name}: invalid JSON — {e}[/red]")
                continue
            console.print(f"[dim]Running against {f.name}...[/dim]")
            try:
                run_agent(r, agent, batch_input)
                passed += 1
                console.print(f"[green]  ✓ {f.name}[/green]")
            except Exception as e:
                console.print(f"[red]  ✗ {f.name}: {e}[/red]")
        color = "green" if passed == len(files) else "yellow"
        console.print(f"\n[bold {color}]{passed}/{len(files)} runs succeeded.[/bold {color}]")
        raise typer.Exit(0 if passed == len(files) else 1)

    if input_file is not None:
        if not input_file.exists():
            console.print(f"[red]--input-file '{input_file}' not found[/red]")
            raise typer.Exit(1)
        try:
            input_data = json.loads(input_file.read_text())
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON in {input_file}: {e}[/red]")
            raise typer.Exit(1)
    else:
        raw = input if input is not None else "{}"
        try:
            input_data = json.loads(raw)
        except json.JSONDecodeError:
            console.print("[red]--input must be valid JSON[/red]")
            raise typer.Exit(1)

    if agent:
        run_agent(r, agent, input_data)
    elif pipeline:
        run_pipeline(r, pipeline, input_data)
    else:
        console.print("[red]Provide --agent or --pipeline[/red]")
        raise typer.Exit(1)

@app.command()
def test(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent name"),
    pipeline: str | None = typer.Option(None, "--pipeline", "-p", help="Pipeline name"),
    model: str | None = typer.Option(None, "--model", "-m", help="ML model name"),
    vector: str | None = typer.Option(None, "--vector", "-v", help="Vector store name"),
    multimodal: str | None = typer.Option(None, "--multimodal", help="Multimodal model name"),
    adversarial: bool = typer.Option(False, "--adversarial", help="Run adversarial tests"),
    hallucination: bool = typer.Option(False, "--hallucination", help="Run hallucination detection"),
    rag: bool = typer.Option(False, "--rag", help="Run RAG pipeline tests"),
    regression: bool = typer.Option(False, "--regression", help="Run regression tests against baseline"),
    memory: bool = typer.Option(False, "--memory", help="Run memory and context retention tests"),
    finetune: bool = typer.Option(False, "--finetune", help="Run fine-tune evaluation tests"),
    categories: str | None = typer.Option(None, "--categories", help="Adversarial categories"),
    fuzz: bool = typer.Option(False, "--fuzz", help="Run fuzzing tests"),
    concurrency: int = typer.Option(10, "--concurrency", "-c", help="Parallel test workers (1-20, default 10)"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Run tests for agents, pipelines, ML models, vector stores, and multimodal models."""
    from ryva.adversarial_tester import run_adversarial_tests
    from ryva.finetune_tester import run_finetune_tests
    from ryva.fuzzer import run_fuzz_tests
    from ryva.hallucination_detector import run_hallucination_tests
    from ryva.memory_tester import run_memory_tests
    from ryva.ml_tester import run_ml_tests
    from ryva.multimodal_tester import run_multimodal_tests
    from ryva.pipeline_tester import run_pipeline_tests
    from ryva.rag_tester import run_rag_tests
    from ryva.regression_tester import run_regression_tests
    from ryva.tester import run_tests
    from ryva.utils import find_project_root
    from ryva.vector_tester import run_vector_tests
    r = root or find_project_root()

    if adversarial:
        cats = categories.split(",") if categories else None
        ok = run_adversarial_tests(r, agent, cats)
    elif hallucination:
        ok = run_hallucination_tests(r, agent)
    elif rag:
        ok = run_rag_tests(r, pipeline)
    elif regression:
        ok = run_regression_tests(r, agent)
    elif memory:
        ok = run_memory_tests(r, agent)
    elif finetune:
        ok = run_finetune_tests(r, agent)
    elif fuzz:
        ok = run_fuzz_tests(r, agent)
    elif pipeline:
        ok = run_pipeline_tests(r, pipeline)
    elif agent:
        ok = run_tests(r, agent, concurrency=concurrency)
    elif model:
        ok = run_ml_tests(r, model)
    elif vector:
        ok = run_vector_tests(r, vector)
    elif multimodal:
        ok = run_multimodal_tests(r, multimodal)
    else:
        agent_ok = run_tests(r, None, concurrency=concurrency)
        pipeline_ok = run_pipeline_tests(r, None)
        ml_ok = run_ml_tests(r, None)
        vector_ok = run_vector_tests(r, None)
        multimodal_ok = run_multimodal_tests(r, None)
        ok = agent_ok and pipeline_ok and ml_ok and vector_ok and multimodal_ok

    raise typer.Exit(0 if ok else 1)


@app.command()
def eval(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent name (omit for all)"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Run LLM-as-judge evals for agents."""
    from ryva.evaluator import run_evals
    from ryva.utils import find_project_root
    r = root or find_project_root()
    ok = run_evals(r, agent)
    raise typer.Exit(0 if ok else 1)


docs_app = typer.Typer(help="Documentation commands.")
app.add_typer(docs_app, name="docs")


@docs_app.command("generate")
def docs_generate(
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Generate markdown documentation for all agents and tools."""
    from ryva.docs import generate_docs
    from ryva.utils import find_project_root
    r = root or find_project_root()
    generate_docs(r)


@docs_app.command("serve")
def docs_serve(
    port: int = typer.Option(8080, "--port", help="Port to serve on"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Serve generated docs locally in your browser."""
    from ryva.docs import serve_docs
    from ryva.utils import find_project_root
    r = root or find_project_root()
    serve_docs(r, port)


list_app = typer.Typer(help="List project resources.")
app.add_typer(list_app, name="list")


@list_app.command("agents")
def list_agents(root: Path | None = typer.Option(None, "--root")):
    """List all agents in the project."""
    from ryva.utils import find_project_root, load_manifest
    r = root or find_project_root()
    m = load_manifest(r)
    for name, a in m.get("agents", {}).items():
        console.print(f"[cyan]{name}[/cyan] [dim]v{a.get('version','?')} — {a.get('description','')}[/dim]")


@list_app.command("tools")
def list_tools(root: Path | None = typer.Option(None, "--root")):
    """List all tools in the project."""
    from ryva.utils import find_project_root, load_manifest
    r = root or find_project_root()
    m = load_manifest(r)
    for name, t in m.get("tools", {}).items():
        console.print(f"[green]{name}[/green] [dim]v{t.get('version','?')} — {t.get('description','')}[/dim]")


@list_app.command("prompts")
def list_prompts(root: Path | None = typer.Option(None, "--root")):
    """List all prompt templates in the project."""
    from ryva.utils import find_project_root
    r = root or find_project_root()
    for p in (r / "prompts").glob("*.j2"):
        console.print(f"[yellow]{p.stem}[/yellow]")


@app.command()
def check(root: Path | None = typer.Option(None, "--root")):
    """Lint and validate the project without writing output."""
    from ryva.resolver import ProjectResolver
    from ryva.utils import find_project_root
    r = root or find_project_root()
    resolver = ProjectResolver(r)
    ok = resolver.resolve()
    if ok:
        console.print("[bold green]✓ No issues found[/bold green]")
    else:
        for err in resolver.errors:
            console.print(f"[red]✗[/red] {err}")
    raise typer.Exit(0 if ok else 1)


@app.command()
def history(
    n: int = typer.Option(10, "--last", help="Number of runs to show"),
    root: Path | None = typer.Option(None, "--root"),
):
    """Show recent run history."""
    from rich.table import Table

    from ryva.utils import find_project_root
    r = root or find_project_root()
    runs_dir = r / "logs" / "runs"
    if not runs_dir.exists():
        console.print("[dim]No runs yet.[/dim]")
        return

    runs = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    table = Table(show_header=True, header_style="bold")
    table.add_column("Run ID", style="dim")
    table.add_column("Agent", style="cyan")
    table.add_column("Timestamp")
    table.add_column("Latency", justify="right")

    for run_path in runs:
        run = json.loads(run_path.read_text())
        table.add_row(
            run.get("run_id", "?"),
            run.get("agent", "?"),
            run.get("timestamp", "?")[:19],
            f"{run.get('elapsed_ms', '?')}ms"
        )
    console.print(table)

@app.command()
def cost(
    month: str | None = typer.Option(None, "--month", "-m", help="Month in YYYY-MM format (default: current)"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Show cost report for agents."""
    from ryva.cost_tracker import show_cost_report
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_cost_report(r, month)

@app.command()
def forecast(
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Show cost forecast and budget projection for the current month."""
    from ryva.cost_tracker import show_forecast
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_forecast(r)

@app.command()
def compare(
    agent: str = typer.Argument(..., help="Agent name to compare"),
    providers: str = typer.Option("anthropic,openai,gemini,ollama", "--providers", "-p", help="Comma separated providers"),
    input: str = typer.Option("{}", "--input", "-i", help="JSON input string"),
    runs: int = typer.Option(3, "--runs", "-n", help="Number of runs per provider"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Compare agent performance across LLM providers."""
    from ryva.comparer import compare_providers
    from ryva.utils import find_project_root
    r = root or find_project_root()

    try:
        input_data = json.loads(input)
    except json.JSONDecodeError:
        console.print("[red]--input must be valid JSON[/red]")
        raise typer.Exit(1)

    provider_list = [p.strip() for p in providers.split(",")]
    compare_providers(r, agent, input_data, provider_list, runs)


@app.command()
def compat(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent name (omit for all)"),
    provider: str = typer.Option("anthropic", "--provider", "-p", help="Provider to test across model tiers"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Test agent compatibility across model sizes to find the cheapest that works."""
    from ryva.compat_tester import run_compat_tests
    from ryva.utils import find_project_root
    r = root or find_project_root()
    ok = run_compat_tests(r, agent, provider)
    raise typer.Exit(0 if ok else 1)

@app.command()
def baseline(
    agent: str = typer.Argument(..., help="Agent name to baseline"),
    label: str | None = typer.Option(None, "--label", "-l", help="Baseline label"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Create a baseline snapshot of agent outputs for regression testing."""
    from ryva.regression_tester import create_baseline
    from ryva.utils import find_project_root
    r = root or find_project_root()
    create_baseline(r, agent, label)

registry_app = typer.Typer(help="Manage the model registry.")
app.add_typer(registry_app, name="registry")


@registry_app.command("list")
def registry_list_cmd(root: Path = typer.Option(None, "--root", help="Project root")):
    """List all registered models."""
    from ryva.registry import registry_list
    from ryva.utils import find_project_root
    r = root or find_project_root()
    registry_list(r)


@registry_app.command("add")
def registry_add_cmd(
    name: str = typer.Argument(..., help="Alias for the model"),
    provider: str = typer.Option(..., "--provider", help="Provider name (anthropic, openai, etc)"),
    model_id: str = typer.Option(..., "--model-id", help="Model ID string"),
    version: str = typer.Option("1.0.0", "--version", help="Version tag"),
    tags: str = typer.Option("", "--tags", help="Comma-separated tags"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Register a new model."""
    from ryva.registry import registry_add
    from ryva.utils import find_project_root
    r = root or find_project_root()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    registry_add(r, name, provider, model_id, version, tag_list)


@registry_app.command("info")
def registry_info_cmd(
    name: str = typer.Argument(..., help="Model alias"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show details for a registered model."""
    from ryva.registry import registry_info
    from ryva.utils import find_project_root
    r = root or find_project_root()
    registry_info(r, name)


@registry_app.command("remove")
def registry_remove_cmd(
    name: str = typer.Argument(..., help="Model alias to remove"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Remove a model from the registry."""
    from ryva.registry import registry_remove
    from ryva.utils import find_project_root
    r = root or find_project_root()
    registry_remove(r, name)

traces_app = typer.Typer(help="Inspect agent run traces.")
app.add_typer(traces_app, name="traces")


@traces_app.command("list")
def traces_list_cmd(root: Path = typer.Option(None, "--root", help="Project root")):
    """List all recorded traces."""
    from ryva.tracer import traces_list
    from ryva.utils import find_project_root
    r = root or find_project_root()
    traces_list(r)


@traces_app.command("show")
def traces_show_cmd(
    run_id: str = typer.Argument(..., help="Run ID to inspect"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show full detail for a trace."""
    from ryva.tracer import traces_show
    from ryva.utils import find_project_root
    r = root or find_project_root()
    traces_show(r, run_id)

@app.command()
def benchmark(
    name: str = typer.Argument(None, help="Benchmark to run (summarization, qa, classification, coding)"),
    model: str = typer.Option(None, "--model", help="Model to benchmark"),
    provider: str = typer.Option(None, "--provider", help="Provider to use"),
    list_all: bool = typer.Option(False, "--list", help="List available benchmarks"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Run standard benchmarks against your model."""
    from ryva.benchmarker import list_benchmarks, run_benchmark
    from ryva.utils import find_project_root
    if list_all:
        list_benchmarks()
        return
    r = root or find_project_root()
    run_benchmark(r, name, model, provider)


@app.command()
def diff(
    run_a: str = typer.Argument(..., help="First run ID"),
    run_b: str = typer.Argument(..., help="Second run ID"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Compare two runs side by side — prompt hash, output hash, tokens, cost."""
    from ryva.lineage import show_diff
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_diff(r, run_a, run_b)


lineage_app = typer.Typer(help="Query AI decision lineage and audit trails.")
app.add_typer(lineage_app, name="lineage")


@lineage_app.command("show")
def lineage_show_cmd(
    run_id: str = typer.Argument(..., help="Run ID to reconstruct"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show the full lineage chain for a run, including multi-agent parent calls."""
    from ryva.lineage import show_chain
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_chain(r, run_id)


@lineage_app.command("search")
def lineage_search_cmd(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filter by agent name"),
    since: str | None = typer.Option(None, "--since", help="ISO date, e.g. 2026-05-01"),
    status: str | None = typer.Option(None, "--status", help="Filter: success or error"),
    limit: int = typer.Option(20, "--limit", help="Max results"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Search lineage records with optional filters."""
    from ryva.lineage import show_search
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_search(r, agent, since, status, limit)


@lineage_app.command("verify")
def lineage_verify_cmd(
    run_id: str | None = typer.Argument(None, help="Run ID to verify (omit to verify all)"),
    all_records: bool = typer.Option(False, "--all", help="Verify all lineage records"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Verify HMAC-SHA256 signatures on lineage records to detect tampering."""
    from ryva.lineage import show_verify
    from ryva.utils import find_project_root
    r = root or find_project_root()
    ids = [] if (all_records or run_id is None) else [run_id]
    if run_id and not all_records:
        ids = [run_id]
    ok = show_verify(r, ids)
    raise typer.Exit(0 if ok else 1)


@lineage_app.command("export")
def lineage_export_cmd(
    run_id: str = typer.Argument(..., help="Run ID to export"),
    out: Path | None = typer.Option(None, "--out", "-o", help="Output file (default: stdout)"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Export full lineage chain as structured JSON for compliance or audit."""
    from ryva.lineage import export_compliance
    from ryva.utils import find_project_root
    r = root or find_project_root()
    data = export_compliance(r, run_id)
    if not data:
        console.print(f"[red]No lineage data found for run '{run_id}'.[/red]")
        raise typer.Exit(1)
    text = json.dumps(data, indent=2)
    if out:
        out.write_text(text)
        console.print(f"[green]✓ Exported to {out}[/green]")
    else:
        console.print(text)


@app.command()
def align(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Agent name (omit for all)"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Check agent outputs against alignment policies defined in project.yml."""
    from ryva.alignment import run_alignment_checks
    from ryva.utils import find_project_root
    r = root or find_project_root()
    ok = run_alignment_checks(r, agent)
    raise typer.Exit(0 if ok else 1)


governance_app = typer.Typer(help="AI governance and compliance reporting.")
app.add_typer(governance_app, name="governance")


@governance_app.command("report")
def governance_report_cmd(
    out: Path | None = typer.Option(None, "--out", "-o", help="Save full JSON report to extra file"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Generate a governance report: risk scores, EU AI Act checklist, AI bill of materials.

    Exit codes: 0=all clear, 1=high-risk (tested), 2=high-risk untested (critical).
    Always writes target/governance_report.json and target/governance_report.md.
    """
    from ryva.governance import show_report
    from ryva.utils import find_project_root
    r = root or find_project_root()
    exit_code = show_report(r, out)
    raise typer.Exit(exit_code)


feedback_app = typer.Typer(help="Record and review outcome feedback for AI runs.")
app.add_typer(feedback_app, name="feedback")


@feedback_app.command("record")
def feedback_record_cmd(
    run_id: str = typer.Option(..., "--run-id", "-r", help="Run ID to annotate"),
    outcome: str = typer.Option(..., "--outcome", "-o", help="correct / incorrect / partial / unknown"),
    note: str = typer.Option("", "--note", "-n", help="Optional note"),
    annotator: str = typer.Option("", "--annotator", help="Who is recording this"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Record an outcome annotation for a completed agent run."""
    from ryva.feedback import record_feedback
    from ryva.utils import find_project_root
    r = root or find_project_root()
    record_feedback(r, run_id, outcome, note=note, annotator=annotator)


@feedback_app.command("report")
def feedback_report_cmd(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filter by agent name"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show outcome feedback summary and accuracy metrics."""
    from ryva.feedback import show_feedback_report
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_feedback_report(r, agent)


vision_app = typer.Typer(help="Vision model inference and annotation lineage.")
app.add_typer(vision_app, name="vision")

vision_lineage_app = typer.Typer(help="Vision lineage subcommands.")
vision_app.add_typer(vision_lineage_app, name="lineage")


@vision_lineage_app.command("show")
def vision_lineage_show_cmd(
    image_hash: str = typer.Argument(..., help="Image SHA-256 hash"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show all inference and annotation records for an image hash."""
    from ryva.utils import find_project_root
    from ryva.vision_lineage import show_lineage
    r = root or find_project_root()
    show_lineage(r, image_hash)


@vision_lineage_app.command("report")
def vision_lineage_report_cmd(
    out: Path | None = typer.Option(None, "--out", "-o", help="Save JSON report to file"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Generate a vision lineage summary report."""
    from ryva.utils import find_project_root
    from ryva.vision_lineage import show_vision_report
    r = root or find_project_root()
    show_vision_report(r, out)


retrain_app = typer.Typer(help="Model drift monitoring and retraining triggers.")
app.add_typer(retrain_app, name="retrain")


@retrain_app.command("trigger")
def retrain_trigger_cmd(
    agent: str = typer.Argument(..., help="Agent name to retrain"),
    trigger: str = typer.Option("manual", "--trigger", "-t",
                                help="Trigger type: manual, drift, feedback, scheduled"),
    reason: str = typer.Option("", "--reason", "-r", help="Reason for retraining"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Record a retraining trigger event for an agent."""
    from ryva.retrainer import trigger_retraining
    from ryva.utils import find_project_root
    r = root or find_project_root()
    trigger_retraining(r, agent, trigger=trigger, reason=reason)


@retrain_app.command("history")
def retrain_history_cmd(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filter by agent name"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show retraining job history."""
    from ryva.retrainer import show_history
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_history(r, agent)


@retrain_app.command("drift")
def retrain_drift_cmd(
    agent: str = typer.Argument(..., help="Agent name to analyse"),
    threshold: float = typer.Option(0.15, "--threshold", help="Drift threshold (default 0.15)"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Analyse quality score drift for an agent."""
    from ryva.retrainer import show_drift
    from ryva.utils import find_project_root
    r = root or find_project_root()
    result = show_drift(r, agent, threshold=threshold)
    raise typer.Exit(1 if result["drifted"] else 0)


edge_app = typer.Typer(help="Edge device telemetry and inference monitoring.")
app.add_typer(edge_app, name="edge")


@edge_app.command("status")
def edge_status_cmd(
    device: str | None = typer.Option(None, "--device", "-d", help="Device ID (omit for all)"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show edge telemetry status for a device or all devices."""
    from ryva.edge import show_status
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_status(r, device)


@edge_app.command("flush")
def edge_flush_cmd(
    device: str = typer.Argument(..., help="Device ID to flush"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Flush (delete) locally cached telemetry for a device after upload."""
    from ryva.edge import flush_device
    from ryva.utils import find_project_root
    r = root or find_project_root()
    flush_device(r, device)


@edge_app.command("report")
def edge_report_cmd(
    out: Path | None = typer.Option(None, "--out", "-o", help="Save JSON report to file"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Generate an aggregate edge fleet telemetry report."""
    from ryva.edge import show_report as edge_show_report
    from ryva.utils import find_project_root
    r = root or find_project_root()
    edge_show_report(r, out)


approvals_app = typer.Typer(help="Manage compliance approvals for AI systems.")
app.add_typer(approvals_app, name="approvals")


@approvals_app.command("list")
def approvals_list(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filter by agent name"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """List all compliance approval requests for this project."""
    r = _resolve_root(root)
    approvals_dir = r / "target" / "approvals"
    if not approvals_dir.exists():
        console.print("[dim]No approvals recorded yet. Use 'ryva approvals request' to create one.[/dim]")
        return
    files = sorted(approvals_dir.glob("*.json"))
    if not files:
        console.print("[dim]No approvals found.[/dim]")
        return
    for f in files:
        data = json.loads(f.read_text())
        if agent and data.get("agent") != agent:
            continue
        status = data.get("status", "pending")
        color = "green" if status == "approved" else "red" if status == "rejected" else "yellow"
        console.print(
            f"  [{color}]{status.upper()}[/{color}]"
            f" [{data.get('step', '?')}]"
            f" {data.get('agent', '?')} —"
            f" {data.get('reviewer_name', 'Unassigned')}"
            f" ({(data.get('created_at') or '')[:10]})"
        )


@approvals_app.command("request")
def approvals_request(
    agent: str = typer.Option(..., "--agent", "-a", help="Agent name"),
    step: str = typer.Option(
        ..., "--step", "-s",
        help="Approval step: technical, privacy, compliance, legal",
    ),
    reviewer: str = typer.Option(..., "--reviewer", help="Reviewer name"),
    reviewer_email: str = typer.Option(..., "--reviewer-email", help="Reviewer email"),
    notes: str = typer.Option("", "--notes", help="Notes for the reviewer"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Create a compliance approval request for an AI system."""
    import uuid
    from datetime import UTC, datetime

    valid_steps = {"technical", "privacy", "compliance", "legal"}
    if step not in valid_steps:
        console.print(f"[red]--step must be one of: {', '.join(sorted(valid_steps))}[/red]")
        raise typer.Exit(1)

    r = _resolve_root(root)
    approvals_dir = r / "target" / "approvals"
    approvals_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {}
    manifest_path = r / "target" / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass

    approval_id = str(uuid.uuid4())[:8]
    approval = {
        "id": approval_id,
        "agent": agent,
        "step": step,
        "status": "pending",
        "reviewer_name": reviewer,
        "reviewer_email": reviewer_email,
        "notes": notes,
        "prompt_hash": manifest.get("agents", {}).get(agent, {}).get("prompt_hash"),
        "approved_model": manifest.get("agents", {}).get(agent, {}).get("model"),
        "approved_provider": manifest.get("agents", {}).get(agent, {}).get("provider"),
        "reviewed_version_id": None,
        "manifest_version": manifest.get("ryva_version"),
        "created_at": datetime.now(UTC).isoformat(),
        "approved_at": None,
        "approved_by": None,
    }
    if approval.get("prompt_hash") or approval.get("approved_model") or approval.get("approved_provider"):
        import hashlib
        raw = "|".join([
            "",
            agent,
            approval.get("prompt_hash") or "",
            approval.get("approved_model") or "",
            approval.get("approved_provider") or "",
        ])
        approval["reviewed_version_id"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    (approvals_dir / f"{approval_id}.json").write_text(json.dumps(approval, indent=2))

    console.print(f"[bold green]✓ Approval request created: {approval_id}[/bold green]")
    console.print(f"  Agent:    {agent}")
    console.print(f"  Step:     {step}")
    console.print(f"  Reviewer: {reviewer} <{reviewer_email}>")
    console.print(f"  Prompt hash: {approval.get('prompt_hash') or 'unknown'}")


@approvals_app.command("record")
def approvals_record(
    approval_id: str = typer.Option(..., "--id", help="Approval ID"),
    approved_by: str = typer.Option(..., "--approved-by", help="Name of approver"),
    notes: str = typer.Option("", "--notes", help="Approval notes"),
    reject: bool = typer.Option(False, "--reject", help="Reject instead of approve"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Record an approval or rejection decision."""
    from datetime import UTC, datetime

    r = _resolve_root(root)
    filepath = r / "target" / "approvals" / f"{approval_id}.json"
    if not filepath.exists():
        console.print(f"[red]Approval '{approval_id}' not found.[/red]")
        raise typer.Exit(1)

    approval = json.loads(filepath.read_text())
    approval["status"] = "rejected" if reject else "approved"
    approval["approved_by"] = approved_by
    approval["approved_at"] = datetime.now(UTC).isoformat()
    approval["approval_notes"] = notes
    filepath.write_text(json.dumps(approval, indent=2))

    action = "rejected" if reject else "approved"
    color = "red" if reject else "green"
    console.print(f"[bold {color}]✓ Approval {action}: {approval_id}[/bold {color}]")


@app.command()
def changes(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filter by agent name"),
    requires_review: bool = typer.Option(False, "--requires-review", help="Show only items needing review"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Show change history recorded during compile."""
    r = _resolve_root(root)
    history_file = r / "target" / "change_history.json"
    if not history_file.exists():
        console.print("[dim]No change history yet — run 'ryva compile' to start tracking.[/dim]")
        return

    all_changes = json.loads(history_file.read_text())
    if agent:
        all_changes = [c for c in all_changes if c.get("agent") == agent]
    if requires_review:
        all_changes = [c for c in all_changes if c.get("requires_review")]
    if not all_changes:
        console.print("[dim]No changes found.[/dim]")
        return

    for c in sorted(all_changes, key=lambda x: x.get("timestamp", ""), reverse=True):
        severity = c.get("severity", "info")
        color = "red" if severity == "high" else "yellow" if severity == "low" else "blue"
        review_flag = "  [bold red]⚠ REVIEW REQUIRED[/bold red]" if c.get("requires_review") else ""
        console.print(f"  [{color}]{c.get('type', '?')}[/{color}]{review_flag}")
        console.print(f"  {c.get('description')}")
        console.print(f"  [dim]{(c.get('timestamp') or '')[:19]}[/dim]")
        if c.get("compliance_note"):
            console.print(f"  [yellow]Note: {c['compliance_note']}[/yellow]")
        console.print()


ci_app = typer.Typer(help="CI/CD integration helpers.")
app.add_typer(ci_app, name="ci")


@ci_app.command("setup")
def ci_setup(
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Create .github/workflows/ryva-governance.yml in this project."""
    from pathlib import Path as _Path

    r = _resolve_root(root)
    workflows_dir = r / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    target = workflows_dir / "ryva-governance.yml"

    template_path = _Path(__file__).parent / "templates" / "github_actions.yml"
    if target.exists():
        console.print("[yellow]ryva-governance.yml already exists — skipping.[/yellow]")
    else:
        target.write_text(template_path.read_text())
        console.print("[bold green]✓ Created .github/workflows/ryva-governance.yml[/bold green]")

    console.print("\n[dim]Add these secrets to your GitHub repository settings:[/dim]")
    console.print("  ANTHROPIC_API_KEY  — your Anthropic API key")
    console.print("  RYVA_API_KEY       — Ryva Cloud API key (if using cloud sync)")
    console.print("  RYVA_PROJECT_ID    — Ryva Cloud project ID (if using cloud sync)")


@app.command()
def status(
    env: str = typer.Option("staging", "--env", help="Environment to check: dev, staging, production"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Show release gate status for the current environment."""
    from ryva.release_gates import check_release_gates
    r = _resolve_root(root)

    console.print(f"[bold]Checking release gates for: {env.upper()}[/bold]\n")
    result = check_release_gates(env=env, root=r)

    if result.passed:
        console.print(f"[bold green]✓ All gates passed — ready to sync to {env}[/bold green]")
    else:
        console.print(
            f"[bold red]✗ {len(result.failures)} gate(s) blocking {env} sync:[/bold red]"
        )
        for f in result.failures:
            console.print(f"  • {f}")

    if result.warnings:
        console.print()
        console.print("[yellow]Warnings:[/yellow]")
        for w in result.warnings:
            console.print(f"  ⚠ {w}")

    if result.agents_checked:
        console.print()
        console.print(f"[dim]Agents checked: {', '.join(result.agents_checked)}[/dim]")

    raise typer.Exit(0 if result.passed else 1)


exceptions_app = typer.Typer(help="Manage policy exceptions and risk waivers.")
app.add_typer(exceptions_app, name="exceptions")


@exceptions_app.command("create")
def exceptions_create(
    agent: str = typer.Option(..., "--agent", "-a", help="Agent name"),
    policy: str = typer.Option(..., "--policy", help="Policy name being excepted"),
    reason: str = typer.Option(..., "--reason", help="Business justification"),
    approved_by: str = typer.Option(..., "--approved-by", help="Name of approver"),
    expires: str = typer.Option(..., "--expires", help="Expiry date YYYY-MM-DD"),
    risk_level: str = typer.Option("medium", "--risk-level", help="Risk level: low, medium, high"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Create a formal policy exception with expiry date."""
    import hashlib
    import uuid
    from datetime import UTC, datetime

    valid_levels = {"low", "medium", "high"}
    if risk_level not in valid_levels:
        console.print(f"[red]--risk-level must be one of: {', '.join(sorted(valid_levels))}[/red]")
        raise typer.Exit(1)

    r = _resolve_root(root)
    target_dir = r / "target"
    target_dir.mkdir(exist_ok=True)
    manifest: dict = {}
    manifest_path = r / "target" / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass

    exceptions_file = target_dir / "exceptions.json"
    existing: list = []
    if exceptions_file.exists():
        try:
            existing = json.loads(exceptions_file.read_text())
        except Exception:
            pass

    exception_id = str(uuid.uuid4())[:8]
    exception = {
        "id": exception_id,
        "agent": agent,
        "policy": policy,
        "reason": reason,
        "approved_by": approved_by,
        "risk_level": risk_level,
        "prompt_hash": manifest.get("agents", {}).get(agent, {}).get("prompt_hash"),
        "approved_model": manifest.get("agents", {}).get(agent, {}).get("model"),
        "approved_provider": manifest.get("agents", {}).get(agent, {}).get("provider"),
        "reviewed_version_id": None,
        "expires_at": f"{expires}T23:59:59Z",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "active",
    }
    if exception.get("prompt_hash") or exception.get("approved_model") or exception.get("approved_provider"):
        raw = "|".join([
            agent,
            exception.get("prompt_hash") or "",
            exception.get("approved_model") or "",
            exception.get("approved_provider") or "",
        ])
        exception["reviewed_version_id"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    existing.append(exception)
    exceptions_file.write_text(json.dumps(existing, indent=2))

    console.print(f"[bold green]✓ Exception created: {exception_id}[/bold green]")
    console.print(f"  Agent:       {agent}")
    console.print(f"  Policy:      {policy}")
    console.print(f"  Approved by: {approved_by}")
    console.print(f"  Expires:     {expires}")
    console.print("[yellow]  ⚠ This exception will appear in your audit package.[/yellow]")


@exceptions_app.command("list")
def exceptions_list(
    agent: str | None = typer.Option(None, "--agent", "-a", help="Filter by agent name"),
    include_expired: bool = typer.Option(False, "--include-expired", help="Show expired exceptions too"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """List all policy exceptions."""
    from datetime import UTC, datetime

    r = _resolve_root(root)
    exceptions_file = r / "target" / "exceptions.json"

    if not exceptions_file.exists():
        console.print("[dim]No exceptions recorded.[/dim]")
        return

    try:
        exceptions = json.loads(exceptions_file.read_text())
    except Exception:
        console.print("[red]Could not read exceptions file.[/red]")
        raise typer.Exit(1)

    now = datetime.now(UTC).isoformat()
    shown = 0
    for exc in exceptions:
        if agent and exc.get("agent") != agent:
            continue
        expired = exc.get("expires_at", "") < now
        if expired and not include_expired:
            continue
        status = "EXPIRED" if expired else "ACTIVE"
        color = "red" if expired else "yellow"
        console.print(
            f"  [{color}]{status}[/{color}]"
            f" [{exc.get('id')}] {exc.get('agent')} — {exc.get('policy')}"
        )
        console.print(f"  Reason: {exc.get('reason')}")
        console.print(f"  Approved by: {exc.get('approved_by')}")
        console.print(f"  Expires: {(exc.get('expires_at') or '')[:10]}")
        console.print()
        shown += 1

    if shown == 0:
        console.print("[dim]No exceptions found.[/dim]")


# ── Cloud commands ────────────────────────────────────────────────────────────

cloud_app = typer.Typer(help="Connect and sync to Ryva Cloud.")
app.add_typer(cloud_app, name="cloud")
cloud_external_app = typer.Typer(help="Scriptable external-system connector helpers.")
cloud_app.add_typer(cloud_external_app, name="external")


@cloud_app.command("login")
def cloud_login_cmd(
    email: str = typer.Option(..., "--email", "-e", prompt=True, help="Your Ryva Cloud email"),
    password: str = typer.Option(..., "--password", "-p", prompt=True, hide_input=True, help="Your Ryva Cloud password"),
    project_id: str = typer.Option(..., "--project-id", prompt=True, help="Your Ryva Cloud project ID"),
):
    """Log in to Ryva Cloud and save credentials locally."""
    from ryva.cloud_sync import cloud_login, save_token
    try:
        result = cloud_login(email, password)
        token = result.get("access_token")
        if not token:
            console.print("[red]Login failed. Check your email and password.[/red]")
            raise typer.Exit(1)
        save_token(token, project_id)
        console.print(f"[green]✓ Logged in as {email}[/green]")
        console.print(f"[green]✓ Project ID: {project_id}[/green]")
    except Exception as e:
        console.print(f"[red]Login failed: {e}[/red]")
        raise typer.Exit(1)


@cloud_app.command("sync")
def cloud_sync_cmd(
    root: Path = typer.Option(None, "--root", help="Project root"),
    env: str = typer.Option("dev", "--env", help="Target environment: dev, staging, production"),
    require_approvals: bool = typer.Option(
        False, "--require-approvals",
        help="Block sync if required approvals are missing or stale.",
    ),
):
    """Sync traces, lineage, compliance reports, and model cards to Ryva Cloud."""
    import json
    import os

    import httpx

    from ryva.cloud_sync import get_project_id, get_token
    from ryva.utils import find_project_root

    r = root or find_project_root()

    # Production always enforces gates
    if env == "production":
        require_approvals = True

    if require_approvals:
        from ryva.release_gates import check_release_gates
        gate = check_release_gates(env=env, root=r)
        if not gate.passed:
            console.print(
                f"[bold red]✗ Sync blocked — release gates failed for {env}:[/bold red]"
            )
            for failure in gate.failures:
                console.print(f"  • {failure}")
            console.print()
            console.print(
                "[dim]Resolve these issues or use --env dev to sync without gates.[/dim]"
            )
            raise typer.Exit(1)
        if gate.warnings:
            for w in gate.warnings:
                console.print(f"[yellow]  ⚠ {w}[/yellow]")

    token = get_token(r)
    project_id = get_project_id(r)

    if not token or not project_id:
        console.print("[red]Not logged in. Run: ryva cloud login[/red]")
        raise typer.Exit(1)

    CLOUD_URL = os.environ.get("RYVA_CLOUD_URL", "https://ryva-cloud-production.up.railway.app")
    headers = {"Authorization": f"Bearer {token}"}

    console.print(f"[bold]Syncing to Ryva Cloud ({env})...[/bold]")

    # Sync traces — map the local trace format onto the backend CreateTraceRequest
    # schema. The local format stores cost as `cost_usd` and tokens nested under
    # `tokens`; the backend expects flat `estimated_cost` / `input_tokens` /
    # `output_tokens`. Missing values are sent as null rather than faked.
    traces_dir = r / "traces"
    if traces_dir.exists():
        trace_files = list(traces_dir.glob("*.json"))
        synced = 0
        for tf in trace_files:
            try:
                trace = json.loads(tf.read_text())
                tokens = trace.get("tokens") or {}
                payload = {
                    "run_id": trace.get("run_id"),
                    "project_id": project_id,
                    "agent": trace.get("agent"),
                    "model": trace.get("model"),
                    "provider": trace.get("provider"),
                    "status": trace.get("status"),
                    "duration_ms": trace.get("duration_ms"),
                    "steps": trace.get("steps", []),
                    "input_tokens": tokens.get("input"),
                    "output_tokens": tokens.get("output"),
                    "estimated_cost": trace.get("cost_usd"),
                    "started_at": trace.get("started_at"),
                    "finished_at": trace.get("finished_at"),
                }
                resp = httpx.post(
                    f"{CLOUD_URL}/api/v1/traces/",
                    json=payload,
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    synced += 1
                else:
                    console.print(
                        f"  [yellow]⚠ Trace {payload['run_id']}: "
                        f"{resp.status_code} {resp.text[:120]}[/yellow]"
                    )
            except Exception as e:
                console.print(f"  [yellow]⚠ Trace {tf.name}: {e}[/yellow]")
        console.print(f"  [green]✓ Synced {synced}/{len(trace_files)} traces[/green]")

    # Sync lineage — preserve prompt/input/output hashes and signed chain data so
    # Cloud can build version history and audit trails from real execution evidence.
    lineage_dir = r / "lineage"
    if lineage_dir.exists():
        lineage_files = list(lineage_dir.glob("*.json"))
        synced = 0
        for lf in lineage_files:
            try:
                record = json.loads(lf.read_text())
                tokens = record.get("tokens") or {}
                payload = {
                    "run_id": record.get("run_id"),
                    "project_id": project_id,
                    "agent": record.get("agent"),
                    "input_hash": record.get("input_hash"),
                    "prompt_hash": record.get("prompt_hash"),
                    "output_hash": record.get("output_hash"),
                    "prompt_template": record.get("prompt_template"),
                    "input_tokens": tokens.get("input"),
                    "output_tokens": tokens.get("output"),
                    "cost_usd": record.get("cost_usd"),
                    "parent_run_id": record.get("parent_run_id"),
                    "trace_id": record.get("trace_id"),
                    "retrieval_chunks": record.get("retrieval_chunks", []),
                    "tool_calls": record.get("tool_calls", []),
                    "signature": record.get("signature"),
                    "signature_verified": record.get("signature_verified", False),
                    "chain_depth": record.get("chain_depth", 1),
                }
                resp = httpx.post(
                    f"{CLOUD_URL}/api/v1/lineage/",
                    json=payload,
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    synced += 1
                else:
                    console.print(
                        f"  [yellow]⚠ Lineage {payload['run_id']}: "
                        f"{resp.status_code} {resp.text[:120]}[/yellow]"
                    )
            except Exception as e:
                console.print(f"  [yellow]⚠ Lineage {lf.name}: {e}[/yellow]")
        console.print(f"  [green]✓ Synced {synced}/{len(lineage_files)} lineage record(s)[/green]")

    # Sync governance / compliance report — map onto CreateComplianceReportRequest.
    # project_name is required by the backend; the local report stores it under
    # `project`. The full report is preserved under `raw_report`.
    gov_report = r / "target" / "governance_report.json"
    if gov_report.exists():
        try:
            report = json.loads(gov_report.read_text())
            summary = report.get("summary") or {}
            overall_score = None
            eu_score = summary.get("eu_ai_act_compliance_score")
            if isinstance(eu_score, str) and "/" in eu_score:
                try:
                    passed, total = eu_score.split("/", 1)
                    total_value = float(total)
                    if total_value > 0:
                        overall_score = round((float(passed) / total_value) * 100, 2)
                except (TypeError, ValueError):
                    overall_score = None
            payload = {
                "project_id": project_id,
                "project_name": report.get("project") or r.name,
                "ryva_version": report.get("ryva_version"),
                "overall_score": overall_score,
                "overall_status": None,
                "eu_ai_act": report.get("eu_ai_act") or {},
                "colorado_ai_act": report.get("colorado_ai_act") or {},
                "risk_summary": report.get("risk_assessment"),
                "ai_bill_of_materials": report.get("bill_of_materials") or [],
                "metrics": summary,
                "prompt_version_registry": report.get("prompt_version_registry") or {},
                "raw_report": report,
            }
            resp = httpx.post(
                f"{CLOUD_URL}/api/v1/compliance/report",
                json=payload,
                headers=headers,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                console.print("  [green]✓ Synced governance report[/green]")
            else:
                console.print(
                    f"  [yellow]⚠ Governance report: "
                    f"{resp.status_code} {resp.text[:160]}[/yellow]"
                )
        except Exception as e:
            console.print(f"  [yellow]⚠ Could not sync governance report: {e}[/yellow]")

    # Sync model cards — flatten the nested local card onto CreateModelCardRequest.
    # The full card is preserved under `raw_card`; every flat column is mapped from
    # its nested source, sending null when a value is absent (never a fake default).
    model_cards_dir = r / "target" / "model_cards"
    if model_cards_dir.exists():
        card_files = list(model_cards_dir.glob("*.json"))
        synced = 0
        for cf in card_files:
            try:
                card = json.loads(cf.read_text())
                system = card.get("system") or {}
                model = card.get("model") or {}
                perf = card.get("performance") or {}
                risk = card.get("risk") or {}
                compliance = card.get("compliance") or {}
                gdpr = compliance.get("gdpr") or {}
                payload = {
                    "project_id": project_id,
                    "agent_name": system.get("name"),
                    "risk_level": risk.get("risk_level"),
                    "risk_justification": risk.get("risk_justification"),
                    "model_id": model.get("model_id"),
                    "provider": model.get("provider"),
                    "intended_use": system.get("intended_use"),
                    "known_limitations": risk.get("known_limitations"),
                    "eu_ai_act_status": compliance.get("eu_ai_act"),
                    "colorado_ai_act_status": compliance.get("colorado_ai_act"),
                    "pii_masking_enabled": gdpr.get("pii_masking_enabled"),
                    "test_coverage": perf.get("test_coverage"),
                    "adversarial_tested": perf.get("adversarial_tested"),
                    "hallucination_tested": perf.get("hallucination_tested"),
                    "total_production_runs": perf.get("total_production_runs"),
                    "raw_card": card,
                }
                resp = httpx.post(
                    f"{CLOUD_URL}/api/v1/compliance/model-cards",
                    json=payload,
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    synced += 1
                else:
                    console.print(
                        f"  [yellow]⚠ Model card {payload.get('agent_name')}: "
                        f"{resp.status_code} {resp.text[:160]}[/yellow]"
                    )
            except Exception as e:
                console.print(f"  [yellow]⚠ Model card {cf.name}: {e}[/yellow]")
        console.print(f"  [green]✓ Synced {synced}/{len(card_files)} model card(s)[/green]")

    manifest_path = r / "target" / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
            manifest["compiled_at"] = datetime.now(timezone.utc).isoformat()
            resp = httpx.post(
                f"{CLOUD_URL}/api/v1/governance/manifest",
                json={"project_id": project_id, "manifest": manifest},
                headers=headers,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                console.print("  [green]✓ Synced manifest snapshot[/green]")
            else:
                console.print(
                    f"  [yellow]⚠ Manifest: "
                    f"{resp.status_code} {resp.text[:160]}[/yellow]"
                )
        except Exception as e:
            console.print(f"  [yellow]⚠ Could not sync manifest: {e}[/yellow]")

    approvals_dir = r / "target" / "approvals"
    if approvals_dir.exists():
        try:
            approvals = []
            for af in sorted(approvals_dir.glob("*.json")):
                approval = json.loads(af.read_text())
                approvals.append(approval)
            if approvals:
                resp = httpx.post(
                    f"{CLOUD_URL}/api/v1/governance/approvals/bulk",
                    json={"project_id": project_id, "approvals": approvals},
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    console.print(f"  [green]✓ Synced {len(approvals)} approval record(s)[/green]")
                else:
                    console.print(
                        f"  [yellow]⚠ Approvals: "
                        f"{resp.status_code} {resp.text[:160]}[/yellow]"
                    )
        except Exception as e:
            console.print(f"  [yellow]⚠ Could not sync approvals: {e}[/yellow]")

    change_history = r / "target" / "change_history.json"
    if change_history.exists():
        try:
            changes = json.loads(change_history.read_text())
            if changes:
                resp = httpx.post(
                    f"{CLOUD_URL}/api/v1/governance/changes/bulk",
                    json={"project_id": project_id, "changes": changes},
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    console.print(f"  [green]✓ Synced {len(changes)} change event(s)[/green]")
                else:
                    console.print(
                        f"  [yellow]⚠ Change history: "
                        f"{resp.status_code} {resp.text[:160]}[/yellow]"
                    )
        except Exception as e:
            console.print(f"  [yellow]⚠ Could not sync change history: {e}[/yellow]")

    exceptions_file = r / "target" / "exceptions.json"
    if exceptions_file.exists():
        try:
            exceptions = json.loads(exceptions_file.read_text())
            if exceptions:
                resp = httpx.post(
                    f"{CLOUD_URL}/api/v1/release/exceptions/bulk",
                    json={"project_id": project_id, "exceptions": exceptions},
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code in (200, 201):
                    console.print(f"  [green]✓ Synced {len(exceptions)} exception record(s)[/green]")
                else:
                    console.print(
                        f"  [yellow]⚠ Exceptions: "
                        f"{resp.status_code} {resp.text[:160]}[/yellow]"
                    )
        except Exception as e:
            console.print(f"  [yellow]⚠ Could not sync exceptions: {e}[/yellow]")

    console.print("\n[bold green]✓ Sync complete[/bold green]")
    console.print("  View at: https://ryva-dashboard.vercel.app/dashboard")


@cloud_app.command("status")
def cloud_status_cmd(
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show cloud connection status."""
    from ryva.cloud_sync import get_project_id, get_token
    from ryva.utils import find_project_root

    r = root or find_project_root()
    token = get_token(r)
    project_id = get_project_id(r)

    if token and project_id:
        console.print("[green]✓ Connected to Ryva Cloud[/green]")
        console.print(f"  Project ID: {project_id}")
    else:
        console.print("[yellow]Not connected. Run: ryva cloud login[/yellow]")


def _resolve_cloud_project_id(root: Path | None, project_id: str | None) -> str:
    if project_id:
        return project_id
    env_project = os.environ.get("RYVA_PROJECT_ID")
    if env_project:
        return env_project
    if root is not None:
        from ryva.cloud_sync import get_project_id

        stored = get_project_id(root)
        if stored:
            return stored
    console.print("[red]Project ID is required. Pass --project-id or set RYVA_PROJECT_ID.[/red]")
    raise typer.Exit(1)


def _resolve_ingestion_token(ingestion_token: str | None) -> str:
    token = ingestion_token or os.environ.get("RYVA_INGESTION_TOKEN")
    if token:
        return token
    console.print("[red]Ingestion token is required. Pass --ingestion-token or set RYVA_INGESTION_TOKEN.[/red]")
    raise typer.Exit(1)


def _load_json_payload(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text())
    except FileNotFoundError:
        console.print(f"[red]File not found: {path}[/red]")
        raise typer.Exit(1)
    except json.JSONDecodeError as exc:
        console.print(f"[red]Invalid JSON in {path}: {exc}[/red]")
        raise typer.Exit(1)
    if not isinstance(payload, dict):
        console.print(f"[red]{path} must contain a JSON object.[/red]")
        raise typer.Exit(1)
    return payload


def _write_external_connector_readme(
    out_dir: Path,
    *,
    system_id: str,
    project_id: str,
    source_type: str,
    config: dict,
) -> None:
    system_name = config.get("system_name") or system_id
    trace_path = out_dir / "trace.payload.json"
    lineage_path = out_dir / "lineage.payload.json"
    refresh_path = out_dir / "refresh.descriptor.json"
    readme = f"""# Ryva external connector scaffold

This folder was generated for system `{system_name}`.

## Identity

- `project_id`: `{project_id}`
- `system_id`: `{system_id}`
- `source_type`: `{source_type}`

## Required auth

Set an ingestion token that has the scopes you need:

```bash
export RYVA_INGESTION_TOKEN=\"<system ingestion token>\"
```

Optional:

```bash
export RYVA_PROJECT_ID=\"{project_id}\"
export RYVA_CLOUD_URL=\"https://ryva-cloud-production.up.railway.app\"
```

## Send external runtime evidence

```bash
ryva cloud external trace \\
  --system-id {system_id} \\
  --project-id {project_id} \\
  {trace_path}
```

```bash
ryva cloud external lineage \\
  --system-id {system_id} \\
  --project-id {project_id} \\
  {lineage_path}
```

## Preview external metadata refresh

```bash
ryva cloud external refresh-preview \\
  --system-id {system_id} \\
  --project-id {project_id} \\
  --source-type {source_type} \\
  {refresh_path}
```

## Apply external metadata refresh

```bash
ryva cloud external refresh \\
  --system-id {system_id} \\
  --project-id {project_id} \\
  --source-type {source_type} \\
  {refresh_path}
```

## Cloud-provided paths

- trace ingestion: `{config.get("trace_ingestion_path", "")}`
- lineage ingestion: `{config.get("lineage_ingestion_path", "")}`
- metadata refresh: `{config.get("metadata_refresh_path", "")}`
- metadata refresh preview: `{config.get("metadata_refresh_preview_path", "")}`
"""
    (out_dir / "README.md").write_text(readme)


@cloud_external_app.command("scaffold")
def cloud_external_scaffold_cmd(
    system_id: str = typer.Option(..., "--system-id", help="Ryva system ID"),
    out_dir: Path = typer.Option(Path("external-connector"), "--out", help="Directory to write sample connector files into"),
    project_id: str | None = typer.Option(None, "--project-id", help="Ryva project ID"),
    cloud_url: str = typer.Option(None, "--cloud-url", help="Ryva Cloud base URL"),
    root: Path | None = typer.Option(None, "--root", help="Optional Ryva root for saved login lookup"),
):
    """Generate ready-to-use sample files for an imported external system connector."""
    from ryva.cloud_sync import get_system_ingestion_config, get_token

    resolved_project_id = _resolve_cloud_project_id(root, project_id)
    lookup_root = root or Path.cwd()
    bearer = get_token(lookup_root)
    if not bearer:
        console.print("[red]Not logged in. Run: ryva cloud login[/red]")
        raise typer.Exit(1)
    target_url = cloud_url or os.environ.get("RYVA_CLOUD_URL", "https://ryva-cloud-production.up.railway.app")

    config = get_system_ingestion_config(
        project_id=resolved_project_id,
        system_id=system_id,
        api_key=bearer,
        cloud_url=target_url,
    )
    source_sync_spec = config.get("source_sync_spec") or {}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "trace.payload.json").write_text(json.dumps(config.get("sample_trace_payload") or {}, indent=2))
    (out_dir / "lineage.payload.json").write_text(json.dumps(config.get("sample_lineage_payload") or {}, indent=2))
    (out_dir / "refresh.descriptor.json").write_text(
        json.dumps(source_sync_spec.get("sample_refresh_descriptor") or {}, indent=2)
    )
    _write_external_connector_readme(
        out_dir,
        system_id=system_id,
        project_id=resolved_project_id,
        source_type=source_sync_spec.get("source_type") or "other",
        config=config,
    )
    console.print(f"[green]✓ External connector scaffold written to {out_dir}[/green]")


@cloud_external_app.command("trace")
def cloud_external_trace_cmd(
    payload_file: Path = typer.Argument(..., help="Path to external trace JSON payload"),
    system_id: str = typer.Option(..., "--system-id", help="Ryva system ID"),
    project_id: str | None = typer.Option(None, "--project-id", help="Ryva project ID"),
    ingestion_token: str | None = typer.Option(None, "--ingestion-token", help="System ingestion token"),
    cloud_url: str = typer.Option(None, "--cloud-url", help="Ryva Cloud base URL"),
    root: Path | None = typer.Option(None, "--root", help="Optional Ryva root for saved project lookup"),
):
    """Send signed external runtime trace evidence to Ryva Cloud."""
    from ryva.cloud_sync import sync_external_trace

    resolved_project_id = _resolve_cloud_project_id(root, project_id)
    resolved_token = _resolve_ingestion_token(ingestion_token)
    payload = _load_json_payload(payload_file)
    target_url = cloud_url or os.environ.get("RYVA_CLOUD_URL", "https://ryva-cloud-production.up.railway.app")

    result = sync_external_trace(
        project_id=resolved_project_id,
        system_id=system_id,
        ingestion_token=resolved_token,
        payload=payload,
        cloud_url=target_url,
    )
    console.print(f"[green]✓ External trace synced[/green] [dim]{result.get('run_id') or payload.get('run_id') or ''}[/dim]")


@cloud_external_app.command("lineage")
def cloud_external_lineage_cmd(
    payload_file: Path = typer.Argument(..., help="Path to external lineage JSON payload"),
    system_id: str = typer.Option(..., "--system-id", help="Ryva system ID"),
    project_id: str | None = typer.Option(None, "--project-id", help="Ryva project ID"),
    ingestion_token: str | None = typer.Option(None, "--ingestion-token", help="System ingestion token"),
    cloud_url: str = typer.Option(None, "--cloud-url", help="Ryva Cloud base URL"),
    root: Path | None = typer.Option(None, "--root", help="Optional Ryva root for saved project lookup"),
):
    """Send signed external lineage/version evidence to Ryva Cloud."""
    from ryva.cloud_sync import sync_external_lineage

    resolved_project_id = _resolve_cloud_project_id(root, project_id)
    resolved_token = _resolve_ingestion_token(ingestion_token)
    payload = _load_json_payload(payload_file)
    target_url = cloud_url or os.environ.get("RYVA_CLOUD_URL", "https://ryva-cloud-production.up.railway.app")

    result = sync_external_lineage(
        project_id=resolved_project_id,
        system_id=system_id,
        ingestion_token=resolved_token,
        payload=payload,
        cloud_url=target_url,
    )
    console.print(f"[green]✓ External lineage synced[/green] [dim]{result.get('run_id') or payload.get('run_id') or ''}[/dim]")


@cloud_external_app.command("refresh-preview")
def cloud_external_refresh_preview_cmd(
    descriptor_file: Path = typer.Argument(..., help="Path to external source descriptor JSON"),
    source_type: str = typer.Option(..., "--source-type", help="Connector source type, e.g. github_repo or aws_bedrock"),
    system_id: str | None = typer.Option(None, "--system-id", help="Ryva system ID"),
    external_system_id: str | None = typer.Option(None, "--external-system-id", help="External source system ID"),
    project_id: str | None = typer.Option(None, "--project-id", help="Ryva project ID"),
    ingestion_token: str | None = typer.Option(None, "--ingestion-token", help="System ingestion token"),
    cloud_url: str = typer.Option(None, "--cloud-url", help="Ryva Cloud base URL"),
    root: Path | None = typer.Option(None, "--root", help="Optional Ryva root for saved project lookup"),
):
    """Preview external metadata refresh against an imported system."""
    from ryva.cloud_sync import preview_external_refresh

    if not system_id and not external_system_id:
        console.print("[red]Provide --system-id or --external-system-id.[/red]")
        raise typer.Exit(1)

    resolved_project_id = _resolve_cloud_project_id(root, project_id)
    resolved_token = _resolve_ingestion_token(ingestion_token)
    descriptor = _load_json_payload(descriptor_file)
    target_url = cloud_url or os.environ.get("RYVA_CLOUD_URL", "https://ryva-cloud-production.up.railway.app")

    result = preview_external_refresh(
        project_id=resolved_project_id,
        system_id=system_id,
        external_system_id=external_system_id,
        source_type=source_type,
        descriptor=descriptor,
        ingestion_token=resolved_token,
        cloud_url=target_url,
    )
    console.print_json(data=result)


@cloud_external_app.command("refresh")
def cloud_external_refresh_cmd(
    descriptor_file: Path = typer.Argument(..., help="Path to external source descriptor JSON"),
    source_type: str = typer.Option(..., "--source-type", help="Connector source type, e.g. github_repo or aws_bedrock"),
    system_id: str | None = typer.Option(None, "--system-id", help="Ryva system ID"),
    external_system_id: str | None = typer.Option(None, "--external-system-id", help="External source system ID"),
    project_id: str | None = typer.Option(None, "--project-id", help="Ryva project ID"),
    ingestion_token: str | None = typer.Option(None, "--ingestion-token", help="System ingestion token"),
    cloud_url: str = typer.Option(None, "--cloud-url", help="Ryva Cloud base URL"),
    root: Path | None = typer.Option(None, "--root", help="Optional Ryva root for saved project lookup"),
):
    """Apply external metadata refresh to an imported system."""
    from ryva.cloud_sync import refresh_external_metadata

    if not system_id and not external_system_id:
        console.print("[red]Provide --system-id or --external-system-id.[/red]")
        raise typer.Exit(1)

    resolved_project_id = _resolve_cloud_project_id(root, project_id)
    resolved_token = _resolve_ingestion_token(ingestion_token)
    descriptor = _load_json_payload(descriptor_file)
    target_url = cloud_url or os.environ.get("RYVA_CLOUD_URL", "https://ryva-cloud-production.up.railway.app")

    result = refresh_external_metadata(
        project_id=resolved_project_id,
        system_id=system_id,
        external_system_id=external_system_id,
        source_type=source_type,
        descriptor=descriptor,
        ingestion_token=resolved_token,
        cloud_url=target_url,
    )
    console.print_json(data=result)


@app.command("modelcard")
def modelcard_cmd(
    agent: str = typer.Argument(..., help="Agent name to generate model card for"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Generate a model card for an agent."""
    from ryva.model_card import generate_model_card, save_model_card, print_model_card_summary
    from ryva.utils import find_project_root

    r = root or find_project_root()
    console.print(f"[bold]Generating model card for {agent}...[/bold]")
    card = generate_model_card(r, agent)
    path = save_model_card(r, agent, card)
    print_model_card_summary(card)
    console.print(f"[green]✓ Model card saved: {path}[/green]")


if __name__ == "__main__":
    app()
