from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from ryva.cli import app

runner = CliRunner()


@pytest.fixture()
def project(tmp_path):
    (tmp_path / "project.yml").write_text("name: test\n")
    (tmp_path / "target").mkdir()
    return tmp_path


class TestApprovalsList:
    def test_list_empty_no_dir(self, project):
        result = runner.invoke(app, ["approvals", "list", "--root", str(project)])
        assert result.exit_code == 0
        assert "No approvals" in result.output

    def test_list_empty_dir(self, project):
        (project / "target" / "approvals").mkdir()
        result = runner.invoke(app, ["approvals", "list", "--root", str(project)])
        assert result.exit_code == 0
        assert "No approvals" in result.output

    def test_list_shows_pending(self, project):
        approvals_dir = project / "target" / "approvals"
        approvals_dir.mkdir()
        (approvals_dir / "abc12345.json").write_text(json.dumps({
            "id": "abc12345",
            "agent": "my_agent",
            "step": "technical",
            "status": "pending",
            "reviewer_name": "Alice",
            "created_at": "2026-06-01T10:00:00+00:00",
        }))
        result = runner.invoke(app, ["approvals", "list", "--root", str(project)])
        assert result.exit_code == 0
        assert "PENDING" in result.output
        assert "Alice" in result.output

    def test_list_filter_by_agent(self, project):
        approvals_dir = project / "target" / "approvals"
        approvals_dir.mkdir()
        for agent, aid in [("agent_a", "aaaa1111"), ("agent_b", "bbbb2222")]:
            (approvals_dir / f"{aid}.json").write_text(json.dumps({
                "id": aid,
                "agent": agent,
                "step": "technical",
                "status": "pending",
                "reviewer_name": "Bob",
                "created_at": "2026-06-01T10:00:00+00:00",
            }))
        result = runner.invoke(app, ["approvals", "list", "--root", str(project), "--agent", "agent_a"])
        assert "agent_a" in result.output
        assert "agent_b" not in result.output


class TestApprovalsRequest:
    def test_request_creates_file(self, project):
        result = runner.invoke(app, [
            "approvals", "request",
            "--root", str(project),
            "--agent", "my_agent",
            "--step", "technical",
            "--reviewer", "Alice",
            "--reviewer-email", "alice@example.com",
        ])
        assert result.exit_code == 0
        approvals_dir = project / "target" / "approvals"
        files = list(approvals_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert data["agent"] == "my_agent"
        assert data["step"] == "technical"
        assert data["status"] == "pending"
        assert data["reviewer_name"] == "Alice"
        assert data["reviewer_email"] == "alice@example.com"

    def test_request_invalid_step(self, project):
        result = runner.invoke(app, [
            "approvals", "request",
            "--root", str(project),
            "--agent", "my_agent",
            "--step", "invalid_step",
            "--reviewer", "Bob",
            "--reviewer-email", "bob@example.com",
        ])
        assert result.exit_code != 0
        assert "must be one of" in result.output

    def test_request_prints_id(self, project):
        result = runner.invoke(app, [
            "approvals", "request",
            "--root", str(project),
            "--agent", "my_agent",
            "--step", "privacy",
            "--reviewer", "Carol",
            "--reviewer-email", "carol@example.com",
        ])
        assert "Approval request created" in result.output

    def test_request_all_valid_steps(self, project):
        for step in ("technical", "privacy", "compliance", "legal"):
            result = runner.invoke(app, [
                "approvals", "request",
                "--root", str(project),
                "--agent", "my_agent",
                "--step", step,
                "--reviewer", "Dave",
                "--reviewer-email", "dave@example.com",
            ])
            assert result.exit_code == 0, f"Step '{step}' failed: {result.output}"


class TestApprovalsRecord:
    def _create_approval(self, project, approval_id: str = "test1234") -> None:
        approvals_dir = project / "target" / "approvals"
        approvals_dir.mkdir(parents=True, exist_ok=True)
        (approvals_dir / f"{approval_id}.json").write_text(json.dumps({
            "id": approval_id,
            "agent": "my_agent",
            "step": "technical",
            "status": "pending",
            "reviewer_name": "Alice",
            "reviewer_email": "alice@example.com",
            "created_at": "2026-06-01T10:00:00+00:00",
        }))

    def test_record_approves(self, project):
        self._create_approval(project)
        result = runner.invoke(app, [
            "approvals", "record",
            "--root", str(project),
            "--id", "test1234",
            "--approved-by", "Manager Bob",
        ])
        assert result.exit_code == 0
        data = json.loads((project / "target" / "approvals" / "test1234.json").read_text())
        assert data["status"] == "approved"
        assert data["approved_by"] == "Manager Bob"

    def test_record_rejects(self, project):
        self._create_approval(project)
        result = runner.invoke(app, [
            "approvals", "record",
            "--root", str(project),
            "--id", "test1234",
            "--approved-by", "Manager Bob",
            "--reject",
        ])
        assert result.exit_code == 0
        data = json.loads((project / "target" / "approvals" / "test1234.json").read_text())
        assert data["status"] == "rejected"

    def test_record_missing_id(self, project):
        result = runner.invoke(app, [
            "approvals", "record",
            "--root", str(project),
            "--id", "nonexistent",
            "--approved-by", "Bob",
        ])
        assert result.exit_code != 0
        assert "not found" in result.output
