from __future__ import annotations

import json

from ryva.lineage import (
    _legacy_fallback_secret,
    chain,
    export_compliance,
    hash_content,
    hash_data,
    record,
    search,
    verify_record,
)

# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

class TestHashHelpers:
    def test_hash_content_returns_sha256_prefix(self):
        h = hash_content("hello world")
        assert h.startswith("sha256:")

    def test_hash_content_is_deterministic(self):
        assert hash_content("abc") == hash_content("abc")

    def test_hash_content_differs_for_different_input(self):
        assert hash_content("abc") != hash_content("xyz")

    def test_hash_data_handles_dict(self):
        h = hash_data({"key": "value"})
        assert h.startswith("sha256:")

    def test_hash_data_is_key_order_independent(self):
        assert hash_data({"a": 1, "b": 2}) == hash_data({"b": 2, "a": 1})

    def test_hash_data_empty_dict(self):
        assert hash_data({}).startswith("sha256:")


# ---------------------------------------------------------------------------
# record() / _load_record()
# ---------------------------------------------------------------------------

def _make_trace(run_id: str, agent: str = "summarizer", parent: str | None = None) -> dict:
    return {
        "run_id": run_id,
        "trace_id": parent or run_id,
        "parent_run_id": parent,
        "agent": agent,
        "model": "claude-haiku-4-5",
        "provider": "anthropic",
        "prompt_template": "summarize.j2",
        "prompt_hash": hash_content("summarize"),
        "input_hash": hash_data({"text": "hello"}),
        "output_hash": hash_data({"summary": "world"}),
        "started_at": "2026-05-01T10:00:00",
        "finished_at": "2026-05-01T10:00:01",
        "duration_ms": 1000,
        "status": "success",
        "tokens": {"input": 100, "output": 50, "total": 150},
        "cost_usd": 0.001,
        "context": {},
        "retrieval_chunks": [],
        "tool_calls": [],
    }


class TestRecord:
    def test_creates_file(self, tmp_path):
        trace = _make_trace("run001")
        record(tmp_path, trace)
        assert (tmp_path / "lineage" / "run001.json").exists()

    def test_round_trip(self, tmp_path):
        trace = _make_trace("run002")
        record(tmp_path, trace)
        data = json.loads((tmp_path / "lineage" / "run002.json").read_text())
        assert data["run_id"] == "run002"
        assert data["agent"] == "summarizer"
        assert data["prompt_hash"] == trace["prompt_hash"]

    def test_preserves_parent_run_id(self, tmp_path):
        trace = _make_trace("child01", parent="parent01")
        record(tmp_path, trace)
        data = json.loads((tmp_path / "lineage" / "child01.json").read_text())
        assert data["parent_run_id"] == "parent01"


# ---------------------------------------------------------------------------
# chain()
# ---------------------------------------------------------------------------

class TestChain:
    def test_single_run(self, tmp_path):
        trace = _make_trace("solo01")
        record(tmp_path, trace)
        result = chain(tmp_path, "solo01")
        assert len(result) == 1
        assert result[0]["run_id"] == "solo01"

    def test_parent_child_chain(self, tmp_path):
        parent = _make_trace("parent01")
        child = _make_trace("child01", parent="parent01")
        record(tmp_path, parent)
        record(tmp_path, child)
        result = chain(tmp_path, "child01")
        assert len(result) == 2
        assert result[0]["run_id"] == "parent01"
        assert result[1]["run_id"] == "child01"

    def test_three_level_chain(self, tmp_path):
        record(tmp_path, _make_trace("r1"))
        record(tmp_path, _make_trace("r2", parent="r1"))
        record(tmp_path, _make_trace("r3", parent="r2"))
        result = chain(tmp_path, "r3")
        assert [r["run_id"] for r in result] == ["r1", "r2", "r3"]

    def test_missing_run_returns_empty(self, tmp_path):
        assert chain(tmp_path, "nonexistent") == []

    def test_cycle_protection(self, tmp_path):
        t1 = _make_trace("c1", parent="c2")
        t2 = _make_trace("c2", parent="c1")
        record(tmp_path, t1)
        record(tmp_path, t2)
        result = chain(tmp_path, "c1")
        assert len(result) <= 2

    def test_falls_back_to_traces_dir(self, tmp_path):
        traces_dir = tmp_path / "traces"
        traces_dir.mkdir()
        trace = _make_trace("tr01")
        (traces_dir / "tr01.json").write_text(json.dumps(trace))
        result = chain(tmp_path, "tr01")
        assert len(result) == 1
        assert result[0]["run_id"] == "tr01"


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------

class TestSearch:
    def _populate(self, tmp_path, n=5):
        for i in range(n):
            t = _make_trace(f"s{i:03}", agent="agent_a" if i % 2 == 0 else "agent_b")
            record(tmp_path, t)

    def test_returns_all_without_filters(self, tmp_path):
        self._populate(tmp_path)
        results = search(tmp_path)
        assert len(results) == 5

    def test_filter_by_agent(self, tmp_path):
        self._populate(tmp_path)
        results = search(tmp_path, agent="agent_a")
        assert all(r["agent"] == "agent_a" for r in results)

    def test_filter_by_status(self, tmp_path):
        record(tmp_path, _make_trace("ok01"))
        t = _make_trace("err01")
        t["status"] = "error"
        record(tmp_path, t)
        results = search(tmp_path, status="error")
        assert len(results) == 1
        assert results[0]["run_id"] == "err01"

    def test_limit_respected(self, tmp_path):
        self._populate(tmp_path, 10)
        assert len(search(tmp_path, limit=3)) == 3

    def test_empty_directory(self, tmp_path):
        assert search(tmp_path) == []

    def test_filter_by_prompt_hash(self, tmp_path):
        t = _make_trace("ph01")
        t["prompt_hash"] = "sha256:unique9999"
        record(tmp_path, t)
        record(tmp_path, _make_trace("ph02"))
        results = search(tmp_path, prompt_hash="sha256:unique9999")
        assert len(results) == 1
        assert results[0]["run_id"] == "ph01"


# ---------------------------------------------------------------------------
# export_compliance()
# ---------------------------------------------------------------------------

class TestExportCompliance:
    def test_single_run(self, tmp_path):
        record(tmp_path, _make_trace("e01"))
        export = export_compliance(tmp_path, "e01")
        assert export["run_id"] == "e01"
        assert export["chain_depth"] == 1
        assert "summary" in export
        assert "chain" in export

    def test_summary_fields(self, tmp_path):
        record(tmp_path, _make_trace("e02"))
        s = export_compliance(tmp_path, "e02")["summary"]
        assert "summarizer" in s["agents_involved"]
        assert "anthropic" in s["providers_used"]
        assert s["total_tokens"] == 150
        assert s["all_succeeded"] is True

    def test_chain_cost_summed(self, tmp_path):
        record(tmp_path, _make_trace("p01"))
        record(tmp_path, _make_trace("p02", parent="p01"))
        export = export_compliance(tmp_path, "p02")
        assert export["chain_depth"] == 2
        assert abs(export["summary"]["total_cost_usd"] - 0.002) < 1e-9

    def test_missing_run_returns_empty(self, tmp_path):
        assert export_compliance(tmp_path, "ghost") == {}

    def test_retrieval_sources_collected(self, tmp_path):
        t = _make_trace("r01")
        t["retrieval_chunks"] = [{"source": "annual-report.pdf", "score": 0.9}]
        record(tmp_path, t)
        export = export_compliance(tmp_path, "r01")
        assert "annual-report.pdf" in export["summary"]["retrieval_sources"]


# ---------------------------------------------------------------------------
# HMAC signature verification
# ---------------------------------------------------------------------------

class TestHmacSignature:
    def test_record_includes_signature(self, tmp_path):
        record(tmp_path, _make_trace("sig01"))
        data = json.loads((tmp_path / "lineage" / "sig01.json").read_text())
        assert "signature" in data
        assert len(data["signature"]) == 64  # hex-encoded SHA-256

    def test_record_creates_project_secret_when_unset(self, tmp_path):
        record(tmp_path, _make_trace("sig00"))
        assert (tmp_path / ".ryva_secret").exists()

    def test_verify_passes_for_fresh_record(self, tmp_path):
        record(tmp_path, _make_trace("sig02"))
        ok, detail = verify_record(tmp_path, "sig02")
        assert ok is True
        assert "valid" in detail.lower()

    def test_verify_fails_for_missing_record(self, tmp_path):
        ok, detail = verify_record(tmp_path, "ghost999")
        assert ok is False
        assert "not found" in detail.lower()

    def test_verify_fails_after_tampering(self, tmp_path):
        record(tmp_path, _make_trace("sig03"))
        path = tmp_path / "lineage" / "sig03.json"
        data = json.loads(path.read_text())
        data["agent"] = "evil_agent"
        path.write_text(json.dumps(data))
        ok, detail = verify_record(tmp_path, "sig03")
        assert ok is False
        assert "tamper" in detail.lower() or "mismatch" in detail.lower()

    def test_verify_no_signature_returns_false(self, tmp_path):
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        entry = {"run_id": "nosig", "agent": "a"}
        (lineage_dir / "nosig.json").write_text(json.dumps(entry))
        ok, detail = verify_record(tmp_path, "nosig")
        assert ok is False
        assert "signature" in detail.lower() or "predates" in detail.lower()

    def test_signature_stable_across_calls(self, tmp_path):
        trace = _make_trace("sig04")
        record(tmp_path, trace)
        ok1, _ = verify_record(tmp_path, "sig04")
        ok2, _ = verify_record(tmp_path, "sig04")
        assert ok1 is True
        assert ok2 is True

    def test_env_secret_used_when_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RYVA_SECRET", "test-secret-key")
        record(tmp_path, _make_trace("sig05"))
        ok, _ = verify_record(tmp_path, "sig05")
        assert ok is True

    def test_different_secrets_produce_mismatch(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RYVA_SECRET", "secret-a")
        record(tmp_path, _make_trace("sig06"))
        monkeypatch.setenv("RYVA_SECRET", "secret-b")
        ok, _ = verify_record(tmp_path, "sig06")
        assert ok is False

    def test_legacy_path_secret_still_verifies_existing_records(self, tmp_path):
        trace = _make_trace("sig07")
        lineage_dir = tmp_path / "lineage"
        lineage_dir.mkdir()
        canonical = {
            "run_id": trace["run_id"],
            "parent_run_id": trace.get("parent_run_id"),
            "trace_id": trace.get("trace_id", trace["run_id"]),
            "agent": trace.get("agent"),
            "model": trace.get("model"),
            "provider": trace.get("provider"),
            "prompt_hash": trace.get("prompt_hash"),
            "input_hash": trace.get("input_hash"),
            "output_hash": trace.get("output_hash"),
            "started_at": trace.get("started_at"),
            "status": trace.get("status"),
        }
        import hashlib
        import hmac

        payload = json.dumps(canonical, sort_keys=True, default=str).encode()
        trace["signature"] = hmac.new(
            _legacy_fallback_secret(tmp_path),
            payload,
            hashlib.sha256,
        ).hexdigest()
        (lineage_dir / "sig07.json").write_text(json.dumps(trace))

        ok, detail = verify_record(tmp_path, "sig07")
        assert ok is True
        assert "legacy" in detail.lower()
