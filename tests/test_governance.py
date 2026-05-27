from __future__ import annotations

import json
from pathlib import Path

from ryva.governance import (
    _compute_exit_code,
    _eu_ai_act_checklist,
    _render_markdown,
    _score_risk,
    generate_report,
    show_report,
)

# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

class TestScoreRisk:
    def test_high_risk_on_medical_keyword(self):
        agent = {"name": "diagnostic", "description": "medical image analysis"}
        level, reasons = _score_risk(agent, has_tests=True, has_adversarial=True)
        assert level == "HIGH"
        assert any("medical" in r or "diagnostic" in r for r in reasons)

    def test_medium_risk_on_generic_keywords(self):
        agent = {"name": "chatbot", "description": "customer support assistant"}
        level, _ = _score_risk(agent, has_tests=True, has_adversarial=True)
        assert level == "MEDIUM"

    def test_low_risk_baseline(self):
        agent = {"name": "formatter", "description": "formats text nicely"}
        level, _ = _score_risk(agent, has_tests=True, has_adversarial=True)
        assert level == "LOW"

    def test_no_tests_adds_reason(self):
        agent = {"name": "formatter", "description": "formats text"}
        _, reasons = _score_risk(agent, has_tests=False, has_adversarial=True)
        assert any("test" in r.lower() for r in reasons)

    def test_no_adversarial_adds_reason(self):
        agent = {"name": "formatter", "description": "formats text"}
        _, reasons = _score_risk(agent, has_tests=True, has_adversarial=False)
        assert any("adversarial" in r.lower() for r in reasons)


# ---------------------------------------------------------------------------
# EU AI Act checklist
# ---------------------------------------------------------------------------

class TestEuAiActChecklist:
    def _checklist(self, **kwargs):
        defaults = dict(
            root=Path("/tmp"),
            has_policies=False,
            has_lineage=False,
            has_feedback=False,
            has_tests=False,
            has_adversarial=False,
            has_docs=False,
            high_risk_count=0,
        )
        defaults.update(kwargs)
        return _eu_ai_act_checklist(**defaults)

    def test_returns_list_of_dicts(self):
        items = self._checklist()
        assert isinstance(items, list)
        assert all("article" in item and "status" in item for item in items)

    def test_all_fail_without_anything(self):
        items = self._checklist()
        fail_count = sum(1 for i in items if i["status"] == "✗")
        assert fail_count > 0

    def test_lineage_satisfies_audit_log(self):
        items = self._checklist(has_lineage=True)
        art12 = [i for i in items if "Art. 12" in i["article"]]
        assert any(i["status"] == "✓" for i in art12)

    def test_policies_satisfies_human_oversight(self):
        items = self._checklist(has_policies=True)
        art14 = [i for i in items if "Art. 14" in i["article"]]
        assert any(i["status"] == "✓" for i in art14)

    def test_adversarial_satisfies_robustness(self):
        items = self._checklist(has_adversarial=True)
        art15 = [i for i in items if "Art. 15" in i["article"]]
        assert any(i["status"] == "✓" for i in art15)

    def test_guidance_empty_when_met(self):
        items = self._checklist(has_lineage=True, has_policies=True)
        for i in items:
            if i["status"] == "✓":
                assert i["guidance"] == ""


# ---------------------------------------------------------------------------
# generate_report
# ---------------------------------------------------------------------------

def _make_manifest(tmp_path: Path, agents: dict | None = None) -> None:
    target = tmp_path / "target"
    target.mkdir()
    manifest = {
        "ryva_version": "0.1.0",
        "project": {"name": "test-project"},
        "agents": agents or {},
        "tools": {},
        "pipelines": {},
        "prompt_hashes": {"summarize": "sha256:abc123"},
    }
    (target / "manifest.json").write_text(json.dumps(manifest))


class TestGenerateReport:
    def test_structure(self, tmp_path):
        _make_manifest(tmp_path)
        report = generate_report(tmp_path)
        assert "generated_at" in report
        assert "summary" in report
        assert "bill_of_materials" in report
        assert "eu_ai_act_checklist" in report
        assert "risk_assessment" in report

    def test_empty_agents(self, tmp_path):
        _make_manifest(tmp_path)
        report = generate_report(tmp_path)
        assert report["summary"]["agents"] == 0
        assert report["summary"]["total_ai_systems"] == 0

    def test_agent_in_bom(self, tmp_path):
        _make_manifest(tmp_path, agents={
            "summarizer": {"name": "summarizer", "description": "summarizes text", "model": "claude-haiku-4-5"}
        })
        report = generate_report(tmp_path)
        bom = report["bill_of_materials"]
        assert len(bom) == 1
        assert bom[0]["name"] == "summarizer"
        assert bom[0]["type"] == "agent"

    def test_risk_distribution_populated(self, tmp_path):
        _make_manifest(tmp_path, agents={
            "medical_ai": {"name": "medical_ai", "description": "clinical diagnosis"}
        })
        report = generate_report(tmp_path)
        risk = report["summary"]["risk_distribution"]
        assert risk["HIGH"] + risk["MEDIUM"] + risk["LOW"] == 1

    def test_high_risk_in_risk_assessment(self, tmp_path):
        _make_manifest(tmp_path, agents={
            "fraud_detector": {"name": "fraud_detector", "description": "financial fraud detection"}
        })
        report = generate_report(tmp_path)
        assert "fraud_detector" in report["risk_assessment"]["high_risk_systems"]

    def test_lineage_count(self, tmp_path):
        _make_manifest(tmp_path)
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        (lineage_dir / "r1.json").write_text('{"run_id": "r1"}')
        (lineage_dir / "r2.json").write_text('{"run_id": "r2"}')
        report = generate_report(tmp_path)
        assert report["summary"]["total_production_runs"] == 2

    def test_prompt_hashes_in_report(self, tmp_path):
        _make_manifest(tmp_path)
        report = generate_report(tmp_path)
        assert "summarize" in report["prompt_version_registry"]
        assert report["summary"]["prompt_versions_tracked"] == 1

    def test_compliance_score_format(self, tmp_path):
        _make_manifest(tmp_path)
        report = generate_report(tmp_path)
        score = report["summary"]["eu_ai_act_compliance_score"]
        assert "/" in score
        parts = score.split("/")
        assert int(parts[0]) <= int(parts[1])


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

class TestComputeExitCode:
    def _report(self, high_systems=None, untested_systems=None):
        return {
            "risk_assessment": {
                "high_risk_systems": high_systems or [],
                "untested_systems": untested_systems or [],
            }
        }

    def test_exit_0_when_no_high_risk(self):
        assert _compute_exit_code(self._report()) == 0

    def test_exit_1_when_high_risk_but_tested(self):
        report = self._report(
            high_systems=["fraud_detector"],
            untested_systems=[],
        )
        assert _compute_exit_code(report) == 1

    def test_exit_2_when_high_risk_untested(self):
        report = self._report(
            high_systems=["fraud_detector"],
            untested_systems=["fraud_detector"],
        )
        assert _compute_exit_code(report) == 2

    def test_exit_2_when_some_high_risk_untested(self):
        report = self._report(
            high_systems=["a", "b"],
            untested_systems=["b"],
        )
        assert _compute_exit_code(report) == 2

    def test_exit_1_all_high_risk_are_tested(self):
        report = self._report(
            high_systems=["a", "b"],
            untested_systems=["c"],  # c is untested but not high-risk
        )
        assert _compute_exit_code(report) == 1


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

class TestRenderMarkdown:
    def test_contains_project_name(self, tmp_path):
        _make_manifest(tmp_path)
        report = generate_report(tmp_path)
        md = _render_markdown(report)
        assert "test-project" in md

    def test_contains_checklist_section(self, tmp_path):
        _make_manifest(tmp_path)
        report = generate_report(tmp_path)
        md = _render_markdown(report)
        assert "EU AI Act Checklist" in md

    def test_contains_bom_section(self, tmp_path):
        _make_manifest(tmp_path)
        report = generate_report(tmp_path)
        md = _render_markdown(report)
        assert "Bill of Materials" in md

    def test_contains_summary_table(self, tmp_path):
        _make_manifest(tmp_path)
        report = generate_report(tmp_path)
        md = _render_markdown(report)
        assert "Summary" in md


# ---------------------------------------------------------------------------
# File output (show_report writes target/ files)
# ---------------------------------------------------------------------------

class TestShowReportFileOutput:
    def test_writes_json_to_target(self, tmp_path):
        _make_manifest(tmp_path)
        show_report(tmp_path)
        assert (tmp_path / "target" / "governance_report.json").exists()

    def test_writes_md_to_target(self, tmp_path):
        _make_manifest(tmp_path)
        show_report(tmp_path)
        assert (tmp_path / "target" / "governance_report.md").exists()

    def test_json_is_valid(self, tmp_path):
        _make_manifest(tmp_path)
        show_report(tmp_path)
        text = (tmp_path / "target" / "governance_report.json").read_text()
        data = json.loads(text)
        assert "summary" in data

    def test_returns_exit_code_int(self, tmp_path):
        _make_manifest(tmp_path)
        code = show_report(tmp_path)
        assert isinstance(code, int)
        assert code in {0, 1, 2}

    def test_extra_out_written_when_specified(self, tmp_path):
        _make_manifest(tmp_path)
        extra = tmp_path / "my_report.json"
        show_report(tmp_path, out=extra)
        assert extra.exists()
