from __future__ import annotations

import json
from pathlib import Path

from rich.table import Table

from ryva.utils import console, load_manifest, load_yaml


def run_memory_tests(
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
        test_dir = root / "tests" / "memory" / name
        if not test_dir.exists():
            console.print(
                f"[dim]No memory tests found at tests/memory/{name}/[/dim]"
            )
            continue

        for test_file in test_dir.glob("*.yml"):
            test_data = load_yaml(test_file)
            test_type = test_data.get("type", "conversation")
            cases = test_data.get("cases", [])

            for case in cases:
                case_name = case.get("name", test_file.stem)
                passed, detail = _run_memory_case(
                    root, name, case, test_type,
                    manifest.get("project", {})
                )
                results.append((name, case_name, test_type, passed, detail))
                if not passed:
                    all_passed = False

    if not results:
        console.print("[dim]No memory tests found.[/dim]")
        return True

    _print_results(results)
    return all_passed


def _run_memory_case(
    root: Path,
    agent_name: str,
    case: dict,
    test_type: str,
    project: dict
) -> tuple[bool, str]:
    try:
        if test_type == "conversation":
            return _test_conversation_memory(root, agent_name, case, project)
        elif test_type == "context_retention":
            return _test_context_retention(root, agent_name, case, project)
        elif test_type == "multi_turn":
            return _test_multi_turn(root, agent_name, case, project)
        elif test_type == "sliding_window":
            return _test_sliding_window(root, agent_name, case, project)
        else:
            return False, f"Unknown memory test type: {test_type}"
    except Exception as e:
        return False, str(e)[:80]


def _test_conversation_memory(
    root: Path,
    agent_name: str,
    case: dict,
    project: dict
) -> tuple[bool, str]:
    """Test that agent remembers information from earlier in a conversation."""
    turns = case.get("turns", [])
    memory_check = case.get("memory_check", {})

    if not turns:
        return False, "No conversation turns defined"

    conversation_history = []
    outputs = []

    for i, turn in enumerate(turns):
        inp = turn.get("input", {})

        # Add conversation history to input
        if conversation_history:
            inp["_conversation_history"] = conversation_history

        try:
            from ryva.runner import run_agent
            output = run_agent(root, agent_name, inp)
            outputs.append(output)
            conversation_history.append({
                "turn": i + 1,
                "input": inp,
                "output": output
            })
        except Exception as e:
            return False, f"Turn {i+1} failed: {str(e)[:60]}"

    # Check memory retention
    if memory_check:
        check_turn = memory_check.get("check_turn", -1)
        check_output = outputs[check_turn] if outputs else {}
        expected_key = memory_check.get("expected_key")
        expected_value = memory_check.get("expected_value")

        if expected_key and expected_key not in check_output:
            return False, f"Memory check failed: '{expected_key}' not in output"

        if expected_value:
            actual = str(check_output.get(expected_key, "")).lower()
            if expected_value.lower() not in actual:
                return False, f"Memory check failed: expected '{expected_value}' in output"

    return True, f"All {len(turns)} turns completed successfully"


def _test_context_retention(
    root: Path,
    agent_name: str,
    case: dict,
    project: dict
) -> tuple[bool, str]:
    """Test that agent retains specific facts across multiple calls."""
    setup_input = case.get("setup_input", {})
    recall_input = case.get("recall_input", {})
    expected_recall = case.get("expected_recall", "")
    threshold = case.get("threshold", 0.5)

    if not setup_input or not recall_input:
        return False, "Missing setup_input or recall_input"

    try:
        from ryva.runner import run_agent

        # Step 1: Give the agent information
        setup_output = run_agent(root, agent_name, setup_input)

        # Step 2: Ask the agent to recall it
        recall_input["_previous_context"] = json.dumps(setup_output)
        recall_output = run_agent(root, agent_name, recall_input)

        # Step 3: Check if recalled correctly
        recall_str = str(recall_output).lower()
        expected_words = set(expected_recall.lower().split())
        recall_words = set(recall_str.split())

        overlap = expected_words & recall_words
        score = len(overlap) / len(expected_words) if expected_words else 0

        passed = score >= threshold
        return passed, f"Recall score: {score:.2f} (threshold: {threshold})"

    except Exception as e:
        return False, str(e)[:80]


def _test_multi_turn(
    root: Path,
    agent_name: str,
    case: dict,
    project: dict
) -> tuple[bool, str]:
    """Test agent behavior across multiple independent turns."""
    turns = case.get("turns", [])
    pass_threshold = case.get("pass_threshold", 1.0)

    if not turns:
        return False, "No turns defined"

    passed_turns = 0
    failed_turns = []

    for i, turn in enumerate(turns):
        inp = turn.get("input", {})
        expect = turn.get("expect", {})

        try:
            from ryva.runner import run_agent
            from ryva.tester import _check_schema

            output = run_agent(root, agent_name, inp)

            if expect:
                turn_passed, detail = _check_schema(output, expect)
                if turn_passed:
                    passed_turns += 1
                else:
                    failed_turns.append(f"Turn {i+1}: {detail}")
            else:
                passed_turns += 1

        except Exception as e:
            failed_turns.append(f"Turn {i+1}: {str(e)[:40]}")

    pass_rate = passed_turns / len(turns) if turns else 0
    passed = pass_rate >= pass_threshold

    if failed_turns:
        return passed, f"Failed: {failed_turns[0]}"
    return passed, f"{passed_turns}/{len(turns)} turns passed"


def _test_sliding_window(
    root: Path,
    agent_name: str,
    case: dict,
    project: dict,
) -> tuple[bool, str]:
    """Test that an agent handles a long conversation using a sliding context window.

    Each turn receives only the last `window_size` turns as history, simulating
    real deployments that truncate context to fit token limits. The test verifies
    the agent responds without error across all turns and that any `memory_check`
    at the end still passes using only the windowed history.
    """
    turns = case.get("turns", [])
    window_size = case.get("window_size", 5)
    memory_check = case.get("memory_check", {})

    if not turns:
        return False, "No turns defined"

    from ryva.runner import run_agent

    window: list[dict] = []
    outputs: list[dict] = []

    for i, turn in enumerate(turns):
        inp = dict(turn.get("input", {}))
        inp["_context_window"] = window[-window_size:]

        try:
            output = run_agent(root, agent_name, inp)
            outputs.append(output)
            window.append({"turn": i + 1, "input": turn.get("input", {}), "output": output})
        except Exception as e:
            return False, f"Turn {i + 1} failed: {str(e)[:60]}"

    if memory_check:
        check_turn = memory_check.get("check_turn", -1)
        check_output = outputs[check_turn] if outputs else {}
        expected_key = memory_check.get("expected_key")
        expected_value = memory_check.get("expected_value")

        if expected_key and expected_key not in check_output:
            return False, f"Memory check failed: '{expected_key}' not in output"

        if expected_value:
            actual = str(check_output.get(expected_key, "")).lower()
            if expected_value.lower() not in actual:
                return False, f"Memory check failed: expected '{expected_value}' in output"

    return True, f"{len(turns)} turns with window_size={window_size}"


def _print_results(results: list):
    console.print()
    table = Table(
        title="Memory Test Results",
        show_header=True,
        header_style="bold"
    )
    table.add_column("Agent", style="cyan")
    table.add_column("Test Case")
    table.add_column("Type", style="dim")
    table.add_column("Status", justify="center")
    table.add_column("Detail", style="dim")

    passed = sum(1 for *_, p, _ in results if p)
    total = len(results)

    for agent, case, typ, p, detail in results:
        status = "[bold green]✓ PASS[/bold green]" if p else "[bold red]✗ FAIL[/bold red]"
        table.add_row(agent, case, typ or "—", status, detail)

    console.print(table)
    color = "green" if passed == total else "red"
    console.print(f"\n[bold {color}]{passed}/{total} memory tests passed[/bold {color}]")
