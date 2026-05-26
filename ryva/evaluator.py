from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from rich.table import Table

from ryva.utils import console, load_manifest, load_yaml

DEFAULT_RUBRIC = """
You are an expert AI evaluator. Score the following agent output against the criteria below.

Agent: {agent_name}
Input: {input}
Output: {output}

Criteria:
{criteria}

Respond with a JSON object:
{{
  "score": <float between 0.0 and 1.0>,
  "reasoning": "<one sentence explanation>",
  "passed": <true if score >= threshold>
}}
"""


def run_evals(root: Path, agent_name: str | None = None) -> bool:
    manifest = load_manifest(root)
    agents = manifest.get("agents", {})
    targets = {agent_name: agents[agent_name]} if agent_name and agent_name in agents else agents

    if not targets:
        console.print("[red]No agents found.[/red]")
        return False

    all_passed = True
    results = []

    for name, agent in targets.items():
        eval_dir = root / "evals" / name
        if not eval_dir.exists():
            console.print(f"[dim]No evals found for agent '{name}' at evals/{name}/[/dim]")
            continue

        for eval_file in eval_dir.glob("*.yml"):
            eval_data = load_yaml(eval_file)
            cases = eval_data.get("cases", [])

            for case in cases:
                case_name = case.get("name", eval_file.stem)
                inp = case.get("input", {})
                criteria = case.get("criteria", "The output should be accurate and helpful.")
                threshold = case.get("threshold", 0.7)
                scorer = eval_data.get("scorer")

                score, reasoning, passed = _run_eval_case(
                    root, name, inp, criteria, threshold, scorer, manifest
                )
                results.append((name, case_name, score, passed, reasoning))
                if not passed:
                    all_passed = False

    _print_eval_results(results)
    return all_passed


def _run_eval_case(
    root: Path,
    agent_name: str,
    input_data: dict,
    criteria: str,
    threshold: float,
    scorer: str | None,
    manifest: dict,
) -> tuple[float, str, bool]:
    from ryva.runner import run_agent

    try:
        output = run_agent(root, agent_name, input_data)

        if scorer:
            return _run_custom_scorer(root, scorer, input_data, output, threshold)
        else:
            return _run_llm_scorer(
                agent_name, input_data, output, criteria, threshold, manifest
            )
    except Exception as e:
        return 0.0, str(e), False


def _run_llm_scorer(
    agent_name: str,
    input_data: dict,
    output: dict,
    criteria: str,
    threshold: float,
    manifest: dict,
) -> tuple[float, str, bool]:
    import os

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    prompt = DEFAULT_RUBRIC.format(
        agent_name=agent_name,
        input=json.dumps(input_data, indent=2),
        output=json.dumps(output, indent=2),
        criteria=criteria,
    )

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )

    text = msg.content[0].text
    result = _parse_json(text)
    score = float(result.get("score", 0.0))
    reasoning = result.get("reasoning", "No reasoning provided.")
    passed = score >= threshold

    return score, reasoning, passed


def _run_custom_scorer(
    root: Path,
    scorer_path: str,
    input_data: dict,
    output: dict,
    threshold: float,
) -> tuple[float, str, bool]:
    full_path = root / scorer_path
    if not full_path.exists():
        raise FileNotFoundError(f"Scorer not found: {full_path}")

    console.print(
        f"[yellow]⚠ Executing custom scorer:[/yellow] {full_path}\n"
        "[dim]Custom scorer files run as Python code. Only use scorers you trust.[/dim]"
    )
    spec = importlib.util.spec_from_file_location("scorer", full_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.score(input_data, output)
    score = float(result.get("score", 0.0))
    reasoning = result.get("reasoning", "")
    passed = score >= threshold

    return score, reasoning, passed


def _parse_json(text: str) -> dict:
    import re
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _print_eval_results(results: list):
    console.print()
    table = Table(title="Eval Results", show_header=True, header_style="bold")
    table.add_column("Agent", style="cyan")
    table.add_column("Case")
    table.add_column("Score", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Reasoning", style="dim")

    passed = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for agent, case, score, p, reasoning in results:
        score_color = "green" if score >= 0.7 else "yellow" if score >= 0.4 else "red"
        score_str = f"[{score_color}]{score:.2f}[/{score_color}]"
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        short_reason = reasoning[:60] + "..." if len(reasoning) > 60 else reasoning
        table.add_row(agent, case, score_str, status, short_reason)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} evals passed[/bold {color}]")
