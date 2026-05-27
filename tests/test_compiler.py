from __future__ import annotations

import json

from ryva.compiler import compile_project


class TestCompileProject:
    def test_success_writes_manifest(self, project_dir):
        assert compile_project(project_dir) is True
        manifest_path = project_dir / "target" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["ryva_version"] == "0.1.0"

    def test_returns_false_on_errors(self, project_dir):
        # Agent with missing name causes a validation error
        (project_dir / "agents" / "bad.yml").write_text("description: no name\n")
        assert compile_project(project_dir) is False

    def test_manifest_includes_agents(self, project_dir):
        (project_dir / "agents" / "summarizer.yml").write_text("name: summarizer\n")
        compile_project(project_dir)
        manifest = json.loads((project_dir / "target" / "manifest.json").read_text())
        assert "summarizer" in manifest["agents"]

    def test_manifest_includes_tools(self, project_dir):
        (project_dir / "tools" / "search.yml").write_text(
            "name: search\nimplementation: tools.search\n"
        )
        compile_project(project_dir)
        manifest = json.loads((project_dir / "target" / "manifest.json").read_text())
        assert "search" in manifest["tools"]

    def test_no_manifest_on_failure(self, project_dir):
        (project_dir / "agents" / "bad.yml").write_text("description: no name\n")
        compile_project(project_dir)
        assert not (project_dir / "target" / "manifest.json").exists()

    def test_missing_prompt_ref_fails(self, project_dir):
        (project_dir / "agents" / "a.yml").write_text(
            "name: a\nprompt: ref(prompts/missing)\n"
        )
        assert compile_project(project_dir) is False
