from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from rich.table import Table

from ryva.utils import console

_RETRAIN_DIR = "retraining"
_VALID_TRIGGERS = frozenset({"manual", "drift", "feedback", "scheduled"})


class DriftMonitor:
    """
    Tracks model output quality over time by comparing recent run scores
    to a baseline window. Detects statistical drift using a simple
    sliding-window mean comparison.
    """

    def __init__(
        self,
        root: Path,
        agent: str,
        baseline_window: int = 50,
        drift_threshold: float = 0.15,
    ) -> None:
        self.root = root
        self.agent = agent
        self.baseline_window = baseline_window
        self.drift_threshold = drift_threshold
        self._scores_file = root / "retraining" / f"{agent}_scores.json"

    def record_score(self, score: float, run_id: str | None = None) -> None:
        """Append a quality score in [0, 1] for a recent run."""
        scores = self._load_scores()
        scores.append({
            "score": float(score),
            "run_id": run_id or "",
            "recorded_at": datetime.now(UTC).isoformat(),
        })
        self._save_scores(scores)

    def compute_drift(self) -> dict:
        """
        Compare the latest half of recorded scores to the baseline half.
        Returns a dict with drift magnitude, baseline_mean, recent_mean, and drifted flag.
        """
        scores = self._load_scores()
        values = [s["score"] for s in scores]

        if len(values) < 4:
            return {
                "agent": self.agent,
                "drifted": False,
                "reason": "Insufficient data",
                "baseline_mean": None,
                "recent_mean": None,
                "drift_magnitude": None,
                "score_count": len(values),
            }

        mid = len(values) // 2
        baseline = values[:mid]
        recent = values[mid:]

        baseline_mean = sum(baseline) / len(baseline)
        recent_mean = sum(recent) / len(recent)
        drift_magnitude = baseline_mean - recent_mean  # positive = degradation

        drifted = drift_magnitude >= self.drift_threshold

        return {
            "agent": self.agent,
            "drifted": drifted,
            "reason": (
                f"Recent mean {recent_mean:.3f} dropped {drift_magnitude:.3f} "
                f"from baseline {baseline_mean:.3f} (threshold: {self.drift_threshold})"
                if drifted else "Within threshold"
            ),
            "baseline_mean": round(baseline_mean, 4),
            "recent_mean": round(recent_mean, 4),
            "drift_magnitude": round(drift_magnitude, 4),
            "score_count": len(values),
        }

    def _load_scores(self) -> list[dict]:
        if not self._scores_file.exists():
            return []
        try:
            return json.loads(self._scores_file.read_text())
        except (json.JSONDecodeError, OSError):
            return []

    def _save_scores(self, scores: list[dict]) -> None:
        self._scores_file.parent.mkdir(parents=True, exist_ok=True)
        self._scores_file.write_text(json.dumps(scores, indent=2))

    def clear_scores(self) -> None:
        """Clear all recorded scores for this agent."""
        if self._scores_file.exists():
            self._scores_file.unlink()


# ---------------------------------------------------------------------------
# Retraining job management
# ---------------------------------------------------------------------------

def trigger_retraining(
    root: Path,
    agent: str,
    trigger: str = "manual",
    reason: str = "",
    metadata: dict | None = None,
) -> str:
    """
    Record a retraining trigger event. Returns the job_id.

    trigger must be one of: manual, drift, feedback, scheduled.
    """
    if trigger not in _VALID_TRIGGERS:
        console.print(f"[red]Invalid trigger '{trigger}'. Must be one of: {', '.join(sorted(_VALID_TRIGGERS))}[/red]")
        raise SystemExit(1)

    retrain_dir = root / _RETRAIN_DIR
    retrain_dir.mkdir(exist_ok=True)

    job_id = str(uuid.uuid4())[:8]
    entry = {
        "job_id": job_id,
        "agent": agent,
        "trigger": trigger,
        "reason": reason,
        "status": "pending",
        "created_at": datetime.now(UTC).isoformat(),
        "completed_at": None,
        "metadata": metadata or {},
    }
    (retrain_dir / f"{job_id}.json").write_text(json.dumps(entry, indent=2))
    console.print(f"[green]✓ Retraining job {job_id} created for agent '{agent}' (trigger: {trigger})[/green]")
    return job_id


def load_history(root: Path, agent: str | None = None) -> list[dict]:
    """Load all retraining jobs, optionally filtered by agent."""
    retrain_dir = root / _RETRAIN_DIR
    if not retrain_dir.exists():
        return []

    jobs = []
    for path in sorted(retrain_dir.glob("*.json"), reverse=True):
        if path.stem.endswith("_scores"):
            continue
        try:
            job = json.loads(path.read_text())
            if agent and job.get("agent") != agent:
                continue
            jobs.append(job)
        except (json.JSONDecodeError, OSError):
            continue
    return jobs


def update_job_status(root: Path, job_id: str, status: str, metadata: dict | None = None) -> bool:
    """Update the status of a retraining job. Returns True if found."""
    path = root / _RETRAIN_DIR / f"{job_id}.json"
    if not path.exists():
        return False
    try:
        job = json.loads(path.read_text())
        job["status"] = status
        if status in {"completed", "failed"}:
            job["completed_at"] = datetime.now(UTC).isoformat()
        if metadata:
            job["metadata"].update(metadata)
        path.write_text(json.dumps(job, indent=2))
        return True
    except (json.JSONDecodeError, OSError):
        return False


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def show_history(root: Path, agent: str | None = None) -> None:
    jobs = load_history(root, agent)
    if not jobs:
        msg = f"No retraining history for agent '{agent}'." if agent else "No retraining history."
        console.print(f"[yellow]{msg}[/yellow]")
        return

    table = Table(title="Retraining History", header_style="bold")
    table.add_column("Job ID", style="dim")
    table.add_column("Agent", style="cyan")
    table.add_column("Trigger")
    table.add_column("Status", justify="center")
    table.add_column("Reason", style="dim")
    table.add_column("Created")

    for job in jobs:
        status = job.get("status", "—")
        color = {"pending": "yellow", "completed": "green", "failed": "red"}.get(status, "dim")
        table.add_row(
            job.get("job_id", "—"),
            job.get("agent", "—"),
            job.get("trigger", "—"),
            f"[{color}]{status}[/{color}]",
            (job.get("reason") or "—")[:50],
            (job.get("created_at") or "—")[:19].replace("T", " "),
        )

    console.print(table)


def show_drift(root: Path, agent: str, threshold: float = 0.15) -> dict:
    """Display drift analysis for a single agent."""
    monitor = DriftMonitor(root, agent, drift_threshold=threshold)
    result = monitor.compute_drift()

    color = "red" if result["drifted"] else "green"
    icon = "✗" if result["drifted"] else "✓"
    console.print(f"\n[{color}]{icon} Drift analysis for '{agent}'[/{color}]")
    console.print(f"  {result['reason']}")
    if result["score_count"] > 0:
        console.print(f"  Scores analyzed: {result['score_count']}")
    return result
