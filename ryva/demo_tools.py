from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def _repo_root(root: Path) -> Path:
    return Path(_git(["rev-parse", "--show-toplevel"], cwd=root))


def _relative_to_repo(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def reset_demo_artifacts(root: Path) -> dict[str, int]:
    """Remove generated demo artifacts while preserving checked-in fixtures."""
    repo_root = _repo_root(root)
    cleanup_paths = [
        root / "target",
        root / "traces",
        root / "lineage",
        root / "logs" / "runs",
    ]

    removed_files = 0
    removed_dirs = 0

    target_dir = root / "target"
    if target_dir.exists():
        shutil.rmtree(target_dir)
        removed_dirs += 1

    tracked = set(
        line
        for line in _git(
            [
                "ls-files",
                "--",
                *[
                    _relative_to_repo(path, repo_root)
                    for path in cleanup_paths
                    if path.exists() and path != target_dir
                ],
            ],
            cwd=repo_root,
        ).splitlines()
        if line
    )

    for path in cleanup_paths:
        if not path.exists() or path == target_dir:
            continue
        for file_path in path.rglob("*"):
            if not file_path.is_file():
                continue
            rel = _relative_to_repo(file_path, repo_root)
            if rel not in tracked:
                file_path.unlink()
                removed_files += 1

    return {"removed_files": removed_files, "removed_dirs": removed_dirs}
