from __future__ import annotations

import json
from pathlib import Path

from rich.panel import Panel
from rich.table import Table

from ryva.cost_tracker import calculate_cost
from ryva.utils import console, load_manifest, load_yaml

# Model tiers from cheapest/smallest to most capable
MODEL_TIERS = {
    "anthropic": [
        {"name": "claude-haiku-4-5", "tier": "small", "cost_rank": 1},
        {"name": "claude-sonnet-4-5", "tier": "medium", "cost_rank": 2},
        {"name": "claude-opus-4-5", "tier": "large", "cost_rank": 3},
    ],
    "openai": [
        {"name": "gpt-4o-mini", "tier": "small", "cost_rank": 1},
        {"name": "gpt-4o", "tier": "medium", "cost_rank": 2},
        {"name": "gpt-4-turbo", "tier": "large", "cost_rank": 3},
    ],
    "gemini": [
        {"name": "gemini-1.5-flash", "tier": "small", "cost_rank": 1},
        {"name": "gemini-1.5-pro", "tier": "medium", "cost_rank": 2},
    ],
    "ollama": [
        {"name": "llama3", "tier": "small", "cost_rank": 0},
        {"name": "mistral", "tier": "medium", "cost_rank": 0},
    ]
}


def run_compat_tests(
    root: Path,
    agent_name: str | None = None,
    provider: str = "anthropic"
) -> bool:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})
    targets = (
        {agent_name: agents[agent_name]}
        if agent_name and agent_name in agents
        else agents
    )

    if not targets:
        console.print("[red]No agents found.[/red]")
        return False

    all_passed = True

    for name, agent in targets.items():
        console.print(Panel(
            f"[bold cyan]Compatibility Test:[/bold cyan] [bold]{name}[/bold]\n"
            f"[dim]Testing across {provider} model tiers[/dim]",
            expand=False
        ))

        test_dir = root / "tests" / name
        if not test_dir.exists():
            console.print(f"[dim]No tests found for '{name}' — skipping compat test[/dim]")
            continue

        # Load test cases
        test_cases = []
        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            for case in test_data.get("cases", []):
                test_cases.append({
                    "name": case.get("name", test_file.stem),
                    "input": case.get("input", {}),
                    "expect": case.get("expect", {})
                })

        if not test_cases:
            console.print(f"[dim]No test cases found for '{name}'[/dim]")
            continue

        models = MODEL_TIERS.get(provider, [])
        results = []

        for model_info in models:
            model_name = model_info["name"]
            tier = model_info["tier"]
            console.print(f"\n[dim]Testing with {model_name} ({tier})...[/dim]")

            model_results = []
            for case in test_cases:
                passed, detail, cost = _run_compat_case(
                    root, agent, case, provider, model_name,
                    manifest.get("project", {})
                )
                model_results.append({
                    "case": case["name"],
                    "passed": passed,
                    "detail": detail,
                    "cost": cost
                })

            pass_count = sum(1 for r in model_results if r["passed"])
            total = len(model_results)
            pass_rate = pass_count / total if total > 0 else 0
            avg_cost = sum(r["cost"] for r in model_results) / total if total > 0 else 0

            results.append({
                "model": model_name,
                "tier": tier,
                "pass_rate": pass_rate,
                "passed": pass_count,
                "total": total,
                "avg_cost": avg_cost,
                "details": model_results
            })

            if pass_rate < 1.0:
                all_passed = False

        _print_compat_report(name, results)

    return all_passed


def _run_compat_case(
    root: Path,
    agent: dict,
    case: dict,
    provider: str,
    model: str,
    project: dict
) -> tuple[bool, str, float]:
    import re

    from jinja2 import Environment, FileSystemLoader

    from ryva.providers import get_provider
    from ryva.tester import _check_schema
    from ryva.utils import parse_ref

    try:
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

                macro_imports = []
                if macros_path.exists():
                    for macro_file in macros_path.glob("*.j2"):
                        macro_text = macro_file.read_text()
                        names = re.findall(
                            r'\{%-?\s*macro\s+(\w+)\s*\(', macro_text
                        )
                        if names:
                            macro_imports.append(
                                f"{{% from '{macro_file.name}' import {', '.join(names)} %}}"
                            )

                raw = prompt_path.read_text()
                full_template = "\n".join(macro_imports) + "\n" + raw
                template = env.from_string(full_template)
                prompt = template.render(input=case["input"])
            else:
                prompt = json.dumps(case["input"])
        else:
            prompt = json.dumps(case["input"])

        # Get provider
        providers_cfg = project.get("providers", {})
        provider_cfg = {**providers_cfg.get(provider, {}), "model": model}
        llm_provider = get_provider(provider, provider_cfg)
        max_tokens = project.get("runtime", {}).get("max_tokens", 4096)

        result_text = llm_provider.complete(prompt, model, max_tokens)

        # Parse output
        output = {}
        match = re.search(r'\{[\s\S]*\}', result_text)
        if match:
            try:
                output = json.loads(match.group())
            except json.JSONDecodeError:
                output = {"raw_output": result_text}
        else:
            output = {"raw_output": result_text}

        # Estimate cost
        input_tokens = int(len(prompt.split()) * 1.3)
        output_tokens = int(len(result_text.split()) * 1.3)
        cost = calculate_cost(provider, model, input_tokens, output_tokens)

        # Check schema
        expect = case.get("expect", {})
        if expect:
            passed, detail = _check_schema(output, expect)
        else:
            passed, detail = True, "No schema check"

        return passed, detail, cost

    except Exception as e:
        return False, str(e)[:80], 0.0


def _print_compat_report(agent_name: str, results: list):
    console.print(f"\n[bold]Compatibility Report — {agent_name}[/bold]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Model", style="cyan")
    table.add_column("Tier", style="dim")
    table.add_column("Pass Rate", justify="center")
    table.add_column("Tests", justify="center")
    table.add_column("Avg Cost", justify="right")
    table.add_column("Verdict", justify="center")

    best_model = None
    for r in results:
        if r["pass_rate"] == 1.0:
            if best_model is None:
                best_model = r

    for r in results:
        pass_color = "green" if r["pass_rate"] == 1.0 else "yellow" if r["pass_rate"] >= 0.5 else "red"
        verdict = ""
        if r == best_model:
            verdict = "[green]✓ recommended[/green]"
        elif r["pass_rate"] == 1.0:
            verdict = "[green]✓ compatible[/green]"
        elif r["pass_rate"] >= 0.5:
            verdict = "[yellow]⚠ partial[/yellow]"
        else:
            verdict = "[red]✗ incompatible[/red]"

        table.add_row(
            r["model"],
            r["tier"],
            f"[{pass_color}]{r['pass_rate']:.0%}[/{pass_color}]",
            f"{r['passed']}/{r['total']}",
            f"${r['avg_cost']:.6f}",
            verdict
        )

    console.print(table)

    if best_model:
        savings = None
        large_model = next(
            (r for r in results if r["tier"] == "large"), None
        )
        if large_model and best_model["avg_cost"] < large_model["avg_cost"]:
            if large_model["avg_cost"] > 0:
                savings_pct = (
                    1 - best_model["avg_cost"] / large_model["avg_cost"]
                ) * 100
                savings = f"{savings_pct:.0f}%"

        console.print(
            f"\n[bold green]✓ Recommended:[/bold green] "
            f"[cyan]{best_model['model']}[/cyan] "
            f"({best_model['tier']}) passes all tests"
            + (f" — [yellow]{savings} cheaper[/yellow] than the large model" if savings else "")
        )
