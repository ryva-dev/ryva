from __future__ import annotations
import json
import uuid
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

TRACES_DIR = "traces"


def start_trace(root: Path, agent: str, model: str, provider: str) -> dict:
    trace = {
        "run_id": str(uuid.uuid4())[:8],
        "agent": agent,
        "model": model,
        "provider": provider,
        "started_at": datetime.utcnow().isoformat(),
        "steps": [],
        "status": "running",
    }
    return trace


def add_step(trace: dict, step_type: str, data: dict):
    trace["steps"].append({
        "type": step_type,
        "timestamp": datetime.utcnow().isoformat(),
        **data,
    })


def finish_trace(root: Path, trace: dict, status: str = "success"):
    trace["status"] = status
    trace["finished_at"] = datetime.utcnow().isoformat()

    started = datetime.fromisoformat(trace["started_at"])
    finished = datetime.fromisoformat(trace["finished_at"])
    trace["duration_ms"] = int((finished - started).total_seconds() * 1000)

    traces_dir = root / TRACES_DIR
    traces_dir.mkdir(exist_ok=True)

    path = traces_dir / f"{trace['run_id']}.json"
    path.write_text(json.dumps(trace, indent=2))
    return trace["run_id"]


def traces_list(root: Path):
    traces_dir = root / TRACES_DIR
    if not traces_dir.exists():
        console.print("[yellow]No traces found. Run an agent first.[/yellow]")
        return

    files = sorted(traces_dir.glob("*.json"), reverse=True)
    if not files:
        console.print("[yellow]No traces found. Run an agent first.[/yellow]")
        return

    table = Table(title="Agent Traces", header_style="bold")
    table.add_column("Run ID", style="cyan")
    table.add_column("Agent")
    table.add_column("Model", style="dim")
    table.add_column("Status")
    table.add_column("Duration")
    table.add_column("Steps", justify="right")
    table.add_column("Started")

    for f in files[:20]:
        t = json.loads(f.read_text())
        status_color = "green" if t.get("status") == "success" else "red"
        status = f"[{status_color}]{t.get('status', '—')}[/{status_color}]"
        duration = f"{t.get('duration_ms', '—')}ms" if t.get('duration_ms') else "—"
        table.add_row(
            t.get("run_id", "—"),
            t.get("agent", "—"),
            t.get("model", "—"),
            status,
            duration,
            str(len(t.get("steps", []))),
            t.get("started_at", "—")[:19].replace("T", " "),
        )

    console.print(table)


def traces_show(root: Path, run_id: str):
    traces_dir = root / TRACES_DIR
    path = traces_dir / f"{run_id}.json"

    if not path.exists():
        console.print(f"[red]Trace '{run_id}' not found.[/red]")
        return

    t = json.loads(path.read_text())

    console.print(f"\n[bold cyan]Trace: {t['run_id']}[/bold cyan]")
    console.print(f"  Agent:    {t.get('agent')}")
    console.print(f"  Model:    {t.get('model')} ({t.get('provider')})")
    console.print(f"  Status:   {t.get('status')}")
    console.print(f"  Duration: {t.get('duration_ms')}ms")
    console.print(f"  Started:  {t.get('started_at', '')[:19].replace('T', ' ')}")
    console.print()

    for i, step in enumerate(t.get("steps", []), 1):
        step_type = step.get("type", "step")
        console.print(f"[bold]Step {i} — {step_type}[/bold]")

        if step_type == "prompt":
            console.print(Panel(step.get("content", ""), title="Prompt", border_style="blue"))
        elif step_type == "response":
            console.print(Panel(step.get("content", ""), title="Response", border_style="green"))
            if step.get("tokens"):
                console.print(f"  [dim]Tokens: {step['tokens']} | Cost: ${step.get('cost_usd', 0):.6f}[/dim]")
        elif step_type == "tool_call":
            console.print(f"  Tool: [cyan]{step.get('tool')}[/cyan]")
            console.print(f"  Input: {json.dumps(step.get('input', {}))}")
            console.print(f"  Output: {step.get('output', '—')}")
        else:
            console.print(f"  {json.dumps(step)}")
        console.print()