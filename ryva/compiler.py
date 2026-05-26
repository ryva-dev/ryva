from __future__ import annotations

import json
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from ryva.resolver import ProjectResolver
from ryva.utils import console


def compile_project(root: Path) -> bool:
    console.print(Panel("[bold cyan]Ryva Compile[/bold cyan]", expand=False))
    console.print(f"[dim]Project root: {root}[/dim]\n")

    resolver = ProjectResolver(root)
    resolver.resolve()

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

    # Write manifest
    target = root / "target"
    target.mkdir(exist_ok=True)
    manifest = resolver.to_manifest()
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))

    console.print("[bold green]✓ Compiled successfully[/bold green]")
    console.print("[dim]Manifest written to target/manifest.json[/dim]")
    return True
