from __future__ import annotations

from pathlib import Path

from rich import print as rprint
from rich.tree import Tree

from ryva.utils import console, load_manifest, parse_ref


def show_dag(root: Path, agent_name: str | None = None):
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})
    tools = manifest.get("tools", {})

    if agent_name and agent_name not in agents:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        console.print(f"Available: {', '.join(agents.keys())}")
        return

    targets = {agent_name: agents[agent_name]} if agent_name else agents

    for name, agent in targets.items():
        tree = Tree(f"[bold cyan]agent:[/bold cyan] [bold]{name}[/bold] [dim]v{agent.get('version','?')}[/dim]")

        if agent.get("prompt"):
            try:
                _, prompt_name = parse_ref(agent["prompt"])
                tree.add(f"[yellow]prompt:[/yellow] {prompt_name}")
            except Exception:
                tree.add(f"[yellow]prompt:[/yellow] {agent['prompt']}")

        for tool_ref in agent.get("tools", []):
            try:
                _, tool_name = parse_ref(tool_ref)
                tool = tools.get(tool_name, {})
                branch = tree.add(f"[green]tool:[/green] {tool_name} [dim]v{tool.get('version','?')}[/dim]")
                if tool.get("description"):
                    branch.add(f"[dim]{tool['description']}[/dim]")
            except Exception:
                tree.add(f"[green]tool:[/green] {tool_ref}")

        if agent.get("input", {}) and agent["input"].get("schema"):
            inp = tree.add("[magenta]input[/magenta]")
            for field, spec in agent["input"]["schema"].items():
                inp.add(f"[dim]{field}:[/dim] {spec.get('type','any')}")

        if agent.get("output", {}) and agent["output"].get("schema"):
            out = tree.add("[magenta]output[/magenta]")
            for field, spec in agent["output"]["schema"].items():
                out.add(f"[dim]{field}:[/dim] {spec.get('type','any')}")

        rprint(tree)
        console.print()
