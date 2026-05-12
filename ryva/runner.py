from __future__ import annotations
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from ryva.utils import load_manifest, resolve_env_vars, parse_ref, console
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
    provider, model, api_key = _resolve_provider(project, agent)

    # Call LLM
    start = time.time()
    console.print(f"[dim]Calling {provider} / {model}...[/dim]")

    if provider == "anthropic":
        result = _call_anthropic(api_key, model, prompt_text, project)
    elif provider == "openai":
        result = _call_openai(api_key, model, prompt_text, project)
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    elapsed = int((time.time() - start) * 1000)

    # Try to parse JSON output
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


def _resolve_provider(project: dict, agent: dict) -> tuple[str, str, str]:
    providers = project.get("providers", {})
    default = providers.get("default", "anthropic")
    provider_cfg = providers.get(default, {})

    model = model = agent.get("model") or provider_cfg.get("model", "claude-sonnet-4-5")
    api_key = resolve_env_vars(provider_cfg.get("api_key", ""))

    return default, model, api_key


def _call_anthropic(api_key: str, model: str, prompt: str, project: dict) -> str:
    try:
        import anthropic
    except ImportError:
        raise ImportError("Run: uv add anthropic")

    import os
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=key)
    max_tokens = project.get("runtime", {}).get("max_tokens", 4096)

    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return msg.content[0].text


def _call_openai(api_key: str, model: str, prompt: str, project: dict) -> str:
    try:
        import openai
    except ImportError:
        raise ImportError("Run: uv add openai")

    import os
    key = api_key or os.environ.get("OPENAI_API_KEY", "")
    client = openai.OpenAI(api_key=key)
    max_tokens = project.get("runtime", {}).get("max_tokens", 4096)

    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content


def _parse_output(text: str) -> dict:
    import re
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        try:
            return json.loads(json_match.group())
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