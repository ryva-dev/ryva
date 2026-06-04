from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from ryva.cli import app

runner = CliRunner()


# ── check_release_gates ───────────────────────────────────────────────────────

class TestCheckReleaseGates:
    def test_dev_gates_always_pass(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target").mkdir()
        manifest = {"agents": {"test_agent": {"prompt_hash": "abc", "model": "claude-haiku-4-5"}}}
        (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="dev")
        assert result.passed

    def test_no_agents_returns_warning_not_failure(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target").mkdir()
        (tmp_path / "target" / "manifest.json").write_text(json.dumps({"agents": {}}))

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="production")
        assert result.passed
        assert any("No agents compiled" in w for w in result.warnings)

    def test_production_gates_fail_without_approvals(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target").mkdir()
        manifest = {"agents": {"test_agent": {"prompt_hash": "abc", "model": "claude-haiku-4-5"}}}
        (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="production")
        assert not result.passed
        assert any("missing" in f and "technical" in f for f in result.failures)

    def test_staging_requires_only_technical(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target").mkdir()
        manifest = {"agents": {"agent_x": {"prompt_hash": "abc", "model": "claude-haiku-4-5"}}}
        (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="staging")
        assert not result.passed
        assert any("technical" in f for f in result.failures)
        assert not any("legal" in f for f in result.failures)

    def test_production_needs_all_four_approvals(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target").mkdir()
        manifest = {"agents": {"agent_x": {"prompt_hash": "abc", "model": "claude-haiku-4-5"}}}
        (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="production")
        required = {"technical", "privacy", "compliance", "legal"}
        missing_in_failures = {s for s in required if any(s in f for f in result.failures)}
        assert missing_in_failures == required

    def test_approved_agent_passes_staging(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target" / "approvals").mkdir(parents=True)
        (tmp_path / "target" / "test_results").mkdir(parents=True)
        manifest = {"agents": {"agent_x": {"prompt_hash": "abc", "model": "claude-haiku-4-5"}}}
        (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))
        (tmp_path / "target" / "governance_report.json").write_text("{}")

        approval = {
            "id": "stg001",
            "agent": "agent_x",
            "step": "technical",
            "status": "approved",
            "prompt_hash": "abc",
            "approved_at": "2026-06-01T00:00:00Z",
        }
        (tmp_path / "target" / "approvals" / "stg001.json").write_text(json.dumps(approval))
        # Satisfy test results requirement
        (tmp_path / "target" / "test_results" / "agent_x_results.json").write_text("{}")

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="staging")
        assert result.passed

    def test_stale_approval_detected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target" / "approvals").mkdir(parents=True)

        manifest = {"agents": {"test_agent": {"prompt_hash": "NEW_HASH", "model": "claude-haiku-4-5"}}}
        (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))

        approval = {
            "id": "test001",
            "agent": "test_agent",
            "step": "technical",
            "status": "approved",
            "prompt_hash": "OLD_HASH",
            "approved_at": "2026-01-01T00:00:00Z",
        }
        (tmp_path / "target" / "approvals" / "test001.json").write_text(json.dumps(approval))

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="production")
        assert not result.passed
        assert any("stale" in f for f in result.failures)

    def test_expired_exception_creates_warning(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target").mkdir()
        manifest = {"agents": {"agent_x": {}}}
        (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))
        exceptions = [{
            "id": "exc001",
            "agent": "agent_x",
            "expires_at": "2020-01-01T00:00:00Z",
        }]
        (tmp_path / "target" / "exceptions.json").write_text(json.dumps(exceptions))

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="dev")
        assert any("expired" in w for w in result.warnings)

    def test_agents_checked_list_populated(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target").mkdir()
        manifest = {"agents": {"alpha": {}, "beta": {}}}
        (tmp_path / "target" / "manifest.json").write_text(json.dumps(manifest))

        from ryva.release_gates import check_release_gates
        result = check_release_gates(env="dev")
        assert "alpha" in result.agents_checked
        assert "beta" in result.agents_checked


# ── invalidate_stale_approvals ────────────────────────────────────────────────

class TestInvalidateStaleApprovals:
    def test_approval_invalidated_after_prompt_change(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target" / "approvals").mkdir(parents=True)

        approval = {
            "id": "app001",
            "agent": "test_agent",
            "step": "compliance",
            "status": "approved",
            "prompt_hash": "OLD_HASH",
        }
        (tmp_path / "target" / "approvals" / "app001.json").write_text(json.dumps(approval))

        changes = [{"type": "PROMPT_CHANGE", "agent": "test_agent", "requires_review": True}]

        from ryva.release_gates import invalidate_stale_approvals
        invalidated = invalidate_stale_approvals(changes)

        assert "app001" in invalidated
        updated = json.loads((tmp_path / "target" / "approvals" / "app001.json").read_text())
        assert updated["status"] == "stale"
        assert "stale_reason" in updated
        assert "stale_at" in updated

    def test_model_change_invalidates_approval(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target" / "approvals").mkdir(parents=True)

        approval = {
            "id": "mod001",
            "agent": "my_agent",
            "step": "technical",
            "status": "approved",
        }
        (tmp_path / "target" / "approvals" / "mod001.json").write_text(json.dumps(approval))

        changes = [{"type": "MODEL_CHANGE", "agent": "my_agent", "requires_review": True}]

        from ryva.release_gates import invalidate_stale_approvals
        invalidated = invalidate_stale_approvals(changes)
        assert "mod001" in invalidated

    def test_non_significant_change_does_not_invalidate(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target" / "approvals").mkdir(parents=True)

        approval = {
            "id": "ver001",
            "agent": "my_agent",
            "step": "technical",
            "status": "approved",
        }
        (tmp_path / "target" / "approvals" / "ver001.json").write_text(json.dumps(approval))

        changes = [{"type": "VERSION_BUMP", "agent": "my_agent", "requires_review": False}]

        from ryva.release_gates import invalidate_stale_approvals
        invalidated = invalidate_stale_approvals(changes)
        assert invalidated == []

    def test_only_approved_status_gets_invalidated(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "target" / "approvals").mkdir(parents=True)

        pending = {
            "id": "pend001",
            "agent": "my_agent",
            "step": "technical",
            "status": "pending",
        }
        (tmp_path / "target" / "approvals" / "pend001.json").write_text(json.dumps(pending))

        changes = [{"type": "PROMPT_CHANGE", "agent": "my_agent", "requires_review": True}]

        from ryva.release_gates import invalidate_stale_approvals
        invalidated = invalidate_stale_approvals(changes)
        assert invalidated == []

    def test_no_approvals_dir_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        changes = [{"type": "PROMPT_CHANGE", "agent": "my_agent", "requires_review": True}]

        from ryva.release_gates import invalidate_stale_approvals
        invalidated = invalidate_stale_approvals(changes)
        assert invalidated == []

    def test_empty_changes_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        from ryva.release_gates import invalidate_stale_approvals
        assert invalidate_stale_approvals([]) == []


# ── exceptions CLI ────────────────────────────────────────────────────────────

@pytest.fixture()
def project(tmp_path):
    (tmp_path / "project.yml").write_text("name: test\n")
    (tmp_path / "target").mkdir()
    return tmp_path


class TestExceptionsCreate:
    def test_exception_creation(self, project):
        result = runner.invoke(app, [
            "exceptions", "create",
            "--root", str(project),
            "--agent", "test_agent",
            "--policy", "no_hallucination_test",
            "--reason", "Test environment only",
            "--approved-by", "Jane Smith",
            "--expires", "2026-12-31",
        ])
        assert result.exit_code == 0
        assert (project / "target" / "exceptions.json").exists()
        exceptions = json.loads((project / "target" / "exceptions.json").read_text())
        assert len(exceptions) == 1
        assert exceptions[0]["policy"] == "no_hallucination_test"

    def test_creates_exceptions_file(self, project):
        runner.invoke(app, [
            "exceptions", "create",
            "--root", str(project),
            "--agent", "my_agent",
            "--policy", "data_retention",
            "--reason", "Interim approval pending full review",
            "--approved-by", "CTO",
            "--expires", "2027-01-01",
        ])
        data = json.loads((project / "target" / "exceptions.json").read_text())
        assert data[0]["agent"] == "my_agent"
        assert data[0]["status"] == "active"
        assert "id" in data[0]

    def test_appends_to_existing_exceptions(self, project):
        for i in range(3):
            runner.invoke(app, [
                "exceptions", "create",
                "--root", str(project),
                "--agent", f"agent_{i}",
                "--policy", "test_policy",
                "--reason", "reason",
                "--approved-by", "Bob",
                "--expires", "2027-01-01",
            ])
        data = json.loads((project / "target" / "exceptions.json").read_text())
        assert len(data) == 3

    def test_invalid_risk_level(self, project):
        result = runner.invoke(app, [
            "exceptions", "create",
            "--root", str(project),
            "--agent", "agent",
            "--policy", "policy",
            "--reason", "reason",
            "--approved-by", "Bob",
            "--expires", "2027-01-01",
            "--risk-level", "extreme",
        ])
        assert result.exit_code != 0

    def test_exception_appears_in_output(self, project):
        result = runner.invoke(app, [
            "exceptions", "create",
            "--root", str(project),
            "--agent", "my_agent",
            "--policy", "hipaa_compliance",
            "--reason", "Pending audit",
            "--approved-by", "Legal",
            "--expires", "2027-06-01",
        ])
        assert "Exception created" in result.output
        assert "audit package" in result.output


class TestExceptionsList:
    def test_list_empty(self, project):
        result = runner.invoke(app, ["exceptions", "list", "--root", str(project)])
        assert result.exit_code == 0
        assert "No exceptions" in result.output

    def test_list_active(self, project):
        (project / "target" / "exceptions.json").write_text(json.dumps([
            {
                "id": "exc001",
                "agent": "agent_x",
                "policy": "test_policy",
                "reason": "testing",
                "approved_by": "Bob",
                "expires_at": "2099-01-01T23:59:59Z",
                "status": "active",
            }
        ]))
        result = runner.invoke(app, ["exceptions", "list", "--root", str(project)])
        assert result.exit_code == 0
        assert "ACTIVE" in result.output
        assert "agent_x" in result.output

    def test_expired_hidden_by_default(self, project):
        (project / "target" / "exceptions.json").write_text(json.dumps([
            {
                "id": "exc001",
                "agent": "agent_x",
                "policy": "test_policy",
                "reason": "testing",
                "approved_by": "Bob",
                "expires_at": "2020-01-01T00:00:00Z",
                "status": "active",
            }
        ]))
        result = runner.invoke(app, ["exceptions", "list", "--root", str(project)])
        assert "EXPIRED" not in result.output

    def test_expired_shown_with_flag(self, project):
        (project / "target" / "exceptions.json").write_text(json.dumps([
            {
                "id": "exc001",
                "agent": "agent_x",
                "policy": "test_policy",
                "reason": "testing",
                "approved_by": "Bob",
                "expires_at": "2020-01-01T00:00:00Z",
                "status": "active",
            }
        ]))
        result = runner.invoke(app, [
            "exceptions", "list", "--root", str(project), "--include-expired"
        ])
        assert "EXPIRED" in result.output

    def test_filter_by_agent(self, project):
        (project / "target" / "exceptions.json").write_text(json.dumps([
            {"id": "a1", "agent": "agent_a", "policy": "p1", "reason": "r",
             "approved_by": "X", "expires_at": "2099-01-01T00:00:00Z"},
            {"id": "b1", "agent": "agent_b", "policy": "p2", "reason": "r",
             "approved_by": "X", "expires_at": "2099-01-01T00:00:00Z"},
        ]))
        result = runner.invoke(app, [
            "exceptions", "list", "--root", str(project), "--agent", "agent_a"
        ])
        assert "agent_a" in result.output
        assert "agent_b" not in result.output


# ── status command ────────────────────────────────────────────────────────────

class TestStatusCommand:
    def test_status_passes_dev(self, project):
        (project / "target" / "manifest.json").write_text(
            json.dumps({"agents": {"my_agent": {"prompt_hash": "abc"}}})
        )
        result = runner.invoke(app, ["status", "--root", str(project), "--env", "dev"])
        assert result.exit_code == 0
        assert "All gates passed" in result.output

    def test_status_fails_production_no_approvals(self, project):
        (project / "target" / "manifest.json").write_text(
            json.dumps({"agents": {"my_agent": {"prompt_hash": "abc"}}})
        )
        result = runner.invoke(app, ["status", "--root", str(project), "--env", "production"])
        assert result.exit_code != 0
        assert "blocking" in result.output
