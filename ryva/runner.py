from __future__ import annotations
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from ryva.utils import load_manifest, parse_ref, console
from rich.panel import Panel
from rich.syntax import Syntax


def run_agent(root: Path, agent_name: str, input_data: dict) -> dict:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})

    if agent_name not in agents:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        console.print(f"Available: {', '.join(agents.keys())}")
        raise SystemExit(1)

    agent = agents[agent_name]
    project = manifest.get("project", {})

    console.print(Panel(f"[bold cyan]Running agent:[/bold cyan] [bold]{agent_name}[/bold]", expand=False))
    console.print(f"[dim]Input: {json.dumps(input_data, indent=2)}[/dim]\n")

    # Resolve prompt
    prompt_text = _resolve_prompt(root, agent, input_data)

    # Resolve provider
    provider_name, model, provider = _resolve_provider(project, agent)

    # Call LLM
    start = time.time()
    console.print(f"[dim]Calling {provider_name} / {model}...[/dim]")

    max_tokens = project.get("runtime", {}).get("max_tokens", 4096)
    result = provider.complete(prompt_text, model, max_tokens)

    elapsed = int((time.time() - start) * 1000)

    # Parse output
    output = _parse_output(result)

    # Log run
    run_id = str(uuid.uuid4())[:8]
    _save_run(root, run_id, agent_name, input_data, output, elapsed)

    console.print(f"\n[bold green]✓ Done[/bold green] in [cyan]{elapsed}ms[/cyan] [dim](run-id: {run_id})[/dim]\n")
    console.print(Panel(
        Syntax(json.dumps(output, indent=2), "json", theme="monokai"),
        title="Output",
        border_style="green"
    ))

    return output


def _resolve_prompt(root: Path, agent: dict, input_data: dict) -> str:
    prompt_ref = agent.get("prompt")
    if not prompt_ref:
        return json.dumps(input_data)

    try:
        _, prompt_name = parse_ref(prompt_ref)
    except ValueError:
        prompt_name = prompt_ref

    prompt_path = root / "prompts" / f"{prompt_name}.j2"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_path}")

    macros_path = root / "macros"
    loader_paths = [str(root / "prompts")]
    if macros_path.exists():
        loader_paths.append(str(macros_path))

    env = Environment(
        loader=FileSystemLoader(loader_paths),
        keep_trailing_newline=True
    )
    template = env.get_template(f"{prompt_name}.j2")
    return template.render(input=input_data)


def _resolve_provider(project: dict, agent: dict):
    from ryva.providers import get_provider

    providers = project.get("providers", {})
    default = providers.get("default", "anthropic")
    provider_cfg = providers.get(default, {})

    model = agent.get("model") or provider_cfg.get("model", "claude-sonnet-4-5")
    provider = get_provider(default, provider_cfg)

    return default, model, provider


def _parse_output(text: str) -> dict:
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"raw_output": text}


def _save_run(root: Path, run_id: str, agent: str, input_data: dict, output: dict, elapsed_ms: int):
    runs_dir = root / "logs" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id,
        "agent": agent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": elapsed_ms,
        "input": input_data,
        "output": output,
    }
    (runs_dir / f"{run_id}.json").write_text(json.dumps(run, indent=2))