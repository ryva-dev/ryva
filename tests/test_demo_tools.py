from __future__ import annotations

import subprocess
from pathlib import Path

from ryva.demo_tools import reset_demo_artifacts


def _git(cwd: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def test_reset_demo_artifacts_removes_only_untracked_files(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    root = repo / "healthcare-ai-audit-demo"
    (root / "traces").mkdir(parents=True)
    (root / "lineage").mkdir()
    (root / "logs" / "runs").mkdir(parents=True)
    (root / "target").mkdir()

    tracked_trace = root / "traces" / "seed.json"
    tracked_trace.write_text('{"tracked": true}')
    tracked_lineage = root / "lineage" / "seed.json"
    tracked_lineage.write_text('{"tracked": true}')

    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "seed demo")

    untracked_trace = root / "traces" / "fresh.json"
    untracked_trace.write_text('{"fresh": true}')
    untracked_lineage = root / "lineage" / "fresh.json"
    untracked_lineage.write_text('{"fresh": true}')
    run_log = root / "logs" / "runs" / "latest.log"
    run_log.write_text("ok")
    target_file = root / "target" / "artifact.txt"
    target_file.write_text("artifact")

    result = reset_demo_artifacts(root)

    assert tracked_trace.exists()
    assert tracked_lineage.exists()
    assert not untracked_trace.exists()
    assert not untracked_lineage.exists()
    assert not run_log.exists()
    assert not (root / "target").exists()
    assert result == {"removed_files": 3, "removed_dirs": 1}
