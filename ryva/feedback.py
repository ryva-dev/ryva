from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from rich.table import Table

from ryva.utils import console

FEEDBACK_DIR = Path("logs") / "feedback"
VALID_OUTCOMES = frozenset({"correct", "incorrect", "partial", "unknown"})


def record_feedback(
    root: Path,
    run_id: str,
    outcome: str,
    note: str = "",
    annotator: str = "",
) -> None:
    if outcome not in VALID_OUTCOMES:
        console.print(
            f"[red]Invalid outcome '{outcome}'. "
            f"Use: {', '.join(sorted(VALID_OUTCOMES))}[/red]"
        )
        raise SystemExit(1)

    feedback_dir = root / FEEDBACK_DIR
    feedback_dir.mkdir(parents=True, exist_ok=True)

    agent = _resolve_agent(root, run_id)

    entry = {
        "feedback_id": str(uuid.uuid4())[:8],
        "run_id": run_id,
        "agent": agent,
        "outcome": outcome,
        "note": note,
        "annotator": annotator,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    (feedback_dir / f"{run_id}.json").write_text(json.dumps(entry, indent=2))
    console.print(
        f"[bold green]✓ Feedback recorded[/bold green] — "
        f"run [cyan]{run_id}[/cyan]: [bold]{outcome}[/bold]"
    )


def _resolve_agent(root: Path, run_id: str) -> str:
    """Try to look up the agent name from lineage or run logs."""
    for path in (
        root / "lineage" / f"{run_id}.json",
        root / "logs" / "runs" / f"{run_id}.json",
    ):
        if path.exists():
            try:
                return json.loads(path.read_text()).get("agent", "")
            except (json.JSONDecodeError, OSError):
                pass
    return ""


def load_feedback(root: Path, agent: str | None = None) -> list[dict]:
    """Load all feedback entries, optionally filtered by agent."""
    feedback_dir = root / FEEDBACK_DIR
    if not feedback_dir.exists():
        return []

    entries: list[dict] = []
    for f in sorted(feedback_dir.glob("*.json"), reverse=True):
        try:
            entry = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if agent and entry.get("agent") != agent:
            continue
        entries.append(entry)

    return entries


def show_feedback_report(root: Path, agent: str | None = None) -> None:
    entries = load_feedback(root, agent=agent)

    if not entries:
        console.print("[yellow]No feedback recorded yet.[/yellow]")
        console.print(
            "[dim]Record with: "
            "ryva feedback record --run-id <id> --outcome correct[/dim]"
        )
        return

    by_agent: dict[str, dict[str, int]] = {}
    for e in entries:
        a = e.get("agent") or "unknown"
        if a not in by_agent:
            by_agent[a] = {"correct": 0, "incorrect": 0, "partial": 0, "unknown": 0}
        outcome = e.get("outcome", "unknown")
        by_agent[a][outcome] = by_agent[a].get(outcome, 0) + 1

    summary_table = Table(title="Outcome Feedback Summary", header_style="bold")
    summary_table.add_column("Agent", style="cyan")
    summary_table.add_column("Total", justify="right")
    summary_table.add_column("Correct", justify="right")
    summary_table.add_column("Incorrect", justify="right")
    summary_table.add_column("Partial", justify="right")
    summary_table.add_column("Accuracy", justify="right")

    for agent_name, stats in by_agent.items():
        correct = stats.get("correct", 0)
        incorrect = stats.get("incorrect", 0)
        partial = stats.get("partial", 0)
        unknown = stats.get("unknown", 0)
        total = correct + incorrect + partial + unknown
        decided = correct + incorrect + partial
        accuracy = f"{correct / decided:.0%}" if decided else "—"
        summary_table.add_row(
            agent_name,
            str(total),
            f"[green]{correct}[/green]",
            f"[red]{incorrect}[/red]",
            f"[yellow]{partial}[/yellow]",
            accuracy,
        )
    console.print(summary_table)

    console.print("\n[bold]Recent Feedback[/bold]")
    detail_table = Table(show_header=True, header_style="bold")
    detail_table.add_column("Run ID", style="dim")
    detail_table.add_column("Agent", style="cyan")
    detail_table.add_column("Outcome")
    detail_table.add_column("Note", style="dim")
    detail_table.add_column("Recorded")

    for e in entries[:20]:
        outcome = e.get("outcome", "—")
        color = {"correct": "green", "incorrect": "red", "partial": "yellow"}.get(
            outcome, "dim"
        )
        detail_table.add_row(
            e.get("run_id", "—"),
            e.get("agent") or "—",
            f"[{color}]{outcome}[/{color}]",
            (e.get("note") or "")[:50],
            (e.get("recorded_at") or "")[:19].replace("T", " "),
        )
    console.print(detail_table)
