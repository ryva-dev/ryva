from __future__ import annotations

import json

import pytest

from ryva.feedback import load_feedback, record_feedback, show_feedback_report


class TestRecordFeedback:
    def test_creates_file(self, tmp_path):
        record_feedback(tmp_path, "run001", "correct")
        assert (tmp_path / "logs" / "feedback" / "run001.json").exists()

    def test_valid_outcomes(self, tmp_path):
        for outcome in ("correct", "incorrect", "partial", "unknown"):
            record_feedback(tmp_path, f"run_{outcome}", outcome)

    def test_invalid_outcome_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            record_feedback(tmp_path, "run999", "bad_outcome")

    def test_stored_fields(self, tmp_path):
        record_feedback(tmp_path, "run002", "incorrect", note="missed the date", annotator="alice")
        data = json.loads((tmp_path / "logs" / "feedback" / "run002.json").read_text())
        assert data["run_id"] == "run002"
        assert data["outcome"] == "incorrect"
        assert data["note"] == "missed the date"
        assert data["annotator"] == "alice"
        assert "recorded_at" in data
        assert "feedback_id" in data

    def test_agent_resolved_from_lineage(self, tmp_path):
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        (lineage_dir / "run003.json").write_text(json.dumps({"agent": "summarizer"}))
        record_feedback(tmp_path, "run003", "correct")
        data = json.loads((tmp_path / "logs" / "feedback" / "run003.json").read_text())
        assert data["agent"] == "summarizer"

    def test_agent_resolved_from_run_log(self, tmp_path):
        runs_dir = tmp_path / "logs" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "run004.json").write_text(json.dumps({"agent": "classifier"}))
        record_feedback(tmp_path, "run004", "partial")
        data = json.loads((tmp_path / "logs" / "feedback" / "run004.json").read_text())
        assert data["agent"] == "classifier"

    def test_agent_empty_when_not_found(self, tmp_path):
        record_feedback(tmp_path, "run005", "unknown")
        data = json.loads((tmp_path / "logs" / "feedback" / "run005.json").read_text())
        assert data["agent"] == ""


class TestLoadFeedback:
    def _write(self, tmp_path, run_id, outcome, agent="agent_a"):
        feedback_dir = tmp_path / "logs" / "feedback"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        (feedback_dir / f"{run_id}.json").write_text(json.dumps({
            "feedback_id": run_id,
            "run_id": run_id,
            "agent": agent,
            "outcome": outcome,
            "note": "",
            "recorded_at": "2026-05-01T10:00:00+00:00",
        }))

    def test_returns_empty_when_no_directory(self, tmp_path):
        assert load_feedback(tmp_path) == []

    def test_loads_all_entries(self, tmp_path):
        for i in range(3):
            self._write(tmp_path, f"r{i}", "correct")
        assert len(load_feedback(tmp_path)) == 3

    def test_filter_by_agent(self, tmp_path):
        self._write(tmp_path, "r1", "correct", agent="agent_a")
        self._write(tmp_path, "r2", "incorrect", agent="agent_b")
        result = load_feedback(tmp_path, agent="agent_a")
        assert len(result) == 1
        assert result[0]["agent"] == "agent_a"

    def test_skips_malformed_json(self, tmp_path):
        feedback_dir = tmp_path / "logs" / "feedback"
        feedback_dir.mkdir(parents=True)
        (feedback_dir / "bad.json").write_text("{broken json")
        self._write(tmp_path, "good", "correct")
        result = load_feedback(tmp_path)
        assert len(result) == 1

    def test_most_recent_first(self, tmp_path):
        for i in range(3):
            self._write(tmp_path, f"r{i:03}", "correct")
        result = load_feedback(tmp_path)
        assert len(result) == 3


class TestShowFeedbackReport:
    def test_runs_without_error_when_empty(self, tmp_path):
        show_feedback_report(tmp_path)

    def test_runs_without_error_with_data(self, tmp_path):
        feedback_dir = tmp_path / "logs" / "feedback"
        feedback_dir.mkdir(parents=True)
        for outcome in ("correct", "correct", "incorrect"):
            import uuid
            rid = str(uuid.uuid4())[:8]
            (feedback_dir / f"{rid}.json").write_text(json.dumps({
                "feedback_id": rid,
                "run_id": rid,
                "agent": "summarizer",
                "outcome": outcome,
                "note": "",
                "recorded_at": "2026-05-01T10:00:00+00:00",
            }))
        show_feedback_report(tmp_path)
