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
    from ryva.utils import find_project_root
    r = root or find_project_root()
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
    input: str = typer.Option("{}", "--input", "-i", help="JSON input string"),
    root: Path | None = typer.Option(None, "--root", help="Project root"),
):
    """Run an agent or pipeline locally."""
    from ryva.pipeline_runner import run_pipeline
    from ryva.runner import run_agent
    from ryva.utils import find_project_root
    r = root or find_project_root()

    try:
        input_data = json.loads(input)
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
        ok = run_tests(r, agent)
    elif model:
        ok = run_ml_tests(r, model)
    elif vector:
        ok = run_vector_tests(r, vector)
    elif multimodal:
        ok = run_multimodal_tests(r, multimodal)
    else:
        agent_ok = run_tests(r, None)
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
    out: Path | None = typer.Option(None, "--out", "-o", help="Save full JSON report to file"),
    root: Path = typer.Option(None, "--root", help="Project root"),
):
    """Generate a governance report: risk scores, EU AI Act checklist, AI bill of materials."""
    from ryva.governance import show_report
    from ryva.utils import find_project_root
    r = root or find_project_root()
    show_report(r, out)


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


if __name__ == "__main__":
    app()
