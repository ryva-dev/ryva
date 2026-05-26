from __future__ import annotations

import json
import re
from pathlib import Path

from rich.table import Table

from ryva.runner import run_agent
from ryva.utils import console, load_manifest, load_yaml

HALLUCINATION_CHECKS = {
    "factual_grounding": """
You are a hallucination detector. Your job is to check if the AI output
contains any claims that are NOT supported by the provided context.

Context provided to the agent:
{context}

Agent output:
{output}

Check for:
1. Facts stated with confidence that aren't in the context
2. Specific numbers, dates, or names not mentioned in the context
3. Claims that contradict the context
4. Made-up references, citations, or sources

Respond with JSON only:
{{
  "hallucination_detected": true/false,
  "confidence": 0.0-1.0,
  "hallucinated_claims": ["list of specific hallucinated claims"],
  "reasoning": "brief explanation"
}}
""",

    "self_consistency": """
You are checking if two AI responses to the same question are consistent.

Response 1:
{response_1}

Response 2:
{response_2}

Check if these responses contradict each other on key facts or claims.

Respond with JSON only:
{{
  "inconsistency_detected": true/false,
  "confidence": 0.0-1.0,
  "inconsistencies": ["list of specific inconsistencies"],
  "reasoning": "brief explanation"
}}
""",

    "citation_check": """
You are checking if an AI response contains any fabricated citations,
references, URLs, or sources.

Agent output:
{output}

Check for:
1. URLs that look made up
2. Paper citations that seem fabricated
3. References to specific documents that likely don't exist
4. Named sources that appear fictional

Respond with JSON only:
{{
  "fabricated_citations_detected": true/false,
  "confidence": 0.0-1.0,
  "fabricated_items": ["list of suspicious citations or references"],
  "reasoning": "brief explanation"
}}
"""
}


def run_hallucination_tests(
    root: Path,
    agent_name: str | None = None
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
    results = []

    for name, agent in targets.items():
        test_dir = root / "tests" / "hallucination" / name
        if not test_dir.exists():
            console.print(
                f"[dim]No hallucination tests found at "
                f"tests/hallucination/{name}/[/dim]"
            )
            continue

        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            cases = test_data.get("cases", [])
            check_type = test_data.get("check_type", "factual_grounding")

            for case in cases:
                case_name = case.get("name", test_file.stem)
                passed, detail, score = _run_hallucination_case(
                    root, name, case, check_type,
                    manifest.get("project", {})
                )
                results.append((name, case_name, check_type, passed, score, detail))
                if not passed:
                    all_passed = False

    _print_results(results)
    return all_passed


def _run_hallucination_case(
    root: Path,
    agent_name: str,
    case: dict,
    check_type: str,
    project: dict
) -> tuple[bool, str, float]:

    input_data = case.get("input", {})
    context = case.get("context", "")
    threshold = case.get("threshold", 0.3)

    try:
        if check_type == "self_consistency":
            # Run agent twice and compare
            output1 = run_agent(root, agent_name, input_data)
            output2 = run_agent(root, agent_name, input_data)

            prompt = HALLUCINATION_CHECKS["self_consistency"].format(
                response_1=json.dumps(output1),
                response_2=json.dumps(output2)
            )
            result = _call_judge(prompt, project)
            detected = result.get("inconsistency_detected", False)
            confidence = result.get("confidence", 0.0)
            issues = result.get("inconsistencies", [])
            passed = not detected or confidence < threshold

        elif check_type == "citation_check":
            output = run_agent(root, agent_name, input_data)
            prompt = HALLUCINATION_CHECKS["citation_check"].format(
                output=json.dumps(output)
            )
            result = _call_judge(prompt, project)
            detected = result.get("fabricated_citations_detected", False)
            confidence = result.get("confidence", 0.0)
            issues = result.get("fabricated_items", [])
            passed = not detected or confidence < threshold

        else:
            # Default: factual grounding
            output = run_agent(root, agent_name, input_data)
            prompt = HALLUCINATION_CHECKS["factual_grounding"].format(
                context=context or "No context provided",
                output=json.dumps(output)
            )
            result = _call_judge(prompt, project)
            detected = result.get("hallucination_detected", False)
            confidence = result.get("confidence", 0.0)
            issues = result.get("hallucinated_claims", [])
            passed = not detected or confidence < threshold

        if issues:
            detail = f"Issues: {issues[0][:60]}"
        else:
            detail = f"Clean (confidence: {confidence:.2f})"

        return passed, detail, confidence

    except Exception as e:
        return False, str(e)[:80], 0.0


def _call_judge(prompt: str, project: dict) -> dict:
    import os

    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    client = anthropic.Anthropic(api_key=api_key)

    msg = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )

    text = msg.content[0].text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _print_results(results: list):
    console.print()
    table = Table(
        title="Hallucination Detection Results",
        show_header=True,
        header_style="bold"
    )
    table.add_column("Agent", style="cyan")
    table.add_column("Test Case")
    table.add_column("Check Type", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Score", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _, _ in results if p)
    total = len(results)

    for agent, case, check, p, score, detail in results:
        status = "[bold green]✓ CLEAN[/bold green]" if p else "[bold red]✗ HALLUCINATION[/bold red]"
        score_color = "green" if score < 0.3 else "yellow" if score < 0.7 else "red"
        table.add_row(
            agent,
            case,
            check,
            status,
            f"[{score_color}]{score:.2f}[/{score_color}]",
            detail
        )

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} hallucination checks passed[/bold {color}]")
