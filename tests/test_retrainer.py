from __future__ import annotations

import json

import pytest

from ryva.retrainer import (
    DriftMonitor,
    load_history,
    show_history,
    trigger_retraining,
    update_job_status,
)


class TestDriftMonitor:
    def test_record_and_load_scores(self, tmp_path):
        m = DriftMonitor(tmp_path, "summarizer")
        m.record_score(0.9, "r001")
        scores = m._load_scores()
        assert len(scores) == 1
        assert scores[0]["score"] == 0.9

    def test_insufficient_data_no_drift(self, tmp_path):
        m = DriftMonitor(tmp_path, "summarizer")
        m.record_score(0.8)
        m.record_score(0.7)
        result = m.compute_drift()
        assert result["drifted"] is False
        assert "Insufficient" in result["reason"]

    def test_no_drift_stable_scores(self, tmp_path):
        m = DriftMonitor(tmp_path, "summarizer", drift_threshold=0.15)
        for s in [0.9, 0.88, 0.91, 0.89]:
            m.record_score(s)
        result = m.compute_drift()
        assert result["drifted"] is False

    def test_drift_detected(self, tmp_path):
        m = DriftMonitor(tmp_path, "summarizer", drift_threshold=0.15)
        for s in [0.95, 0.94, 0.70, 0.65]:
            m.record_score(s)
        result = m.compute_drift()
        assert result["drifted"] is True
        assert result["drift_magnitude"] > 0

    def test_drift_result_fields(self, tmp_path):
        m = DriftMonitor(tmp_path, "agent_a", drift_threshold=0.1)
        for s in [0.9, 0.9, 0.6, 0.6]:
            m.record_score(s)
        result = m.compute_drift()
        assert "agent" in result
        assert "baseline_mean" in result
        assert "recent_mean" in result
        assert "drift_magnitude" in result
        assert "score_count" in result
        assert result["score_count"] == 4

    def test_clear_scores(self, tmp_path):
        m = DriftMonitor(tmp_path, "agent_b")
        m.record_score(0.8)
        m.clear_scores()
        assert m._load_scores() == []

    def test_drift_threshold_boundary(self, tmp_path):
        m = DriftMonitor(tmp_path, "agent_c", drift_threshold=0.2)
        for s in [0.9, 0.9, 0.71, 0.71]:
            m.record_score(s)
        result = m.compute_drift()
        assert result["drift_magnitude"] < 0.2
        assert result["drifted"] is False


class TestTriggerRetraining:
    def test_creates_job_file(self, tmp_path):
        job_id = trigger_retraining(tmp_path, "summarizer")
        assert (tmp_path / "retraining" / f"{job_id}.json").exists()

    def test_returns_job_id(self, tmp_path):
        job_id = trigger_retraining(tmp_path, "summarizer")
        assert isinstance(job_id, str) and len(job_id) == 8

    def test_job_has_required_fields(self, tmp_path):
        job_id = trigger_retraining(tmp_path, "summarizer", trigger="drift", reason="score drop")
        data = json.loads((tmp_path / "retraining" / f"{job_id}.json").read_text())
        assert data["agent"] == "summarizer"
        assert data["trigger"] == "drift"
        assert data["reason"] == "score drop"
        assert data["status"] == "pending"
        assert "created_at" in data

    def test_invalid_trigger_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            trigger_retraining(tmp_path, "summarizer", trigger="unknown_trigger")

    def test_valid_triggers(self, tmp_path):
        for trigger in ("manual", "drift", "feedback", "scheduled"):
            trigger_retraining(tmp_path, f"agent_{trigger}", trigger=trigger)


class TestLoadHistory:
    def test_empty_returns_empty_list(self, tmp_path):
        assert load_history(tmp_path) == []

    def test_loads_all_jobs(self, tmp_path):
        trigger_retraining(tmp_path, "a1")
        trigger_retraining(tmp_path, "a2")
        assert len(load_history(tmp_path)) == 2

    def test_filter_by_agent(self, tmp_path):
        trigger_retraining(tmp_path, "agent_a")
        trigger_retraining(tmp_path, "agent_b")
        result = load_history(tmp_path, agent="agent_a")
        assert len(result) == 1
        assert result[0]["agent"] == "agent_a"

    def test_skips_score_files(self, tmp_path):
        trigger_retraining(tmp_path, "a1")
        DriftMonitor(tmp_path, "a1").record_score(0.9)
        jobs = load_history(tmp_path)
        assert all("_scores" not in j.get("job_id", "") for j in jobs)


class TestUpdateJobStatus:
    def test_update_to_completed(self, tmp_path):
        job_id = trigger_retraining(tmp_path, "agent_a")
        ok = update_job_status(tmp_path, job_id, "completed")
        assert ok is True
        data = json.loads((tmp_path / "retraining" / f"{job_id}.json").read_text())
        assert data["status"] == "completed"
        assert data["completed_at"] is not None

    def test_update_nonexistent_job(self, tmp_path):
        assert update_job_status(tmp_path, "ghost123", "completed") is False

    def test_update_metadata(self, tmp_path):
        job_id = trigger_retraining(tmp_path, "agent_a")
        update_job_status(tmp_path, job_id, "completed", metadata={"accuracy": 0.95})
        data = json.loads((tmp_path / "retraining" / f"{job_id}.json").read_text())
        assert data["metadata"]["accuracy"] == 0.95


class TestShowHistory:
    def test_runs_without_error_empty(self, tmp_path):
        show_history(tmp_path)

    def test_runs_without_error_with_data(self, tmp_path):
        trigger_retraining(tmp_path, "summarizer", reason="test drift")
        show_history(tmp_path)
