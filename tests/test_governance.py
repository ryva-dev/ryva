from __future__ import annotations

import json
from pathlib import Path

import pytest

from ryva.governance import _eu_ai_act_checklist, _score_risk, generate_report


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
