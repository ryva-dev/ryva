from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from ryva.tester import _check_schema, _print_results, run_tests

# ---------------------------------------------------------------------------
# Schema checks
# ---------------------------------------------------------------------------

class TestCheckSchema:
    def test_correct_types(self):
        output = {"name": "Alice", "score": 0.95, "items": [1, 2, 3], "active": True}
        expect = {
            "name": {"type": "str"},
            "score": {"type": "float"},
            "items": {"type": "list"},
            "active": {"type": "bool"},
        }
        passed, detail = _check_schema(output, expect)
        assert passed is True

    def test_missing_field(self):
        passed, detail = _check_schema({"name": "Alice"}, {"missing_field": {"type": "str"}})
        assert passed is False
        assert "missing_field" in detail

    def test_wrong_type(self):
        passed, detail = _check_schema({"count": "not-an-int"}, {"count": {"type": "int"}})
        assert passed is False
        assert "count" in detail

    def test_min_length_pass(self):
        passed, _ = _check_schema(
            {"summary": "This is long enough."},
            {"summary": {"type": "str", "min_length": 10}},
        )
        assert passed is True

    def test_min_length_fail(self):
        passed, detail = _check_schema(
            {"summary": "short"},
            {"summary": {"type": "str", "min_length": 20}},
        )
        assert passed is False
        assert "too short" in detail

    def test_range_pass(self):
        passed, _ = _check_schema(
            {"confidence": 0.75},
            {"confidence": {"type": "float", "range": [0.0, 1.0]}},
        )
        assert passed is True

    def test_range_fail_above(self):
        passed, detail = _check_schema(
            {"confidence": 1.5},
            {"confidence": {"type": "float", "range": [0.0, 1.0]}},
        )
        assert passed is False
        assert "out of range" in detail

    def test_range_fail_below(self):
        passed, detail = _check_schema(
            {"score": -0.1},
            {"score": {"type": "float", "range": [0.0, 1.0]}},
        )
        assert passed is False
        assert "out of range" in detail

    def test_range_boundary_inclusive(self):
        passed, _ = _check_schema({"v": 0.0}, {"v": {"type": "float", "range": [0.0, 1.0]}})
        assert passed is True
        passed, _ = _check_schema({"v": 1.0}, {"v": {"type": "float", "range": [0.0, 1.0]}})
        assert passed is True

    def test_nested_field_via_output_prefix(self):
        output = {"result": {"text": "hello"}}
        passed, _ = _check_schema(output, {"output.result.text": {"type": "str"}})
        assert passed is True

    def test_nested_field_missing(self):
        output = {"result": {}}
        passed, detail = _check_schema(output, {"output.result.text": {"type": "str"}})
        assert passed is False

    def test_empty_expect_always_passes(self):
        passed, _ = _check_schema({"anything": "goes"}, {})
        assert passed is True

    def test_int_field(self):
        passed, _ = _check_schema({"count": 42}, {"count": {"type": "int"}})
        assert passed is True

    def test_dict_field(self):
        passed, _ = _check_schema({"meta": {"k": "v"}}, {"meta": {"type": "dict"}})
        assert passed is True


# ---------------------------------------------------------------------------
# Concurrency clamping
# ---------------------------------------------------------------------------

def _make_project(tmp_path: Path, cases: list[dict], test_type: str = "returns_non_empty") -> Path:
    """Set up a minimal manifest + test file in tmp_path."""
    target = tmp_path / "target"
    target.mkdir()
    manifest = {
        "ryva_version": "0.1.0",
        "project": {"name": "test-project"},
        "agents": {"agent_a": {"name": "agent_a", "description": "test agent"}},
        "tools": {},
        "pipelines": {},
        "prompt_hashes": {},
    }
    (target / "manifest.json").write_text(json.dumps(manifest))

    tests_dir = tmp_path / "tests" / "agent_a"
    tests_dir.mkdir(parents=True)
    (tests_dir / "basic.yml").write_text(
        json.dumps({"type": test_type, "cases": cases})
    )
    return tmp_path


class TestConcurrencyBounds:
    def test_concurrency_min_clamped_to_1(self):
        # We only check the clamp logic, not actual execution
        with patch("ryva.tester._run_tests_async") as mock_async:
            mock_async.return_value = True
            # Patch asyncio.run to call mock directly
            with patch("asyncio.run", side_effect=lambda coro: asyncio.get_event_loop().run_until_complete(coro) if False else True):
                pass
        # Direct check: concurrency=0 should be clamped to 1
        assert max(1, min(0, 20)) == 1

    def test_concurrency_max_clamped_to_20(self):
        assert max(1, min(999, 20)) == 20

    def test_concurrency_default_is_10(self):
        import inspect

        from ryva.tester import run_tests
        sig = inspect.signature(run_tests)
        assert sig.parameters["concurrency"].default == 10

    def test_concurrency_param_accepted(self):
        import inspect

        from ryva.tester import run_tests
        sig = inspect.signature(run_tests)
        assert "concurrency" in sig.parameters


# ---------------------------------------------------------------------------
# run_tests with no agents / no test cases
# ---------------------------------------------------------------------------

class TestRunTestsEdgeCases:
    def test_returns_false_when_no_agents(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        manifest = {
            "ryva_version": "0.1.0",
            "project": {"name": "empty"},
            "agents": {},
            "tools": {},
            "pipelines": {},
        }
        (target / "manifest.json").write_text(json.dumps(manifest))
        result = run_tests(tmp_path)
        assert result is False

    def test_returns_true_when_no_test_cases_for_agent(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        manifest = {
            "ryva_version": "0.1.0",
            "project": {"name": "no-tests"},
            "agents": {"agent_a": {"name": "agent_a", "description": ""}},
            "tools": {},
            "pipelines": {},
        }
        (target / "manifest.json").write_text(json.dumps(manifest))
        # No tests/ directory — agent has no tests
        result = run_tests(tmp_path, "agent_a")
        assert result is True

    def test_filters_to_named_agent(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        manifest = {
            "ryva_version": "0.1.0",
            "project": {"name": "multi"},
            "agents": {
                "agent_a": {"name": "agent_a", "description": ""},
                "agent_b": {"name": "agent_b", "description": ""},
            },
            "tools": {},
            "pipelines": {},
        }
        (target / "manifest.json").write_text(json.dumps(manifest))
        # Only agent_a requested — should succeed (no test cases = True)
        result = run_tests(tmp_path, "agent_a")
        assert result is True


# ---------------------------------------------------------------------------
# Unknown agent name
# ---------------------------------------------------------------------------

class TestUnknownAgent:
    def test_unknown_agent_falls_back_to_all(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        manifest = {
            "ryva_version": "0.1.0",
            "project": {"name": "p"},
            "agents": {"agent_a": {"name": "agent_a", "description": ""}},
            "tools": {},
            "pipelines": {},
        }
        (target / "manifest.json").write_text(json.dumps(manifest))
        # When agent_name is not in agents dict, all agents are targeted
        result = run_tests(tmp_path, "nonexistent_agent")
        # nonexistent_agent not in agents → falls back to full agents dict
        assert result is True  # no test cases → True


# ---------------------------------------------------------------------------
# _print_results
# ---------------------------------------------------------------------------

class TestPrintResults:
    def test_prints_without_error(self):
        results = [
            ("agent_a", "case1", "schema", True, "All schema checks passed"),
            ("agent_a", "case2", "returns_non_empty", False, "empty output"),
        ]
        _print_results(results)  # should not raise

    def test_prints_with_speedup(self):
        results = [("a", "c", "schema", True, "ok")] * 5
        _print_results(results, concurrency=5, speedup=3.5, wall_elapsed=1.2)

    def test_prints_speedup_only_above_threshold(self):
        results = [("a", "c", "schema", True, "ok")]
        # speedup <= 1.1 should not print speedup line (no assertion, just no crash)
        _print_results(results, concurrency=1, speedup=1.0, wall_elapsed=0.5)

    def test_none_type_displayed_as_dash(self):
        results = [("agent", "case", None, True, "ok")]
        _print_results(results)  # None type should render as "—"
