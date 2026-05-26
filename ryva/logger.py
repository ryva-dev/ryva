from __future__ import annotations

import logging
from pathlib import Path


def setup(root: Path | None = None, level: str = "INFO") -> None:
    log_level = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = []

    if root:
        log_dir = root / "logs"
        log_dir.mkdir(exist_ok=True)
        handlers.append(
            logging.FileHandler(log_dir / "ryva.log", encoding="utf-8")
        )

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(name)-24s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        handlers=handlers or None,
        force=True,
    )


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"ryva.{name}")
