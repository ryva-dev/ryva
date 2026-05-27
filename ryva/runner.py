from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from rich.panel import Panel
from rich.syntax import Syntax

from ryva.lineage import hash_content, hash_data
from ryva.logger import get as get_logger
from ryva.utils import console, load_manifest, parse_ref

logger = get_logger("runner")


def run_agent(
    root: Path,
    agent_name: str,
    input_data: dict,
    parent_run_id: str | None = None,
    trace_id: str | None = None,
    context: dict | None = None,
) -> dict:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})

    if agent_name not in agents:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        console.print(f"Available: {', '.join(agents.keys())}")
        raise SystemExit(1)

    agent = agents[agent_name]
    project = manifest.get("project", {})

    # Check budget before running
    from ryva.cost_tracker import check_budget
    budget_warnings = check_budget(root, project)
    for warning in budget_warnings:
        console.print(warning)
    if any("EXCEEDED" in w for w in budget_warnings):
        console.print("[dim]Run blocked due to budget limit. Update budget.monthly_limit_usd in project.yml to continue.[/dim]")
        raise SystemExit(1)

    console.print(Panel(f"[bold cyan]Running agent:[/bold cyan] [bold]{agent_name}[/bold]", expand=False))

    # Mask PII in input before logging or passing to prompt
    from ryva.pii_masker import apply_if_enabled as _pii
    safe_input, input_findings = _pii(json.dumps(input_data), project)
    if input_findings:
        console.print(f"[dim]PII masked in input: {len(input_findings)} item(s)[/dim]")
        import json as _json
        try:
            input_data = _json.loads(safe_input)
        except Exception:
            pass

    console.print(f"[dim]Input: {json.dumps(input_data, indent=2)}[/dim]\n")

    # Resolve prompt and provider
    prompt_text = _resolve_prompt(root, agent, input_data)
    provider_name, model, provider = _resolve_provider(project, agent)

    # Compute content hashes for lineage
    prompt_hash = hash_content(prompt_text)
    input_hash = hash_data(input_data)
    prompt_template = agent.get("prompt", "")

    # Start trace
    from ryva.tracer import add_step, finish_trace, start_trace
    trace = start_trace(
        root, agent_name, model, provider_name,
        parent_run_id=parent_run_id,
        trace_id=trace_id,
        context=context or {},
    )
    trace["prompt_template"] = prompt_template
    trace["prompt_hash"] = prompt_hash
    trace["input_hash"] = input_hash
    add_step(trace, "prompt", {"content": prompt_text})

    # Call LLM
    start = time.time()
    console.print(f"[dim]Calling {provider_name} / {model}...[/dim]")
    max_tokens = project.get("runtime", {}).get("max_tokens", 4096)
    result, usage = provider.complete_with_usage(prompt_text, model, max_tokens)
    elapsed = int((time.time() - start) * 1000)

    # Calculate cost
    from ryva.cost_tracker import calculate_cost, load_pricing
    pricing = load_pricing(root)
    cost = calculate_cost(
        provider_name, model,
        usage["input_tokens"], usage["output_tokens"],
        pricing,
    )

    # Parse output and hash it
    output = _parse_output(result)
    output_hash = hash_data(output)

    # Attach lineage metadata to trace before finishing
    trace["output_hash"] = output_hash
    trace["tokens"] = {
        "input": usage["input_tokens"],
        "output": usage["output_tokens"],
        "total": usage["input_tokens"] + usage["output_tokens"],
    }
    trace["cost_usd"] = cost

    # Record trace
    add_step(trace, "response", {"content": result, "duration_ms": elapsed})
    run_id = finish_trace(root, trace)

    # Persist lineage record
    from ryva.lineage import record as record_lineage
    record_lineage(root, trace)

    # Mask PII in raw output before saving / displaying
    masked_result, output_findings = _pii(result, project)
    if output_findings:
        console.print(f"[dim]PII masked in output: {len(output_findings)} item(s)[/dim]")
        result = masked_result
        output = _parse_output(result)
        output_hash = hash_data(output)
        trace["output_hash"] = output_hash

    # Auto alignment check against project policies (non-blocking warnings only)
    from ryva.alignment import check_output, load_policies
    policies = load_policies(root, project)
    if policies:
        violations = check_output(result, policies)
        errors = [v for v in violations if v["severity"] == "error"]
        warnings = [v for v in violations if v["severity"] == "warning"]
        for v in warnings:
            console.print(f"[yellow]⚠ Alignment warning ({v['policy']}): {v['detail']}[/yellow]")
        for v in errors:
            console.print(f"[red]✗ Alignment violation ({v['policy']}): {v['detail']}[/red]")

    # Save run with token counts and cost
    _save_run(root, run_id, agent_name, provider_name, model,
              input_data, output, elapsed, usage, cost)

    logger.info(
        "agent=%s model=%s input_tokens=%d output_tokens=%d cost=$%.6f elapsed_ms=%d run_id=%s",
        agent_name, model,
        usage["input_tokens"], usage["output_tokens"],
        cost, elapsed, run_id,
    )

    console.print(f"\n[bold green]✓ Done[/bold green] in [cyan]{elapsed}ms[/cyan] "
                  f"[dim](run-id: {run_id}, cost: ${cost:.6f})[/dim]\n")
    console.print(Panel(
        Syntax(json.dumps(output, indent=2), "json", theme="monokai"),
        title="Output",
        border_style="green",
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

    loader_paths = [str(root / "prompts")]
    macros_path = root / "macros"
    if macros_path.exists():
        loader_paths.append(str(macros_path))

    env = Environment(
        loader=FileSystemLoader(loader_paths),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    macro_imports = []
    if macros_path.exists():
        for macro_file in macros_path.glob("*.j2"):
            macro_text = macro_file.read_text()
            names = re.findall(r'\{%-?\s*macro\s+(\w+)\s*\(', macro_text)
            if names:
                names_str = ", ".join(names)
                macro_imports.append(
                    f"{{% from '{macro_file.name}' import {names_str} %}}"
                )

    raw = prompt_path.read_text()
    full_template = "\n".join(macro_imports) + "\n" + raw if macro_imports else raw
    template = env.from_string(full_template)
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


def _save_run(
    root: Path,
    run_id: str,
    agent: str,
    provider: str,
    model: str,
    input_data: dict,
    output: dict,
    elapsed_ms: int,
    usage: dict,
    cost: float,
) -> None:
    runs_dir = root / "logs" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id,
        "agent": agent,
        "provider": provider,
        "model": model,
        "timestamp": datetime.now(UTC).isoformat(),
        "elapsed_ms": elapsed_ms,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "estimated_cost": cost,
        "input": input_data,
        "output": output,
    }
    (runs_dir / f"{run_id}.json").write_text(json.dumps(run, indent=2))
