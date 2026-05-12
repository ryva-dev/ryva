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
    r = root or find_project_root()

    try:
        input_data = json.loads(input)
    except json.JSONDecodeError:
        console.print("[red]--input must be valid JSON[/red]")
        raise typer.Exit(1)

    if agent:
        run_agent(r, agent, input_data)
    elif pipeline:
        console.print("[yellow]Pipeline runner coming in Phase 2.[/yellow]")
    else:
        console.print("[red]Provide --agent or --pipeline[/red]")
        raise typer.Exit(1)


@app.command()
def test(
    agent: Optional[str] = typer.Option(None, "--agent", "-a", help="Agent name (omit for all)"),
    root: Optional[Path] = typer.Option(None, "--root", help="Project root"),
):
    """Run tests for agents."""
    from ryva.utils import find_project_root
    from ryva.tester import run_tests
    r = root or find_project_root()
    ok = run_tests(r, agent)
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


if __name__ == "__main__":
    app()

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


if __name__ == "__main__":
    app()