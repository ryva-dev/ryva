from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.table import Table

console = Console()

REGISTRY_FILE = "model_registry.json"


def _load(root: Path) -> dict:
    path = root / REGISTRY_FILE
    if not path.exists():
        return {"models": {}}
    return json.loads(path.read_text())


def _save(root: Path, data: dict):
    path = root / REGISTRY_FILE
    path.write_text(json.dumps(data, indent=2))


def registry_list(root: Path):
    data = _load(root)
    models = data.get("models", {})

    if not models:
        console.print("[yellow]No models registered yet. Use 'ryva registry add' to register one.[/yellow]")
        return

    table = Table(title="Model Registry", header_style="bold")
    table.add_column("Name", style="cyan")
    table.add_column("Provider")
    table.add_column("Model ID", style="dim")
    table.add_column("Version", style="dim")
    table.add_column("Tags", style="dim")
    table.add_column("Registered")

    for name, m in models.items():
        table.add_row(
            name,
            m.get("provider", "—"),
            m.get("model_id", "—"),
            m.get("version", "—"),
            ", ".join(m.get("tags", [])) or "—",
            m.get("registered_at", "—")[:10],
        )

    console.print(table)


def registry_add(root: Path, name: str, provider: str, model_id: str, version: str, tags: list[str]):
    data = _load(root)
    data["models"][name] = {
        "provider": provider,
        "model_id": model_id,
        "version": version,
        "tags": tags,
        "registered_at": datetime.utcnow().isoformat(),
    }
    _save(root, data)
    console.print(f"[bold green]✓ Registered model '{name}'[/bold green]")


def registry_info(root: Path, name: str):
    data = _load(root)
    model = data.get("models", {}).get(name)

    if not model:
        console.print(f"[red]Model '{name}' not found in registry.[/red]")
        return

    console.print(f"\n[bold cyan]{name}[/bold cyan]")
    for k, v in model.items():
        val = ", ".join(v) if isinstance(v, list) else v
        console.print(f"  [dim]{k}:[/dim] {val}")


def registry_remove(root: Path, name: str):
    data = _load(root)
    if name not in data.get("models", {}):
        console.print(f"[red]Model '{name}' not found in registry.[/red]")
        return
    del data["models"][name]
    _save(root, data)
    console.print(f"[bold yellow]Removed model '{name}' from registry.[/bold yellow]")