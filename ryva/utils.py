from __future__ import annotations

import json
import os
from pathlib import Path

from rich.console import Console
from ruamel.yaml import YAML

console = Console()
yaml = YAML()
yaml.preserve_quotes = True


def find_project_root(start: Path = Path.cwd()) -> Path:
    for p in [start, *start.parents]:
        if (p / "project.yml").exists():
            return p
    raise FileNotFoundError(
        "No project.yml found. Are you inside a Ryva project? Run `ryva init` first."
    )


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.load(f) or {}


def save_yaml(path: Path, data: dict) -> None:
    with open(path, "w") as f:
        yaml.dump(data, f)


def load_manifest(root: Path) -> dict:
    manifest_path = root / "target" / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            "No manifest found. Run `ryva compile` first."
        )
    return json.loads(manifest_path.read_text())


def resolve_env_vars(value: str) -> str:
    """Resolve {{ env_var('KEY') }} syntax in strings."""
    import re
    pattern = r"\{\{\s*env_var\('([^']+)'\)\s*\}\}"
    def replacer(m):
        key = m.group(1)
        val = os.environ.get(key, "")
        if not val:
            console.print(f"[yellow]Warning: env var '{key}' is not set[/yellow]")
        return val
    return re.sub(pattern, replacer, value)


def parse_ref(ref_str: str) -> tuple[str, str]:
    """Parse ref(agents/foo) → ('agents', 'foo')"""
    import re
    m = re.match(r"ref\(([^/]+)/([^)]+)\)", ref_str)
    if not m:
        raise ValueError(f"Invalid ref: '{ref_str}'. Expected format: ref(type/name)")
    return m.group(1), m.group(2)
