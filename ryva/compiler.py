from __future__ import annotations

import json
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from ryva.lineage import hash_content
from ryva.logger import get as get_logger
from ryva.resolver import ProjectResolver
from ryva.utils import console

logger = get_logger("compiler")


def compile_project(root: Path) -> bool:
    console.print(Panel("[bold cyan]Ryva Compile[/bold cyan]", expand=False))
    console.print(f"[dim]Project root: {root}[/dim]\n")

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
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2))

    if prompt_hashes:
        console.print(f"[dim]Hashed {len(prompt_hashes)} prompt template(s)[/dim]")
    console.print("[bold green]✓ Compiled successfully[/bold green]")
    console.print("[dim]Manifest written to target/manifest.json[/dim]")
    return True
