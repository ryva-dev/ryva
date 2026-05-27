from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """Minimal valid project directory."""
    (tmp_path / "agents").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "project.yml").write_text("name: test-project\nversion: '0.1.0'\n")
    return tmp_path


@pytest.fixture
def project_with_manifest(project_dir: Path) -> Path:
    """Project directory with a compiled manifest."""
    target = project_dir / "target"
    target.mkdir()
    manifest = {
        "ryva_version": "0.1.0",
        "project": {"name": "test-project", "version": "0.1.0"},
        "agents": {},
        "tools": {},
        "pipelines": {},
    }
    (target / "manifest.json").write_text(json.dumps(manifest))
    return project_dir
