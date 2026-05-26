from __future__ import annotations
import pytest
from pathlib import Path
from ryva.utils import parse_ref, resolve_env_vars, find_project_root


class TestParseRef:
    def test_agents(self):
        kind, name = parse_ref("ref(agents/my-agent)")
        assert kind == "agents"
        assert name == "my-agent"

    def test_tools(self):
        kind, name = parse_ref("ref(tools/search)")
        assert kind == "tools"
        assert name == "search"

    def test_prompts(self):
        kind, name = parse_ref("ref(prompts/summarize)")
        assert kind == "prompts"
        assert name == "summarize"

    def test_invalid_no_ref_prefix(self):
        with pytest.raises(ValueError, match="Invalid ref"):
            parse_ref("agents/foo")

    def test_invalid_missing_slash(self):
        with pytest.raises(ValueError, match="Invalid ref"):
            parse_ref("ref(agentsfoo)")

    def test_invalid_empty_string(self):
        with pytest.raises(ValueError, match="Invalid ref"):
            parse_ref("")

    def test_invalid_plain_name(self):
        with pytest.raises(ValueError, match="Invalid ref"):
            parse_ref("my-agent")


class TestResolveEnvVars:
    def test_set_variable(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret123")
        assert resolve_env_vars("{{ env_var('MY_KEY') }}") == "secret123"

    def test_unset_variable_returns_empty(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        assert resolve_env_vars("{{ env_var('MISSING_KEY') }}") == ""

    def test_plain_string_unchanged(self):
        assert resolve_env_vars("plain-string") == "plain-string"

    def test_mixed_content(self, monkeypatch):
        monkeypatch.setenv("HOST", "localhost")
        result = resolve_env_vars("http://{{ env_var('HOST') }}:8080")
        assert result == "http://localhost:8080"

    def test_multiple_vars(self, monkeypatch):
        monkeypatch.setenv("A", "foo")
        monkeypatch.setenv("B", "bar")
        result = resolve_env_vars("{{ env_var('A') }}-{{ env_var('B') }}")
        assert result == "foo-bar"


class TestFindProjectRoot:
    def test_finds_root_directly(self, tmp_path):
        (tmp_path / "project.yml").write_text("name: test\n")
        assert find_project_root(tmp_path) == tmp_path

    def test_finds_root_from_nested_dir(self, tmp_path):
        (tmp_path / "project.yml").write_text("name: test\n")
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        assert find_project_root(nested) == tmp_path

    def test_raises_when_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No project.yml found"):
            find_project_root(tmp_path)
