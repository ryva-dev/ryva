from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from rich.table import Table

from ryva.utils import console


class EdgeTelemetryCollector:
    """
    Collects inference telemetry from edge devices and writes records to
    root/edge_telemetry/<device_id>/<record_id>.json for later aggregation.
    """

    def __init__(self, root: Path, device_id: str) -> None:
        self.root = root
        self.device_id = device_id
        self._dir = root / "edge_telemetry" / device_id

    @property
    def telemetry_dir(self) -> Path:
        return self._dir

    def record(
        self,
        agent: str,
        model: str,
        latency_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        status: str = "success",
        metadata: dict | None = None,
    ) -> str:
        """Persist one inference record. Returns record_id."""
        self._dir.mkdir(parents=True, exist_ok=True)
        record_id = str(uuid.uuid4())[:8]
        entry = {
            "record_id": record_id,
            "device_id": self.device_id,
            "agent": agent,
            "model": model,
            "timestamp": datetime.now(UTC).isoformat(),
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "status": status,
            "metadata": metadata or {},
        }
        (self._dir / f"{record_id}.json").write_text(json.dumps(entry, indent=2))
        return record_id

    def load(self) -> list[dict]:
        """Load all telemetry records for this device."""
        if not self._dir.exists():
            return []
        records = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                records.append(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        return records

    def flush(self) -> int:
        """Delete all local telemetry files for this device after they've been uploaded.
        Returns the number of records flushed."""
        if not self._dir.exists():
            return 0
        count = 0
        for path in list(self._dir.glob("*.json")):
            try:
                path.unlink()
                count += 1
            except OSError:
                pass
        return count

    def status(self) -> dict:
        """Return summary statistics for this device's telemetry."""
        records = self.load()
        if not records:
            return {
                "device_id": self.device_id,
                "record_count": 0,
                "avg_latency_ms": None,
                "error_rate": None,
                "agents": [],
                "oldest_record": None,
                "newest_record": None,
            }
        latencies = [r["latency_ms"] for r in records if "latency_ms" in r]
        errors = [r for r in records if r.get("status") != "success"]
        agents = list({r["agent"] for r in records if r.get("agent")})
        timestamps = [r["timestamp"] for r in records if r.get("timestamp")]
        return {
            "device_id": self.device_id,
            "record_count": len(records),
            "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
            "error_rate": round(len(errors) / len(records), 4) if records else None,
            "agents": sorted(agents),
            "oldest_record": min(timestamps) if timestamps else None,
            "newest_record": max(timestamps) if timestamps else None,
        }


# ---------------------------------------------------------------------------
# Multi-device aggregation
# ---------------------------------------------------------------------------

def load_all_devices(root: Path) -> dict[str, list[dict]]:
    """Load telemetry records from all devices under root/edge_telemetry/."""
    base = root / "edge_telemetry"
    if not base.exists():
        return {}
    result: dict[str, list[dict]] = {}
    for device_dir in sorted(base.iterdir()):
        if not device_dir.is_dir():
            continue
        records = []
        for path in sorted(device_dir.glob("*.json")):
            try:
                records.append(json.loads(path.read_text()))
            except (json.JSONDecodeError, OSError):
                continue
        if records:
            result[device_dir.name] = records
    return result


def aggregate_report(root: Path) -> dict:
    """Compute an aggregate summary across all edge devices."""
    all_devices = load_all_devices(root)
    total_records = sum(len(v) for v in all_devices.values())
    all_records = [r for v in all_devices.values() for r in v]

    if not all_records:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "device_count": 0,
            "total_records": 0,
            "avg_latency_ms": None,
            "error_rate": None,
            "agents": [],
            "devices": [],
        }

    latencies = [r["latency_ms"] for r in all_records if "latency_ms" in r]
    errors = [r for r in all_records if r.get("status") != "success"]
    agents = list({r["agent"] for r in all_records if r.get("agent")})

    device_summaries = []
    for device_id, records in all_devices.items():
        collector = EdgeTelemetryCollector(root, device_id)
        device_summaries.append(collector.status())

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "device_count": len(all_devices),
        "total_records": total_records,
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
        "error_rate": round(len(errors) / total_records, 4) if total_records else None,
        "agents": sorted(agents),
        "devices": device_summaries,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def show_status(root: Path, device_id: str | None) -> None:
    """Display telemetry status for one device or all devices."""
    if device_id:
        collector = EdgeTelemetryCollector(root, device_id)
        s = collector.status()
        _print_device_status(s)
        return

    report = aggregate_report(root)
    if report["device_count"] == 0:
        console.print("[yellow]No edge telemetry data found.[/yellow]")
        return

    console.print(f"\n[bold]Edge Fleet Summary[/bold] — {report['device_count']} device(s), "
                  f"{report['total_records']} records\n")
    for ds in report["devices"]:
        _print_device_status(ds)


def _print_device_status(s: dict) -> None:
    table = Table(title=f"Device: {s['device_id']}", header_style="bold", show_header=False)
    table.add_column("Metric", style="dim")
    table.add_column("Value")

    table.add_row("Records", str(s["record_count"]))
    if s["avg_latency_ms"] is not None:
        table.add_row("Avg Latency", f"{s['avg_latency_ms']}ms")
    if s["error_rate"] is not None:
        color = "red" if s["error_rate"] > 0.1 else "green"
        table.add_row("Error Rate", f"[{color}]{s['error_rate']:.1%}[/{color}]")
    if s["agents"]:
        table.add_row("Agents", ", ".join(s["agents"]))
    if s["newest_record"]:
        table.add_row("Last Record", s["newest_record"][:19].replace("T", " "))

    console.print(table)


def show_report(root: Path, out: Path | None = None) -> None:
    """Display aggregate edge telemetry report."""
    report = aggregate_report(root)

    if report["device_count"] == 0:
        console.print("[yellow]No edge telemetry data found.[/yellow]")
        return

    table = Table(title="Edge Fleet Telemetry", header_style="bold")
    table.add_column("Device")
    table.add_column("Records", justify="right")
    table.add_column("Avg Latency", justify="right")
    table.add_column("Error Rate", justify="right")
    table.add_column("Agents")
    table.add_column("Last Seen")

    for ds in report["devices"]:
        err = ds["error_rate"]
        err_color = "red" if err and err > 0.1 else "green"
        table.add_row(
            ds["device_id"],
            str(ds["record_count"]),
            f"{ds['avg_latency_ms']}ms" if ds["avg_latency_ms"] else "—",
            f"[{err_color}]{err:.1%}[/{err_color}]" if err is not None else "—",
            ", ".join(ds["agents"])[:40] or "—",
            (ds["newest_record"] or "—")[:19].replace("T", " "),
        )

    console.print(table)

    if out:
        out.write_text(json.dumps(report, indent=2))
        console.print(f"[green]✓ Report saved to {out}[/green]")


def flush_device(root: Path, device_id: str) -> None:
    """Flush (delete) all telemetry for a device after upload."""
    collector = EdgeTelemetryCollector(root, device_id)
    n = collector.flush()
    console.print(f"[green]✓ Flushed {n} record(s) for device '{device_id}'[/green]")
