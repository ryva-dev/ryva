from __future__ import annotations

import json

from ryva.compiler import detect_and_record_changes, save_change_history


def _make_manifest(agents: dict) -> dict:
    return {"agents": agents}


def _make_agent(model: str = "claude-sonnet-4", version: str = "1.0.0", prompt_hash: str = "aaaa") -> dict:
    return {"model": model, "version": version, "prompt_hash": prompt_hash}


class TestDetectChanges:
    def test_no_changes_returns_empty_list(self):
        manifest = _make_manifest({"my_agent": _make_agent()})
        changes = detect_and_record_changes(manifest, manifest)
        assert changes == []

    def test_agent_registered_on_first_compile(self):
        new_manifest = _make_manifest({"my_agent": _make_agent()})
        changes = detect_and_record_changes({}, new_manifest)
        assert len(changes) == 1
        assert changes[0]["type"] == "AGENT_REGISTERED"
        assert changes[0]["agent"] == "my_agent"
        assert changes[0]["requires_review"] is False
        assert changes[0]["severity"] == "info"

    def test_prompt_change_detected(self):
        old = _make_manifest({"agent": _make_agent(prompt_hash="aaaa1111")})
        new = _make_manifest({"agent": _make_agent(prompt_hash="bbbb2222")})
        changes = detect_and_record_changes(old, new)
        assert len(changes) == 1
        c = changes[0]
        assert c["type"] == "PROMPT_CHANGE"
        assert c["requires_review"] is True
        assert c["severity"] == "high"
        assert "aaaa1111" in c["description"]
        assert "bbbb2222" in c["description"]

    def test_model_change_requires_review(self):
        old = _make_manifest({"agent": _make_agent(model="claude-haiku")})
        new = _make_manifest({"agent": _make_agent(model="claude-sonnet-4")})
        changes = detect_and_record_changes(old, new)
        assert any(c["type"] == "MODEL_CHANGE" for c in changes)
        model_change = next(c for c in changes if c["type"] == "MODEL_CHANGE")
        assert model_change["requires_review"] is True
        assert model_change["severity"] == "high"
        assert model_change["old_value"] == "claude-haiku"
        assert model_change["new_value"] == "claude-sonnet-4"

    def test_version_bump_does_not_require_review(self):
        old = _make_manifest({"agent": _make_agent(version="1.0.0")})
        new = _make_manifest({"agent": _make_agent(version="1.1.0")})
        changes = detect_and_record_changes(old, new)
        assert any(c["type"] == "VERSION_BUMP" for c in changes)
        bump = next(c for c in changes if c["type"] == "VERSION_BUMP")
        assert bump["requires_review"] is False
        assert bump["severity"] == "low"

    def test_multiple_changes_in_one_compile(self):
        old = _make_manifest({"agent": _make_agent(model="old-model", prompt_hash="aaa")})
        new = _make_manifest({"agent": _make_agent(model="new-model", prompt_hash="bbb")})
        changes = detect_and_record_changes(old, new)
        types = {c["type"] for c in changes}
        assert "MODEL_CHANGE" in types
        assert "PROMPT_CHANGE" in types

    def test_change_has_id_and_timestamp(self):
        new = _make_manifest({"agent": _make_agent()})
        changes = detect_and_record_changes({}, new)
        assert len(changes) == 1
        assert "id" in changes[0]
        assert "timestamp" in changes[0]
        assert len(changes[0]["id"]) > 0

    def test_multiple_agents(self):
        old = _make_manifest({
            "agent_a": _make_agent(prompt_hash="aaa"),
            "agent_b": _make_agent(model="old-model"),
        })
        new = _make_manifest({
            "agent_a": _make_agent(prompt_hash="bbb"),
            "agent_b": _make_agent(model="new-model"),
            "agent_c": _make_agent(),
        })
        changes = detect_and_record_changes(old, new)
        agent_names = {c["agent"] for c in changes}
        assert "agent_a" in agent_names
        assert "agent_b" in agent_names
        assert "agent_c" in agent_names

    def test_unchanged_agent_not_reported(self):
        agent = _make_agent(model="same", version="1.0.0", prompt_hash="same")
        old = _make_manifest({"agent": agent})
        new = _make_manifest({"agent": agent})
        changes = detect_and_record_changes(old, new)
        assert changes == []


class TestSaveChangeHistory:
    def test_creates_file(self, tmp_path):
        (tmp_path / "target").mkdir()
        changes = [{"id": "abc", "type": "AGENT_REGISTERED", "agent": "my_agent"}]
        save_change_history(changes, tmp_path)
        history_file = tmp_path / "target" / "change_history.json"
        assert history_file.exists()
        saved = json.loads(history_file.read_text())
        assert len(saved) == 1
        assert saved[0]["id"] == "abc"

    def test_appends_to_existing(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        existing = [{"id": "first", "type": "AGENT_REGISTERED", "agent": "old_agent"}]
        (target / "change_history.json").write_text(json.dumps(existing))

        new_changes = [{"id": "second", "type": "PROMPT_CHANGE", "agent": "new_agent"}]
        save_change_history(new_changes, tmp_path)

        saved = json.loads((target / "change_history.json").read_text())
        assert len(saved) == 2
        ids = {c["id"] for c in saved}
        assert "first" in ids
        assert "second" in ids

    def test_handles_corrupt_existing_file(self, tmp_path):
        target = tmp_path / "target"
        target.mkdir()
        (target / "change_history.json").write_text("not valid json{{{{")

        changes = [{"id": "abc", "type": "AGENT_REGISTERED", "agent": "my_agent"}]
        save_change_history(changes, tmp_path)
        saved = json.loads((target / "change_history.json").read_text())
        assert len(saved) == 1
