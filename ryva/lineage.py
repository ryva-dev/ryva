from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rich.table import Table
from rich.tree import Tree

from ryva.utils import console

LINEAGE_DIR = "lineage"
_SECRET_ENV = "RYVA_SECRET"
_SECRET_FILE = ".ryva_secret"
_SIG_FIELDS = (
    "run_id", "parent_run_id", "trace_id", "agent", "model", "provider",
    "prompt_hash", "input_hash", "output_hash", "started_at", "status",
)


# ---------------------------------------------------------------------------
# HMAC signing helpers
# ---------------------------------------------------------------------------

def _load_secret(root: Path) -> bytes:
    """Load signing secret from env var, project file, or derive a stable fallback."""
    env_val = os.environ.get(_SECRET_ENV)
    if env_val:
        return env_val.encode()
    secret_file = root / _SECRET_FILE
    if secret_file.exists():
        return secret_file.read_bytes().strip()
    # Stable fallback: SHA-256 of the project root path (not cryptographically secure
    # but ensures consistent signatures across calls without a configured secret)
    return hashlib.sha256(str(root.resolve()).encode()).digest()


def _sign(entry: dict, root: Path) -> str:
    """Compute HMAC-SHA256 signature over canonical lineage fields."""
    canonical = {k: entry.get(k) for k in _SIG_FIELDS}
    payload = json.dumps(canonical, sort_keys=True, default=str).encode()
    secret = _load_secret(root)
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()


def verify_record(root: Path, run_id: str) -> tuple[bool, str]:
    """Verify HMAC signature of a lineage record. Returns (ok, detail)."""
    entry = _load_record(root, run_id)
    if entry is None:
        return False, f"Record not found: {run_id}"
    stored_sig = entry.get("signature")
    if not stored_sig:
        return False, "No signature present — record predates tamper-evident lineage"
    expected = _sign(entry, root)
    if hmac.compare_digest(stored_sig, expected):
        return True, "Signature valid"
    return False, "Signature mismatch — record may have been tampered with"


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------

def hash_content(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()[:16]


def hash_data(data: Any) -> str:
    serialized = json.dumps(data, sort_keys=True, default=str)
    return "sha256:" + hashlib.sha256(serialized.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def record(root: Path, trace: dict) -> None:
    """Persist a lineage record extracted from a completed trace."""
    lineage_dir = root / LINEAGE_DIR
    lineage_dir.mkdir(exist_ok=True)

    entry = {
        "run_id": trace["run_id"],
        "parent_run_id": trace.get("parent_run_id"),
        "trace_id": trace.get("trace_id", trace["run_id"]),
        "agent": trace.get("agent"),
        "model": trace.get("model"),
        "provider": trace.get("provider"),
        "prompt_template": trace.get("prompt_template"),
        "prompt_hash": trace.get("prompt_hash"),
        "input_hash": trace.get("input_hash"),
        "output_hash": trace.get("output_hash"),
        "started_at": trace.get("started_at"),
        "finished_at": trace.get("finished_at"),
        "duration_ms": trace.get("duration_ms"),
        "status": trace.get("status"),
        "tokens": trace.get("tokens"),
        "cost_usd": trace.get("cost_usd"),
        "context": trace.get("context", {}),
        "retrieval_chunks": trace.get("retrieval_chunks", []),
        "tool_calls": trace.get("tool_calls", []),
    }
    entry["signature"] = _sign(entry, root)

    (lineage_dir / f"{trace['run_id']}.json").write_text(json.dumps(entry, indent=2))


def _load_record(root: Path, run_id: str) -> dict | None:
    """Load a lineage record, falling back to raw trace if not found."""
    path = root / LINEAGE_DIR / f"{run_id}.json"
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    trace_path = root / "traces" / f"{run_id}.json"
    if trace_path.exists():
        try:
            return json.loads(trace_path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    return None


# ---------------------------------------------------------------------------
# Chain reconstruction
# ---------------------------------------------------------------------------

def chain(root: Path, run_id: str) -> list[dict]:
    """Walk parent_run_id links to reconstruct the full call chain, root first."""
    records: list[dict] = []
    current_id: str | None = run_id
    seen: set[str] = set()

    while current_id and current_id not in seen:
        seen.add(current_id)
        r = _load_record(root, current_id)
        if r is None:
            break
        records.insert(0, r)
        current_id = r.get("parent_run_id")

    return records


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(
    root: Path,
    agent: str | None = None,
    since: str | None = None,
    status: str | None = None,
    prompt_hash: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Search lineage records with optional filters."""
    lineage_dir = root / LINEAGE_DIR
    if not lineage_dir.exists():
        lineage_dir = root / "traces"
    if not lineage_dir.exists():
        return []

    since_dt: datetime | None = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=UTC)
        except ValueError:
            console.print(f"[yellow]Invalid --since date '{since}', ignoring.[/yellow]")

    results: list[dict] = []
    for path in sorted(lineage_dir.glob("*.json"), reverse=True):
        if len(results) >= limit:
            break
        try:
            r = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue

        if agent and r.get("agent") != agent:
            continue
        if status and r.get("status") != status:
            continue
        if prompt_hash and r.get("prompt_hash") != prompt_hash:
            continue
        if since_dt:
            started = r.get("started_at", "")
            if not started:
                continue
            try:
                ts = datetime.fromisoformat(started.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                if ts < since_dt:
                    continue
            except ValueError:
                continue

        results.append(r)

    return results


# ---------------------------------------------------------------------------
# Compliance export
# ---------------------------------------------------------------------------

def export_compliance(root: Path, run_id: str) -> dict:
    """Generate a structured compliance export for a run and its full chain."""
    records = chain(root, run_id)
    if not records:
        return {}

    agents = list({r.get("agent") for r in records if r.get("agent")})
    models = list({r.get("model") for r in records if r.get("model")})
    providers = list({r.get("provider") for r in records if r.get("provider")})
    total_tokens = sum((r.get("tokens") or {}).get("total", 0) for r in records)
    total_cost = sum(r.get("cost_usd") or 0.0 for r in records)
    total_duration = sum(r.get("duration_ms") or 0 for r in records)
    retrieval_sources = list({
        c.get("source")
        for r in records
        for c in r.get("retrieval_chunks", [])
        if c.get("source")
    })

    return {
        "export_timestamp": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "chain_depth": len(records),
        "summary": {
            "agents_involved": agents,
            "models_used": models,
            "providers_used": providers,
            "total_duration_ms": total_duration,
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 8),
            "all_succeeded": all(r.get("status") == "success" for r in records),
            "prompt_hashes": [r.get("prompt_hash") for r in records if r.get("prompt_hash")],
            "retrieval_sources": retrieval_sources,
        },
        "chain": records,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def show_chain(root: Path, run_id: str) -> None:
    records = chain(root, run_id)
    if not records:
        console.print(f"[red]No lineage record found for run '{run_id}'.[/red]")
        return

    tree = Tree(f"[bold cyan]Lineage chain for[/bold cyan] [bold]{run_id}[/bold]")

    for i, r in enumerate(records, 1):
        status_color = "green" if r.get("status") == "success" else "red"
        status_icon = "✓" if r.get("status") == "success" else "✗"
        duration = f"{r.get('duration_ms', '?')}ms"
        cost = f"${r.get('cost_usd', 0):.6f}" if r.get("cost_usd") is not None else "—"

        node_label = (
            f"[{status_color}]{status_icon}[/{status_color}] "
            f"[bold]{r.get('agent', '?')}[/bold] "
            f"[dim]{r.get('model', '?')} | {duration} | {cost}[/dim]"
        )
        node = tree.add(node_label)

        if r.get("prompt_template"):
            ph = r.get("prompt_hash", "—")
            node.add(f"[yellow]prompt:[/yellow] {r['prompt_template']} [dim]{ph}[/dim]")
        if r.get("input_hash"):
            node.add(f"[dim]input: {r['input_hash']}[/dim]")
        if r.get("output_hash"):
            node.add(f"[dim]output: {r['output_hash']}[/dim]")
        tokens = r.get("tokens")
        if tokens:
            node.add(f"[dim]tokens: {tokens.get('input', 0)} in / {tokens.get('output', 0)} out[/dim]")
        for chunk in r.get("retrieval_chunks", []):
            source = chunk.get("source", "unknown")
            score = chunk.get("score")
            score_str = f" score={score:.2f}" if score is not None else ""
            node.add(f"[magenta]chunk:[/magenta] {source}{score_str}")
        for tc in r.get("tool_calls", []):
            ok = "[green]✓[/green]" if tc.get("success") else "[red]✗[/red]"
            node.add(f"[green]tool:[/green] {tc.get('tool', '?')} {ok}")

    console.print(tree)

    total_cost = sum(r.get("cost_usd") or 0.0 for r in records)
    total_tokens = sum((r.get("tokens") or {}).get("total", 0) for r in records)
    total_ms = sum(r.get("duration_ms") or 0 for r in records)
    console.print(
        f"\n[dim]Chain: {len(records)} step(s) | "
        f"{total_ms}ms total | "
        f"{total_tokens} tokens | "
        f"${total_cost:.6f}[/dim]"
    )


def show_search(
    root: Path,
    agent: str | None,
    since: str | None,
    status: str | None,
    limit: int,
) -> None:
    results = search(root, agent=agent, since=since, status=status, limit=limit)
    if not results:
        console.print("[yellow]No lineage records found.[/yellow]")
        return

    table = Table(title="Lineage Records", header_style="bold")
    table.add_column("Run ID", style="cyan")
    table.add_column("Agent")
    table.add_column("Model", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Duration", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Prompt Hash", style="dim")
    table.add_column("Started")

    for r in results:
        status_val = r.get("status", "—")
        color = "green" if status_val == "success" else "red"
        cost = f"${r.get('cost_usd', 0):.6f}" if r.get("cost_usd") is not None else "—"
        table.add_row(
            r.get("run_id", "—"),
            r.get("agent", "—"),
            r.get("model", "—"),
            f"[{color}]{status_val}[/{color}]",
            f"{r.get('duration_ms', '?')}ms" if r.get("duration_ms") else "—",
            cost,
            (r.get("prompt_hash") or "—")[:20],
            (r.get("started_at") or "—")[:19].replace("T", " "),
        )

    console.print(table)


def show_verify(root: Path, run_ids: list[str]) -> bool:
    """Verify signatures for given run IDs (or all if empty). Returns True if all pass."""
    if not run_ids:
        lineage_dir = root / LINEAGE_DIR
        if not lineage_dir.exists():
            console.print("[yellow]No lineage records found.[/yellow]")
            return True
        run_ids = [p.stem for p in sorted(lineage_dir.glob("*.json"))]

    if not run_ids:
        console.print("[yellow]No lineage records to verify.[/yellow]")
        return True

    all_ok = True
    for rid in run_ids:
        ok, detail = verify_record(root, rid)
        if ok:
            console.print(f"[green]✓[/green] {rid} — {detail}")
        else:
            console.print(f"[red]✗[/red] {rid} — {detail}")
            all_ok = False

    return all_ok


def show_diff(root: Path, run_a: str, run_b: str) -> None:
    """Compare two runs side by side."""
    ra = _load_record(root, run_a)
    rb = _load_record(root, run_b)

    if ra is None:
        console.print(f"[red]Run '{run_a}' not found.[/red]")
        return
    if rb is None:
        console.print(f"[red]Run '{run_b}' not found.[/red]")
        return

    table = Table(title=f"Diff: {run_a} vs {run_b}", header_style="bold")
    table.add_column("Field", style="dim")
    table.add_column(run_a, style="cyan")
    table.add_column(run_b, style="cyan")
    table.add_column("", justify="center")

    def _row(field: str, key: str, formatter=None):
        va = ra.get(key)
        vb = rb.get(key)
        if formatter:
            sa = formatter(va) if va is not None else "—"
            sb = formatter(vb) if vb is not None else "—"
        else:
            sa = str(va) if va is not None else "—"
            sb = str(vb) if vb is not None else "—"
        marker = "[green]=[/green]" if sa == sb else "[yellow]≠[/yellow]"
        table.add_row(field, sa, sb, marker)

    _row("agent", "agent")
    _row("model", "model")
    _row("provider", "provider")
    _row("status", "status")
    _row("prompt_template", "prompt_template")
    _row("prompt_hash", "prompt_hash")
    _row("input_hash", "input_hash")
    _row("output_hash", "output_hash")

    tokens_a = ra.get("tokens") or {}
    tokens_b = rb.get("tokens") or {}
    in_a, in_b = tokens_a.get("input", 0), tokens_b.get("input", 0)
    out_a, out_b = tokens_a.get("output", 0), tokens_b.get("output", 0)

    def _delta(a, b):
        if a == b:
            return "[green]=[/green]"
        pct = ((b - a) / a * 100) if a else float("inf")
        arrow = "↑" if b > a else "↓"
        return f"[yellow]{arrow}{abs(pct):.0f}%[/yellow]"

    table.add_row("tokens (in)", str(in_a), str(in_b), _delta(in_a, in_b))
    table.add_row("tokens (out)", str(out_a), str(out_b), _delta(out_a, out_b))

    cost_a = ra.get("cost_usd") or 0.0
    cost_b = rb.get("cost_usd") or 0.0
    table.add_row(
        "cost",
        f"${cost_a:.6f}",
        f"${cost_b:.6f}",
        _delta(cost_a, cost_b) if cost_a else "—",
    )

    dur_a = ra.get("duration_ms") or 0
    dur_b = rb.get("duration_ms") or 0
    table.add_row(
        "duration",
        f"{dur_a}ms",
        f"{dur_b}ms",
        _delta(dur_a, dur_b) if dur_a else "—",
    )

    console.print(table)
