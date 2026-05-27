from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from jinja2 import Environment
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from ryva.runner import run_agent
from ryva.utils import console, load_manifest, parse_ref


def run_pipeline(root: Path, pipeline_name: str, input_data: dict) -> dict:
    manifest = load_manifest(root)
    pipelines = manifest.get("pipelines", {})

    if pipeline_name not in pipelines:
        console.print(f"[red]Pipeline '{pipeline_name}' not found.[/red]")
        console.print(f"Available: {', '.join(pipelines.keys())}")
        raise SystemExit(1)

    pipeline = pipelines[pipeline_name]
    steps = pipeline.get("steps", [])

    console.print(Panel(
        f"[bold cyan]Running pipeline:[/bold cyan] [bold]{pipeline_name}[/bold]",
        expand=False
    ))
    console.print(f"[dim]Input: {json.dumps(input_data, indent=2)}[/dim]\n")

    run_id = str(uuid.uuid4())[:8]
    trace_id = run_id  # shared across all steps in this pipeline run
    start = time.time()
    step_results = {}
    step_table_data = []
    prev_run_id: str | None = None

    for step in steps:
        step_name = step.get("name")
        agent_ref = step.get("agent")
        tool_ref = step.get("tool")
        step_input_template = step.get("input", {})

        console.print(f"[dim]Step: {step_name}[/dim]")

        # Resolve step input using Jinja2
        resolved_input = _resolve_step_input(
            step_input_template, input_data, step_results
        )

        step_start = time.time()

        try:
            if agent_ref:
                try:
                    _, agent_name = parse_ref(agent_ref)
                except ValueError:
                    agent_name = agent_ref

                output = run_agent(
                    root, agent_name, resolved_input,
                    parent_run_id=prev_run_id,
                    trace_id=trace_id,
                )
                # Capture the run_id from the returned output if available
                if isinstance(output, dict) and "run_id" not in output:
                    pass  # lineage is recorded inside run_agent
                prev_run_id = None  # reset; only chain explicitly sequential agents
                status = "success"

            elif tool_ref:
                try:
                    _, tool_name = parse_ref(tool_ref)
                except ValueError:
                    tool_name = tool_ref

                output = _run_tool(root, tool_name, resolved_input)
                status = "success"

            else:
                output = {}
                status = "skipped"

        except Exception as e:
            output = {"error": str(e)}
            status = "error"
            console.print(f"[red]Step '{step_name}' failed: {e}[/red]")

        step_elapsed = int((time.time() - step_start) * 1000)
        step_results[step_name] = {
            "input": resolved_input,
            "output": output,
            "status": status,
            "elapsed_ms": step_elapsed
        }
        step_table_data.append((step_name, status, step_elapsed))

    # Resolve pipeline output
    output_template = pipeline.get("output", {})
    final_output = _resolve_step_input(output_template, input_data, step_results)

    total_elapsed = int((time.time() - start) * 1000)

    # Print step summary
    table = Table(show_header=True, header_style="bold")
    table.add_column("Step", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")

    for step_name, status, elapsed in step_table_data:
        status_str = "[green]✓ success[/green]" if status == "success" else "[red]✗ error[/red]"
        table.add_row(step_name, status_str, f"{elapsed}ms")

    console.print(table)
    console.print(
        f"\n[bold green]✓ Pipeline done[/bold green] in "
        f"[cyan]{total_elapsed}ms[/cyan] "
        f"[dim](run-id: {run_id})[/dim]\n"
    )
    console.print(Panel(
        Syntax(json.dumps(final_output, indent=2), "json", theme="monokai"),
        title="Output",
        border_style="green"
    ))

    # Save run
    _save_pipeline_run(
        root, run_id, pipeline_name, input_data,
        step_results, final_output, total_elapsed
    )

    return {
        "run_id": run_id,
        "output": final_output,
        "steps": step_results,
        "elapsed_ms": total_elapsed
    }


def _resolve_step_input(
    template: dict, input_data: dict, step_results: dict
) -> dict:
    resolved = {}
    env = Environment()

    for key, value in template.items():
        if isinstance(value, str) and "{{" in value:
            try:
                t = env.from_string(value)
                resolved[key] = t.render(input=input_data, steps=step_results)
            except Exception:
                resolved[key] = value
        elif isinstance(value, (int, float, bool)):
            resolved[key] = value
        else:
            resolved[key] = value

    return resolved


def _run_tool(root: Path, tool_name: str, input_data: dict) -> dict:
    import importlib.util
    manifest = load_manifest(root)
    tools = manifest.get("tools", {})

    if tool_name not in tools:
        raise ValueError(f"Tool '{tool_name}' not found")

    tool = tools[tool_name]
    impl_path = root / tool.get("implementation", "")
    function_name = tool.get("function", "run")

    if not impl_path.exists():
        raise FileNotFoundError(f"Tool implementation not found: {impl_path}")

    spec = importlib.util.spec_from_file_location(tool_name, impl_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    fn = getattr(module, function_name)
    return fn(**input_data)


def _save_pipeline_run(
    root: Path, run_id: str, pipeline: str,
    input_data: dict, steps: dict, output: dict, elapsed_ms: int
):
    runs_dir = root / "logs" / "pipeline_runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id,
        "pipeline": pipeline,
        "timestamp": datetime.now(UTC).isoformat(),
        "elapsed_ms": elapsed_ms,
        "input": input_data,
        "steps": steps,
        "output": output,
    }
    (runs_dir / f"{run_id}.json").write_text(json.dumps(run, indent=2))
