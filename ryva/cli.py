from __future__ import annotations
import json
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel

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
    path: Optional[Path] = typer.Option(None, help="Where to create the project"),
):
    """Initialize a new Ryva project."""
    from ryva.init_project import scaffold
    scaffold(name, path or Path.cwd() / name)


@app.command()
def compile(
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Compile and validate all agents, tools, and pipelines."""
    from ryva.utils import find_project_root
    from ryva.compiler import compile_project
    r = root or find_project_root()
    ok = compile_project(r)
    raise typer.Exit(0 if ok else 1)


@app.command()
def dag(
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent name (omit for all)"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Show the dependency graph for agents."""
    from ryva.utils import find_project_root
    from ryva.dag import show_dag
    r = root or find_project_root()
    show_dag(r, agent)


@app.command()
def run(
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent name"),
    pipeline: Optional[str] = typer.Option(None, "--pipeline", "-p", help="Pipeline name"),
    input: str = typer.Option("{}", "--input", "-i", help="JSON input string"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Run an agent or pipeline locally."""
    from ryva.utils import find_project_root
    from ryva.runner import run_agent
    from ryva.pipeline_runner import run_pipeline
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
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent name"),
    pipeline: Optional[str] = typer.Option(None, "--pipeline", "-p", help="Pipeline name"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="ML model name"),
    vector: Optional[str] = typer.Option(None, "--vector", "-v", help="Vector store name"),
    multimodal: Optional[str] = typer.Option(None, "--multimodal", help="Multimodal model name"),
    adversarial: bool = typer.Option(False, "--adversarial", help="Run adversarial tests"),
    hallucination: bool = typer.Option(False, "--hallucination", help="Run hallucination detection"),
    rag: bool = typer.Option(False, "--rag", help="Run RAG pipeline tests"),
    regression: bool = typer.Option(False, "--regression", help="Run regression tests against baseline"),
    memory: bool = typer.Option(False, "--memory", help="Run memory and context retention tests"),
    finetune: bool = typer.Option(False, "--finetune", help="Run fine-tune evaluation tests"),
    categories: Optional[str] = typer.Option(None, "--categories", help="Adversarial categories"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Run tests for agents, pipelines, ML models, vector stores, and multimodal models."""
    from ryva.utils import find_project_root
    from ryva.tester import run_tests
    from ryva.pipeline_tester import run_pipeline_tests
    from ryva.ml_tester import run_ml_tests
    from ryva.vector_tester import run_vector_tests
    from ryva.multimodal_tester import run_multimodal_tests
    from ryva.adversarial_tester import run_adversarial_tests
    from ryva.hallucination_detector import run_hallucination_tests
    from ryva.rag_tester import run_rag_tests
    from ryva.regression_tester import run_regression_tests
    from ryva.memory_tester import run_memory_tests
    from ryva.finetune_tester import run_finetune_tests
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
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent name (omit for all)"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Run LLM-as-judge evals for agents."""
    from ryva.utils import find_project_root
    from ryva.evaluator import run_evals
    r = root or find_project_root()
    ok = run_evals(r, agent)
    raise typer.Exit(0 if ok else 1)


docs_app = typer.Typer(help="Documentation commands.")
app.add_typer(docs_app, name="docs")


@docs_app.command("generate")
def docs_generate(
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Generate markdown documentation for all agents and tools."""
    from ryva.utils import find_project_root
    from ryva.docs import generate_docs
    r = root or find_project_root()
    generate_docs(r)


@docs_app.command("serve")
def docs_serve(
    port: int = typer.Option(8080, "--port", help="Port to serve on"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Serve generated docs locally in your browser."""
    from ryva.utils import find_project_root
    from ryva.docs import serve_docs
    r = root or find_project_root()
    serve_docs(r, port)


list_app = typer.Typer(help="List project resources.")
app.add_typer(list_app, name="list")


@list_app.command("agents")
def list_agents(root: Optional[Path] = typer.Option(None, "--root")):
    """List all agents in the project."""
    from ryva.utils import find_project_root, load_manifest
    r = root or find_project_root()
    m = load_manifest(r)
    for name, a in m.get("agents", {}).items():
        console.print(f"[cyan]{name}[/cyan] [dim]v{a.get('version','?')} — {a.get('description','')}[/dim]")


@list_app.command("tools")
def list_tools(root: Optional[Path] = typer.Option(None, "--root")):
    """List all tools in the project."""
    from ryva.utils import find_project_root, load_manifest
    r = root or find_project_root()
    m = load_manifest(r)
    for name, t in m.get("tools", {}).items():
        console.print(f"[green]{name}[/green] [dim]v{t.get('version','?')} — {t.get('description','')}[/dim]")


@list_app.command("prompts")
def list_prompts(root: Optional[Path] = typer.Option(None, "--root")):
    """List all prompt templates in the project."""
    from ryva.utils import find_project_root
    r = root or find_project_root()
    for p in (r / "prompts").glob("*.j2"):
        console.print(f"[yellow]{p.stem}[/yellow]")


@app.command()
def check(root: Optional[Path] = typer.Option(None, "--root")):
    """Lint and validate the project without writing output."""
    from ryva.utils import find_project_root
    from ryva.resolver import ProjectResolver
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
    root: Optional[Path] = typer.Option(None, "--root"),
):
    """Show recent run history."""
    from ryva.utils import find_project_root
    from rich.table import Table
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
    month: Optional[str] = typer.Option(None, "--month", "-m", help="Month in YYYY-MM format (default: current)"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Show cost report for agents."""
    from ryva.utils import find_project_root
    from ryva.cost_tracker import show_cost_report
    r = root or find_project_root()
    show_cost_report(r, month)

@app.command()
def forecast(
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Show cost forecast and budget projection for the current month."""
    from ryva.utils import find_project_root
    from ryva.cost_tracker import show_forecast
    r = root or find_project_root()
    show_forecast(r)

@app.command()
def compare(
    agent: str = typer.Argument(..., help="Agent name to compare"),
    providers: str = typer.Option("anthropic,openai,gemini,ollama", "--providers", "-p", help="Comma separated providers"),
    input: str = typer.Option("{}", "--input", "-i", help="JSON input string"),
    runs: int = typer.Option(3, "--runs", "-n", help="Number of runs per provider"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Compare agent performance across LLM providers."""
    from ryva.utils import find_project_root
    from ryva.comparer import compare_providers
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
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent name (omit for all)"),
    provider: str = typer.Option("anthropic", "--provider", "-p", help="Provider to test across model tiers"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Test agent compatibility across model sizes to find the cheapest that works."""
    from ryva.utils import find_project_root
    from ryva.compat_tester import run_compat_tests
    r = root or find_project_root()
    ok = run_compat_tests(r, agent, provider)
    raise typer.Exit(0 if ok else 1)

@app.command()
def baseline(
    agent: str = typer.Argument(..., help="Agent name to baseline"),
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Baseline label"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Create a baseline snapshot of agent outputs for regression testing."""
    from ryva.utils import find_project_root
    from ryva.regression_tester import create_baseline
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

if __name__ == "__main__":
    app()