from __future__ import annotations
import json
import pytest
from pathlib import Path
from ryva.cost_tracker import calculate_cost, check_budget, get_cost_summary, load_pricing, load_runs


class TestCalculateCost:
    def test_anthropic_sonnet(self):
        cost = calculate_cost("anthropic", "claude-sonnet-4-5", 1_000_000, 1_000_000)
        assert cost == pytest.approx(18.0)  # $3 input + $15 output per 1M tokens

    def test_anthropic_haiku(self):
        cost = calculate_cost("anthropic", "claude-haiku-4-5", 1_000_000, 1_000_000)
        assert cost == pytest.approx(4.80)  # $0.80 + $4.00

    def test_openai_gpt4o(self):
        cost = calculate_cost("openai", "gpt-4o", 1_000_000, 1_000_000)
        assert cost == pytest.approx(12.50)  # $2.50 + $10.00

    def test_openai_mini(self):
        cost = calculate_cost("openai", "gpt-4o-mini", 1_000_000, 1_000_000)
        assert cost == pytest.approx(0.75)  # $0.15 + $0.60

    def test_ollama_is_free(self):
        assert calculate_cost("ollama", "llama3", 100_000, 100_000) == 0.0

    def test_zero_tokens(self):
        assert calculate_cost("anthropic", "claude-sonnet-4-5", 0, 0) == 0.0

    def test_unknown_provider_returns_zero(self):
        assert calculate_cost("unknown", "some-model", 1_000_000, 1_000_000) == 0.0

    def test_unknown_model_falls_back_to_default(self):
        # Unknown model for a known provider should use provider's default pricing
        cost = calculate_cost("anthropic", "unknown-model", 1_000_000, 0)
        assert cost == pytest.approx(3.0)  # anthropic default input price

    def test_only_input_tokens(self):
        cost = calculate_cost("openai", "gpt-4o", 1_000_000, 0)
        assert cost == pytest.approx(2.50)

    def test_only_output_tokens(self):
        cost = calculate_cost("openai", "gpt-4o", 0, 1_000_000)
        assert cost == pytest.approx(10.0)


class TestLoadRuns:
    def test_no_directory(self, tmp_path):
        assert load_runs(tmp_path) == []

    def test_empty_directory(self, tmp_path):
        (tmp_path / "logs" / "runs").mkdir(parents=True)
        assert load_runs(tmp_path) == []

    def test_valid_run(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        run = {"run_id": "abc123", "agent": "summarizer"}
        (runs_dir / "abc123.json").write_text(json.dumps(run))
        runs = load_runs(tmp_path)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "abc123"

    def test_multiple_runs(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        for i in range(5):
            run = {"run_id": f"run-{i}", "agent": "a"}
            (runs_dir / f"run-{i}.json").write_text(json.dumps(run))
        assert len(load_runs(tmp_path)) == 5

    def test_skips_invalid_json(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "bad.json").write_text("{ not valid json {{")
        assert load_runs(tmp_path) == []

    def test_valid_and_invalid_mixed(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "good.json").write_text(json.dumps({"run_id": "good"}))
        (runs_dir / "bad.json").write_text("broken")
        runs = load_runs(tmp_path)
        assert len(runs) == 1
        assert runs[0]["run_id"] == "good"


class TestGetCostSummary:
    def test_empty_project(self, tmp_path):
        summary = get_cost_summary(tmp_path)
        assert summary["total_runs"] == 0
        assert summary["total_cost"] == 0.0
        assert summary["by_agent"] == {}
        assert summary["total_tokens"] == 0

    def test_with_runs(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        for i in range(3):
            run = {
                "run_id": f"r{i}",
                "agent": "summarizer",
                "timestamp": "2026-05-26T10:00:00+00:00",
                "estimated_cost": 0.01,
                "input_tokens": 100,
                "output_tokens": 50,
                "elapsed_ms": 500,
            }
            (runs_dir / f"r{i}.json").write_text(json.dumps(run))

        summary = get_cost_summary(tmp_path, month="2026-05")
        assert summary["total_runs"] == 3
        assert summary["total_cost"] == pytest.approx(0.03)
        assert "summarizer" in summary["by_agent"]
        assert summary["by_agent"]["summarizer"]["runs"] == 3

    def test_filters_by_month(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "may.json").write_text(
            json.dumps({"run_id": "a", "agent": "x", "timestamp": "2026-05-01T00:00:00+00:00", "estimated_cost": 1.0})
        )
        (runs_dir / "june.json").write_text(
            json.dumps({"run_id": "b", "agent": "x", "timestamp": "2026-06-01T00:00:00+00:00", "estimated_cost": 2.0})
        )

        summary = get_cost_summary(tmp_path, month="2026-05")
        assert summary["total_runs"] == 1
        assert summary["total_cost"] == pytest.approx(1.0)

    def test_avg_latency_per_agent(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        for i, latency in enumerate([100, 200, 300]):
            run = {
                "run_id": f"r{i}",
                "agent": "agent",
                "timestamp": "2026-05-01T00:00:00+00:00",
                "elapsed_ms": latency,
            }
            (runs_dir / f"r{i}.json").write_text(json.dumps(run))

        summary = get_cost_summary(tmp_path, month="2026-05")
        assert summary["by_agent"]["agent"]["avg_latency"] == 200


class TestCheckBudget:
    def test_no_budget_config(self, tmp_path):
        assert check_budget(tmp_path, {}) == []

    def test_no_monthly_limit(self, tmp_path):
        assert check_budget(tmp_path, {"budget": {"alert_threshold": 0.8}}) == []

    def test_under_threshold(self, tmp_path):
        project = {"budget": {"monthly_limit_usd": 100.0, "alert_threshold": 0.8}}
        assert check_budget(tmp_path, project) == []

    def test_alert_triggered(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "r.json").write_text(
            json.dumps({"run_id": "r", "agent": "a", "timestamp": "2026-05-01T00:00:00+00:00", "estimated_cost": 85.0})
        )
        project = {"budget": {"monthly_limit_usd": 100.0, "alert_threshold": 0.8}}
        warnings = check_budget(tmp_path, project)
        assert len(warnings) == 1
        assert "ALERT" in warnings[0]

    def test_budget_exceeded(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "r.json").write_text(
            json.dumps({"run_id": "r", "agent": "a", "timestamp": "2026-05-01T00:00:00+00:00", "estimated_cost": 150.0})
        )
        project = {"budget": {"monthly_limit_usd": 100.0}}
        warnings = check_budget(tmp_path, project)
        assert any("EXCEEDED" in w for w in warnings)

    def test_per_agent_budget_exceeded(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "r.json").write_text(
            json.dumps({"run_id": "r", "agent": "summarizer", "timestamp": "2026-05-01T00:00:00+00:00", "estimated_cost": 20.0})
        )
        project = {
            "budget": {
                "monthly_limit_usd": 1000.0,
                "agents": {"summarizer": 10.0},
            }
        }
        warnings = check_budget(tmp_path, project)
        assert any("summarizer" in w for w in warnings)


class TestLoadPricing:
    def test_returns_defaults_without_root(self):
        pricing = load_pricing(None)
        assert "anthropic" in pricing
        assert "openai" in pricing

    def test_returns_defaults_with_no_override_file(self, tmp_path):
        pricing = load_pricing(tmp_path)
        assert pricing["anthropic"]["claude-sonnet-4-5"]["input"] == pytest.approx(3.0)

    def test_project_override_merges(self, tmp_path):
        (tmp_path / "pricing.yml").write_text(
            "anthropic:\n  claude-sonnet-4-5:\n    input: 1.00\n    output: 5.00\n"
        )
        pricing = load_pricing(tmp_path)
        assert pricing["anthropic"]["claude-sonnet-4-5"]["input"] == pytest.approx(1.0)
        # Other providers should still be present from defaults
        assert "openai" in pricing

    def test_calculate_cost_uses_custom_pricing(self, tmp_path):
        custom = {"anthropic": {"claude-sonnet-4-5": {"input": 1.0, "output": 2.0}, "default": {"input": 1.0, "output": 2.0}}}
        cost = calculate_cost("anthropic", "claude-sonnet-4-5", 1_000_000, 1_000_000, pricing=custom)
        assert cost == pytest.approx(3.0)

    def test_project_override_adds_new_provider(self, tmp_path):
        (tmp_path / "pricing.yml").write_text(
            "my-provider:\n  my-model:\n    input: 0.50\n    output: 2.00\n  default:\n    input: 0.50\n    output: 2.00\n"
        )
        pricing = load_pricing(tmp_path)
        assert "my-provider" in pricing
        cost = calculate_cost("my-provider", "my-model", 1_000_000, 0, pricing=pricing)
        assert cost == pytest.approx(0.50)
