from __future__ import annotations

import json
import time
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from ryva.cost_tracker import calculate_cost
from ryva.utils import console, load_manifest

PROVIDER_MODELS = {
    "anthropic": "claude-sonnet-4-5",
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-pro",
    "ollama": "llama3",
}


def compare_providers(
    root: Path,
    agent_name: str,
    input_data: dict,
    providers: list[str] | None = None,
    runs_per_provider: int = 3
) -> dict:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})

    if agent_name not in agents:
        console.print(f"[red]Agent '{agent_name}' not found.[/red]")
        raise SystemExit(1)

    agent = agents[agent_name]
    project = manifest.get("project", {})
    target_providers = providers or list(PROVIDER_MODELS.keys())

    console.print(Panel(
        f"[bold cyan]Provider Comparison:[/bold cyan] [bold]{agent_name}[/bold]\n"
        f"[dim]Providers: {', '.join(target_providers)} | Runs each: {runs_per_provider}[/dim]",
        expand=False
    ))

    results = {}

    for provider in target_providers:
        console.print(f"\n[dim]Testing {provider}...[/dim]")
        model = PROVIDER_MODELS.get(provider, "default")

        provider_results = []
        errors = 0

        for i in range(runs_per_provider):
            try:
                start = time.time()
                output = _run_with_provider(
                    root, agent, input_data, provider, model, project
                )
                elapsed = int((time.time() - start) * 1000)

                input_tokens = output.pop("_input_tokens", 0)
                output_tokens = output.pop("_output_tokens", 0)
                cost = calculate_cost(provider, model, input_tokens, output_tokens)

                provider_results.append({
                    "run": i + 1,
                    "elapsed_ms": elapsed,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cost": cost,
                    "output": output,
                    "success": True
                })
                console.print(
                    f"  Run {i+1}: [green]✓[/green] "
                    f"{elapsed}ms | "
                    f"${cost:.6f} | "
                    f"{input_tokens+output_tokens} tokens"
                )

            except Exception as e:
                errors += 1
                provider_results.append({
                    "run": i + 1,
                    "success": False,
                    "error": str(e)
                })
                console.print(f"  Run {i+1}: [red]✗[/red] {str(e)[:60]}")

            time.sleep(0.5)

        successful = [r for r in provider_results if r.get("success")]

        if successful:
            avg_latency = int(sum(r["elapsed_ms"] for r in successful) / len(successful))
            avg_cost = sum(r["cost"] for r in successful) / len(successful)
            avg_tokens = int(sum(
                r["input_tokens"] + r["output_tokens"] for r in successful
            ) / len(successful))
        else:
            avg_latency = avg_cost = avg_tokens = 0

        results[provider] = {
            "model": model,
            "runs": len(provider_results),
            "successful": len(successful),
            "errors": errors,
            "avg_latency_ms": avg_latency,
            "avg_cost": round(avg_cost, 6),
            "avg_tokens": avg_tokens,
            "details": provider_results
        }

    _print_comparison_report(agent_name, results, input_data)
    return results


def _run_with_provider(
    root: Path,
    agent: dict,
    input_data: dict,
    provider: str,
    model: str,
    project: dict
) -> dict:
    from jinja2 import Environment, FileSystemLoader

    from ryva.providers import get_provider
    from ryva.utils import parse_ref

    # Resolve prompt
    prompt_ref = agent.get("prompt")
    if prompt_ref:
        try:
            _, prompt_name = parse_ref(prompt_ref)
        except ValueError:
            prompt_name = prompt_ref

        prompt_path = root / "prompts" / f"{prompt_name}.j2"
        if prompt_path.exists():
            macros_path = root / "macros"
            loader_paths = [str(root / "prompts")]
            if macros_path.exists():
                loader_paths.append(str(macros_path))
            env = Environment(
                loader=FileSystemLoader(loader_paths),
                keep_trailing_newline=True,
                trim_blocks=True,
                lstrip_blocks=True,
            )

            import re
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
            full_template = "\n".join(macro_imports) + "\n" + raw
            template = env.from_string(full_template)
            prompt = template.render(input=input_data)
        else:
            prompt = json.dumps(input_data)
    else:
        prompt = json.dumps(input_data)

    # Get provider config
    providers_cfg = project.get("providers", {})
    provider_cfg = providers_cfg.get(provider, {})

    # Override model
    provider_cfg = {**provider_cfg, "model": model}

    llm_provider = get_provider(provider, provider_cfg)
    max_tokens = project.get("runtime", {}).get("max_tokens", 4096)

    result_text, usage = llm_provider.complete_with_usage(prompt, model, max_tokens)

    import re as re2
    output = {}
    match = re2.search(r'\{[\s\S]*\}', result_text)
    if match:
        try:
            output = json.loads(match.group())
        except json.JSONDecodeError:
            output = {"raw_output": result_text}
    else:
        output = {"raw_output": result_text}

    output["_input_tokens"] = usage.get("input_tokens", 0)
    output["_output_tokens"] = usage.get("output_tokens", 0)

    return output


def _print_comparison_report(
    agent_name: str,
    results: dict,
    input_data: dict
):
    console.print(f"\n[bold]Comparison Results — {agent_name}[/bold]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Provider", style="cyan")
    table.add_column("Model", style="dim")
    table.add_column("Success", justify="center")
    table.add_column("Avg Latency", justify="right")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Avg Tokens", justify="right")
    table.add_column("Winner", justify="center")

    # Find winners
    successful_providers = {
        p: r for p, r in results.items() if r["successful"] > 0
    }

    fastest = min(
        successful_providers,
        key=lambda p: successful_providers[p]["avg_latency_ms"],
        default=None
    )
    cheapest = min(
        successful_providers,
        key=lambda p: successful_providers[p]["avg_cost"],
        default=None
    )

    for provider, data in results.items():
        badges = []
        if provider == fastest:
            badges.append("[green]⚡ fastest[/green]")
        if provider == cheapest and provider != "ollama":
            badges.append("[yellow]💰 cheapest[/yellow]")
        if provider == "ollama" and data["successful"] > 0:
            badges.append("[blue]🏠 free[/blue]")

        success_rate = f"{data['successful']}/{data['runs']}"
        success_color = "green" if data["successful"] == data["runs"] else "yellow"

        table.add_row(
            provider,
            data["model"],
            f"[{success_color}]{success_rate}[/{success_color}]",
            f"{data['avg_latency_ms']}ms" if data["successful"] > 0 else "—",
            f"${data['avg_cost']:.6f}" if data["successful"] > 0 else "—",
            str(data["avg_tokens"]) if data["successful"] > 0 else "—",
            " ".join(badges) if badges else "—"
        )

    console.print(table)

    # Recommendation
    if successful_providers:
        console.print("\n[bold]Recommendation:[/bold]")
        if "ollama" in successful_providers and successful_providers["ollama"]["successful"] > 0:
            console.print(
                "  [blue]🏠 Ollama[/blue] is free — use it for development and testing"
            )
        if cheapest and cheapest != "ollama":
            cheap_data = successful_providers[cheapest]
            console.print(
                f"  [yellow]💰 {cheapest}[/yellow] is cheapest at "
                f"${cheap_data['avg_cost']:.6f}/run"
            )
        if fastest:
            fast_data = successful_providers[fastest]
            console.print(
                f"  [green]⚡ {fastest}[/green] is fastest at "
                f"{fast_data['avg_latency_ms']}ms avg"
            )
