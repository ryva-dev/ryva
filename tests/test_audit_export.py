from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ryva.audit_export import (
    _collect_test_evidence,
    _generate_colorado_checklist,
    _generate_eu_checklist,
    _generate_readme,
    _get_project_name,
    _summarize_feedback,
    export_audit_package,
)


def _minimal_project(tmp_path: Path) -> None:
    (tmp_path / "project.yml").write_text("name: test-project\nversion: '0.1.0'\n")
    (tmp_path / "target").mkdir(exist_ok=True)
    (tmp_path / "target" / "manifest.json").write_text(json.dumps({
        "ryva_version": "0.1.0",
        "project": {"name": "test-project"},
        "agents": {},
        "tools": {},
        "pipelines": {},
        "prompt_hashes": {},
    }))


class TestExportAuditPackage:
    def test_creates_zip_file(self, tmp_path):
        _minimal_project(tmp_path)
        out = tmp_path / "audit.zip"
        result = export_audit_package(tmp_path, out)
        assert result == out
        assert out.exists()
        assert zipfile.is_zipfile(out)

    def test_zip_contains_readme(self, tmp_path):
        _minimal_project(tmp_path)
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            assert "README.md" in zf.namelist()

    def test_zip_contains_package_manifest(self, tmp_path):
        _minimal_project(tmp_path)
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            assert "PACKAGE_MANIFEST.json" in zf.namelist()

    def test_zip_contains_eu_ai_act_checklist(self, tmp_path):
        _minimal_project(tmp_path)
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            assert "compliance/eu_ai_act_checklist.md" in zf.namelist()

    def test_zip_contains_colorado_checklist(self, tmp_path):
        _minimal_project(tmp_path)
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            assert "compliance/colorado_ai_act_checklist.md" in zf.namelist()

    def test_zip_contains_test_evidence(self, tmp_path):
        _minimal_project(tmp_path)
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            assert "testing/test_evidence.json" in zf.namelist()

    def test_package_manifest_is_valid_json(self, tmp_path):
        _minimal_project(tmp_path)
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            data = json.loads(zf.read("PACKAGE_MANIFEST.json"))
            assert data["package_version"] == "1.0.0"
            assert "generated_at" in data

    def test_includes_governance_report_when_present(self, tmp_path):
        _minimal_project(tmp_path)
        (tmp_path / "target" / "governance_report.json").write_text(json.dumps({"test": True}))
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            assert "governance/governance_report.json" in zf.namelist()

    def test_includes_model_cards_when_present(self, tmp_path):
        _minimal_project(tmp_path)
        cards_dir = tmp_path / "target" / "model_cards"
        cards_dir.mkdir(parents=True)
        (cards_dir / "my_agent_model_card.json").write_text(json.dumps({"system": {"name": "my_agent"}}))
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            assert "model_cards/my_agent_model_card.json" in zf.namelist()

    def test_default_output_path_in_target(self, tmp_path):
        _minimal_project(tmp_path)
        result = export_audit_package(tmp_path)
        assert "target" in str(result)
        assert result.suffix == ".zip"
        assert result.exists()

    def test_includes_lineage_records_when_present(self, tmp_path):
        _minimal_project(tmp_path)
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        (lineage_dir / "run1.json").write_text(json.dumps({"run_id": "run1"}))
        out = tmp_path / "audit.zip"
        export_audit_package(tmp_path, out)
        with zipfile.ZipFile(out) as zf:
            assert "lineage/run1.json" in zf.namelist()


class TestCollectTestEvidence:
    def test_returns_correct_structure(self, tmp_path):
        evidence = _collect_test_evidence(tmp_path)
        assert "generated_at" in evidence
        assert "test_types_configured" in evidence
        assert "test_files" in evidence
        assert "total_test_cases" in evidence

    def test_empty_when_no_tests_dir(self, tmp_path):
        evidence = _collect_test_evidence(tmp_path)
        assert evidence["total_test_cases"] == 0
        assert evidence["test_types_configured"] == []

    def test_counts_yml_files(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test1.yml").write_text("name: t1")
        (tests_dir / "test2.yml").write_text("name: t2")
        evidence = _collect_test_evidence(tmp_path)
        assert evidence["total_test_cases"] == 2

    def test_detects_adversarial_dir(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "adversarial").mkdir()
        evidence = _collect_test_evidence(tmp_path)
        assert "adversarial" in evidence["test_types_configured"]

    def test_detects_multiple_test_type_dirs(self, tmp_path):
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        for td in ["fuzz", "hallucination", "rag"]:
            (tests_dir / td).mkdir()
        evidence = _collect_test_evidence(tmp_path)
        assert set(["fuzz", "hallucination", "rag"]).issubset(set(evidence["test_types_configured"]))


class TestSummarizeFeedback:
    def test_calculates_accuracy_correctly(self, tmp_path):
        files = []
        for i, outcome in enumerate(["correct", "correct", "incorrect", "partial"]):
            f = tmp_path / f"fb{i}.json"
            f.write_text(json.dumps({"outcome": outcome}))
            files.append(f)
        result = _summarize_feedback(files)
        assert result["total_annotations"] == 4
        assert result["correct"] == 2
        assert result["incorrect"] == 1
        assert result["partial"] == 1
        assert result["accuracy"] == pytest.approx(0.5)

    def test_accuracy_none_when_no_feedback(self, tmp_path):
        result = _summarize_feedback([])
        assert result["accuracy"] is None
        assert result["total_annotations"] == 0

    def test_all_correct_gives_accuracy_one(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"fb{i}.json"
            f.write_text(json.dumps({"outcome": "correct"}))
            files.append(f)
        result = _summarize_feedback(files)
        assert result["accuracy"] == pytest.approx(1.0)

    def test_handles_unknown_outcome(self, tmp_path):
        f = tmp_path / "fb.json"
        f.write_text(json.dumps({"outcome": "unknown"}))
        result = _summarize_feedback([f])
        assert result["total_annotations"] == 1
        assert result["correct"] == 0


class TestGenerateReadme:
    def test_contains_project_name(self, tmp_path):
        readme = _generate_readme(tmp_path, "my_project", "20260101_120000")
        assert "my_project" in readme

    def test_contains_timestamp(self, tmp_path):
        readme = _generate_readme(tmp_path, "proj", "20260530_090000")
        assert "20260530_090000" in readme

    def test_contains_contents_table(self, tmp_path):
        readme = _generate_readme(tmp_path, "proj", "ts")
        assert "governance/" in readme
        assert "model_cards/" in readme
        assert "lineage/" in readme

    def test_contains_verify_command(self, tmp_path):
        readme = _generate_readme(tmp_path, "proj", "ts")
        assert "ryva lineage verify" in readme


class TestGetProjectName:
    def test_reads_name_from_project_yml(self, tmp_path):
        (tmp_path / "project.yml").write_text("name: my-ai-project\n")
        assert _get_project_name(tmp_path) == "my-ai-project"

    def test_replaces_spaces_with_underscores(self, tmp_path):
        (tmp_path / "project.yml").write_text("name: My AI Project\n")
        assert _get_project_name(tmp_path) == "My_AI_Project"

    def test_falls_back_to_directory_name(self, tmp_path):
        name = _get_project_name(tmp_path)
        assert name == tmp_path.name


class TestGenerateChecklists:
    def test_eu_checklist_contains_eu_ai_act_heading(self, tmp_path):
        result = _generate_eu_checklist(tmp_path)
        assert "EU AI Act" in result

    def test_colorado_checklist_contains_sb_24_205(self, tmp_path):
        result = _generate_colorado_checklist(tmp_path)
        assert "SB 24-205" in result

    def test_colorado_checklist_mentions_ryva_coverage(self, tmp_path):
        result = _generate_colorado_checklist(tmp_path)
        assert "Ryva Coverage" in result
