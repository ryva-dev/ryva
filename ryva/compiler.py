from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from ryva.lineage import hash_content
from ryva.logger import get as get_logger
from ryva.resolver import ProjectResolver
from ryva.utils import console, load_yaml

logger = get_logger("compiler")

# Top-level keys that Ryva recognises in project.yml.
# Anything outside this set is flagged by --strict.
_KNOWN_PROJECT_KEYS = {
    "name", "version", "description", "providers", "runtime", "targets",
    "pii_masking", "budget", "policies", "cloud", "default_agent",
    "log_level", "output_dir",
}


def validate_project_config(config: dict, strict: bool = False) -> list[str]:
    """Return a list of warning strings for unknown top-level keys.

    In strict mode raises ValueError instead of returning warnings.
    """
    unknown = set(config.keys()) - _KNOWN_PROJECT_KEYS
    if not unknown:
        return []
    msg = f"Unknown config keys in project.yml: {', '.join(sorted(unknown))}"
    if strict:
        raise ValueError(f"{msg}\nRun without --strict to treat these as warnings.")
    return [f"Warning: {msg}"]


def detect_and_record_changes(old_manifest: dict, new_manifest: dict) -> list[dict]:
    """Compare two manifests and return a list of structured change records."""
    changes = []
    now = datetime.now(UTC).isoformat()

    for agent_name, new_agent in new_manifest.get("agents", {}).items():
        old_agent = old_manifest.get("agents", {}).get(agent_name)

        if not old_agent:
            changes.append({
                "id": str(uuid.uuid4())[:8],
                "type": "AGENT_REGISTERED",
                "severity": "info",
                "agent": agent_name,
                "description": f"AI system '{agent_name}' registered for the first time",
                "requires_review": False,
                "timestamp": now,
            })
            continue

        if old_agent.get("prompt_hash") != new_agent.get("prompt_hash"):
            old_h = old_agent.get("prompt_hash") or "unknown"
            new_h = new_agent.get("prompt_hash") or "unknown"
            changes.append({
                "id": str(uuid.uuid4())[:8],
                "type": "PROMPT_CHANGE",
                "severity": "high",
                "agent": agent_name,
                "description": (
                    f"Prompt changed from {old_h[:8]} to {new_h[:8]}"
                ),
                "old_value": old_agent.get("prompt_hash"),
                "new_value": new_agent.get("prompt_hash"),
                "requires_review": True,
                "compliance_note": (
                    "Prompt changes may affect system behavior and compliance. "
                    "Compliance re-review required before next production run."
                ),
                "timestamp": now,
            })

        if old_agent.get("model") != new_agent.get("model"):
            changes.append({
                "id": str(uuid.uuid4())[:8],
                "type": "MODEL_CHANGE",
                "severity": "high",
                "agent": agent_name,
                "description": (
                    f"Model changed from {old_agent.get('model', 'unknown')} "
                    f"to {new_agent.get('model', 'unknown')}"
                ),
                "old_value": old_agent.get("model"),
                "new_value": new_agent.get("model"),
                "requires_review": True,
                "compliance_note": (
                    "Model changes require re-validation of test results and "
                    "compliance evidence. Governance re-review required."
                ),
                "timestamp": now,
            })

        if old_agent.get("version") != new_agent.get("version"):
            changes.append({
                "id": str(uuid.uuid4())[:8],
                "type": "VERSION_BUMP",
                "severity": "low",
                "agent": agent_name,
                "description": (
                    f"Version bumped from {old_agent.get('version')} "
                    f"to {new_agent.get('version')}"
                ),
                "requires_review": False,
                "timestamp": now,
            })

    return changes


def save_change_history(changes: list[dict], root: Path) -> None:
    """Append changes to target/change_history.json."""
    history_file = root / "target" / "change_history.json"
    existing: list = []
    if history_file.exists():
        try:
            existing = json.loads(history_file.read_text())
        except Exception:
            pass
    existing.extend(changes)
    history_file.write_text(json.dumps(existing, indent=2))


def compile_project(root: Path, strict: bool = False) -> bool:
    console.print(Panel("[bold cyan]Ryva Compile[/bold cyan]", expand=False))
    console.print(f"[dim]Project root: {root}[/dim]\n")

    # Validate raw config keys before schema parsing
    project_yml = root / "project.yml"
    if project_yml.exists():
        raw_config = load_yaml(project_yml) or {}
        try:
            cfg_warnings = validate_project_config(raw_config, strict)
            for w in cfg_warnings:
                console.print(f"[yellow]{w}[/yellow]")
        except ValueError as exc:
            console.print(f"[bold red]Strict mode error:[/bold red] {exc}")
            return False

    # Load old manifest for change tracking
    old_manifest: dict = {}
    manifest_path = root / "target" / "manifest.json"
    if manifest_path.exists():
        try:
            old_manifest = json.loads(manifest_path.read_text())
        except Exception:
            pass

    resolver = ProjectResolver(root)
    resolver.resolve()
    logger.info(
        "project=%s agents=%d tools=%d pipelines=%d errors=%d",
        root.name,
        len(resolver.agents),
        len(resolver.tools),
        len(resolver.pipelines),
        len(resolver.errors),
    )

    # Summary table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right")
    table.add_row("Agents", str(len(resolver.agents)))
    table.add_row("Tools", str(len(resolver.tools)))
    table.add_row("Pipelines", str(len(resolver.pipelines)))
    console.print(table)
    console.print()

    if resolver.errors:
        console.print("[bold red]Compilation failed with errors:[/bold red]")
        for err in resolver.errors:
            console.print(f"  [red]✗[/red] {err}")
        return False

    # Hash all prompt templates for lineage tracking
    prompt_hashes: dict[str, str] = {}
    prompts_dir = root / "prompts"
    if prompts_dir.exists():
        for p in sorted(prompts_dir.glob("*.j2")):
            prompt_hashes[p.stem] = hash_content(p.read_text())

    # Write manifest
    target = root / "target"
    target.mkdir(exist_ok=True)
    manifest = resolver.to_manifest()
    manifest["prompt_hashes"] = prompt_hashes

    # Enrich each agent entry with its prompt hash for change tracking
    for agent_name, agent_data in manifest.get("agents", {}).items():
        prompt_ref = agent_data.get("prompt", "")
        if prompt_ref:
            # Extract stem from refs like "ref(prompts/summarizer)" or "summarizer"
            stem = prompt_ref.split("/")[-1].rstrip(")")
            if stem in prompt_hashes:
                agent_data["prompt_hash"] = prompt_hashes[stem]

    manifest_path.write_text(json.dumps(manifest, indent=2))

    # Detect and record changes since last compile
    changes = detect_and_record_changes(old_manifest, manifest)
    if changes:
        save_change_history(changes, root)
        for c in changes:
            icon = "⚠" if c.get("requires_review") else "ℹ"
            color = "yellow" if c.get("requires_review") else "dim"
            console.print(f"[{color}]{icon} {c['type']}: {c['description']}[/{color}]")
        review_needed = [c for c in changes if c.get("requires_review")]
        if review_needed:
            console.print(
                f"[yellow]⚠ {len(review_needed)} change(s) require compliance review "
                f"— run 'ryva changes --requires-review'[/yellow]"
            )

    if prompt_hashes:
        console.print(f"[dim]Hashed {len(prompt_hashes)} prompt template(s)[/dim]")
    console.print("[bold green]✓ Compiled successfully[/bold green]")
    console.print("[dim]Manifest written to target/manifest.json[/dim]")
    return True
