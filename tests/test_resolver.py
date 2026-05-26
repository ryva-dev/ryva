from __future__ import annotations
import pytest
from pathlib import Path
from ryva.resolver import ProjectResolver


class TestResolveEmptyProject:
    def test_success(self, project_dir):
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is True
        assert resolver.errors == []
        assert resolver.project.name == "test-project"

    def test_missing_project_yml(self, tmp_path):
        (tmp_path / "agents").mkdir()
        (tmp_path / "tools").mkdir()
        (tmp_path / "pipelines").mkdir()
        resolver = ProjectResolver(tmp_path)
        assert resolver.resolve() is False
        assert any("project.yml" in e for e in resolver.errors)

    def test_invalid_project_yml(self, tmp_path):
        (tmp_path / "agents").mkdir()
        (tmp_path / "tools").mkdir()
        (tmp_path / "pipelines").mkdir()
        # Missing required 'name' field
        (tmp_path / "project.yml").write_text("version: '0.1.0'\n")
        resolver = ProjectResolver(tmp_path)
        assert resolver.resolve() is False


class TestAgentLoading:
    def test_valid_agent(self, project_dir):
        (project_dir / "agents" / "summarizer.yml").write_text(
            "name: summarizer\ndescription: test agent\n"
        )
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is True
        assert "summarizer" in resolver.agents

    def test_invalid_agent_missing_name(self, project_dir):
        (project_dir / "agents" / "bad.yml").write_text("description: no name here\n")
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is False
        assert any("bad.yml" in e for e in resolver.errors)

    def test_multiple_agents(self, project_dir):
        for agent_name in ["alpha", "beta", "gamma"]:
            (project_dir / "agents" / f"{agent_name}.yml").write_text(
                f"name: {agent_name}\n"
            )
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is True
        assert len(resolver.agents) == 3


class TestToolLoading:
    def test_valid_tool(self, project_dir):
        (project_dir / "tools" / "search.yml").write_text(
            "name: search\nimplementation: tools.search\n"
        )
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is True
        assert "search" in resolver.tools

    def test_invalid_tool_missing_implementation(self, project_dir):
        (project_dir / "tools" / "bad.yml").write_text("name: bad\n")
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is False


class TestPipelineLoading:
    def test_valid_pipeline(self, project_dir):
        (project_dir / "pipelines" / "my-pipeline.yml").write_text(
            "name: my-pipeline\nsteps: []\n"
        )
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is True
        assert "my-pipeline" in resolver.pipelines

    def test_invalid_pipeline_missing_name(self, project_dir):
        (project_dir / "pipelines" / "bad.yml").write_text("steps: []\n")
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is False


class TestRefValidation:
    def test_missing_prompt_ref(self, project_dir):
        (project_dir / "agents" / "agent.yml").write_text(
            "name: agent\nprompt: ref(prompts/missing)\n"
        )
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is False
        assert any("missing" in e for e in resolver.errors)

    def test_valid_prompt_ref(self, project_dir):
        (project_dir / "prompts" / "summarize.j2").write_text(
            "Summarize: {{ input.text }}"
        )
        (project_dir / "agents" / "agent.yml").write_text(
            "name: agent\nprompt: ref(prompts/summarize)\n"
        )
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is True

    def test_missing_tool_ref(self, project_dir):
        (project_dir / "agents" / "agent.yml").write_text(
            "name: agent\ntools:\n  - ref(tools/missing_tool)\n"
        )
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is False
        assert any("missing_tool" in e for e in resolver.errors)

    def test_valid_tool_ref(self, project_dir):
        (project_dir / "tools" / "search.yml").write_text(
            "name: search\nimplementation: tools.search\n"
        )
        (project_dir / "agents" / "agent.yml").write_text(
            "name: agent\ntools:\n  - ref(tools/search)\n"
        )
        resolver = ProjectResolver(project_dir)
        assert resolver.resolve() is True


class TestToManifest:
    def test_structure(self, project_dir):
        resolver = ProjectResolver(project_dir)
        resolver.resolve()
        manifest = resolver.to_manifest()
        assert manifest["ryva_version"] == "0.1.0"
        assert "project" in manifest
        assert "agents" in manifest
        assert "tools" in manifest
        assert "pipelines" in manifest

    def test_agents_included(self, project_dir):
        (project_dir / "agents" / "summarizer.yml").write_text("name: summarizer\n")
        resolver = ProjectResolver(project_dir)
        resolver.resolve()
        manifest = resolver.to_manifest()
        assert "summarizer" in manifest["agents"]

    def test_no_project_returns_empty_dict(self, tmp_path):
        (tmp_path / "agents").mkdir()
        (tmp_path / "tools").mkdir()
        (tmp_path / "pipelines").mkdir()
        resolver = ProjectResolver(tmp_path)
        resolver.resolve()
        manifest = resolver.to_manifest()
        assert manifest["project"] == {}
