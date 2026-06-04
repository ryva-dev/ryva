from __future__ import annotations

import json
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
):
    """Initialize a new Ryva project."""
    from ryva.init_project import scaffold
    scaffold(name, path or Path.cwd() / name)


@app.command()
def compile(
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Compile and validate all agents, tools, and pipelines."""
    from ryva.compiler import compile_project
    r = _resolve_root(root)
    ok = compile_project(r)
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


if __name__ == "__main__":
    app()


# ── Cloud commands ────────────────────────────────────────────────────────────

cloud_app = typer.Typer(help="Connect and sync to Ryva Cloud.")
app.add_typer(cloud_app, name="cloud")


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
):
    """Sync traces, lineage, compliance reports, and model cards to Ryva Cloud."""
    import os
    import json
    import httpx
    from ryva.cloud_sync import get_token, get_project_id, cloud_sync as do_cloud_sync
    from ryva.utils import find_project_root

    r = root or find_project_root()
    token = get_token(r)
    project_id = get_project_id(r)

    if not token or not project_id:
        console.print("[red]Not logged in. Run: ryva cloud login[/red]")
        raise typer.Exit(1)

    CLOUD_URL = os.environ.get("RYVA_CLOUD_URL", "https://ryva-cloud-production.up.railway.app")
    headers = {"Authorization": f"Bearer {token}"}

    console.print(f"[bold]Syncing to Ryva Cloud ({env})...[/bold]")

    # Sync traces
    traces_dir = r / "traces"
    if traces_dir.exists():
        trace_files = list(traces_dir.glob("*.json"))
        synced = 0
        for tf in trace_files:
            try:
                trace = json.loads(tf.read_text())
                trace["project_id"] = project_id
                resp = httpx.post(
                    f"{CLOUD_URL}/api/v1/traces/",
                    json=trace,
                    headers=headers,
                    timeout=10
                )
                if resp.status_code in (200, 201):
                    synced += 1
            except Exception:
                pass
        console.print(f"  [green]✓ Synced {synced}/{len(trace_files)} traces[/green]")

    # Sync governance report
    gov_report = r / "target" / "governance_report.json"
    if gov_report.exists():
        try:
            report = json.loads(gov_report.read_text())
            report["project_id"] = project_id
            resp = httpx.post(
                f"{CLOUD_URL}/api/v1/compliance/report",
                json=report,
                headers=headers,
                timeout=10
            )
            if resp.status_code in (200, 201):
                console.print("  [green]✓ Synced governance report[/green]")
        except Exception as e:
            console.print(f"  [yellow]⚠ Could not sync governance report: {e}[/yellow]")

    # Sync model cards
    model_cards_dir = r / "target" / "model_cards"
    if model_cards_dir.exists():
        card_files = list(model_cards_dir.glob("*.json"))
        for cf in card_files:
            try:
                card = json.loads(cf.read_text())
                card["project_id"] = project_id
                httpx.post(
                    f"{CLOUD_URL}/api/v1/agents/modelcard",
                    json=card,
                    headers=headers,
                    timeout=10
                )
            except Exception:
                pass
        console.print(f"  [green]✓ Synced {len(card_files)} model card(s)[/green]")

    console.print(f"\n[bold green]✓ Sync complete[/bold green]")
    console.print(f"  View at: https://ryva-dashboard.vercel.app/dashboard")


@cloud_app.command("status")
def cloud_status_cmd(
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Show cloud connection status."""
    from ryva.cloud_sync import get_token, get_project_id
    from ryva.utils import find_project_root

    r = root or find_project_root()
    token = get_token(r)
    project_id = get_project_id(r)

    if token and project_id:
        console.print(f"[green]✓ Connected to Ryva Cloud[/green]")
        console.print(f"  Project ID: {project_id}")
    else:
        console.print("[yellow]Not connected. Run: ryva cloud login[/yellow]")
