#!/usr/bin/env python3
"""Demonstrate production Claude → Ryva Forge ingest without rewriting on Ryva CLI."""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
DEMO_INPUT = ROOT_DIR / "demo_inputs" / "routine_appointment_request.json"


def _load_intake_message() -> str:
    payload = json.loads(DEMO_INPUT.read_text())
    return (
        "Patient intake (synthetic demo data): "
        f"{payload['patient_name']} requested: {payload['message']}"
    )


def run_with_live_claude(reporter) -> str:
    from ryva.integrations.anthropic import instrumented_client

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is required for live Claude demo")

    client = instrumented_client(reporter=reporter)
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=512,
        system=(
            "You are an administrative intake triage assistant. "
            "Summarize the request and recommend routing only. Do not diagnose."
        ),
        messages=[{"role": "user", "content": _load_intake_message()}],
    )
    reporter.flush()
    return getattr(response, "id", "live-claude-run")


def run_synthetic(reporter) -> str:
    run_id = f"northstar-demo-{uuid.uuid4().hex[:12]}"
    started = time.perf_counter()
    time.sleep(0.05)
    duration_ms = max(1, int((time.perf_counter() - started) * 1000))
    messages = [{"role": "user", "content": _load_intake_message()}]
    reporter.record_claude_call(
        run_id=run_id,
        model="claude-sonnet-4-5",
        input_messages=messages,
        system_prompt="Administrative intake triage assistant (synthetic demo run).",
        output_text=(
            "Route to scheduling for a routine wellness visit. "
            "No urgent language detected."
        ),
        usage={"input_tokens": 180, "output_tokens": 42},
        duration_ms=duration_ms,
    )
    reporter.flush()
    return run_id


def main() -> int:
    from ryva.ingest import ForgeReporter

    reporter = ForgeReporter.from_env()
    if reporter is None:
        print(
            "Set RYVA_PROJECT_ID, RYVA_SYSTEM_ID, and RYVA_INGESTION_TOKEN "
            "to send production evidence to Forge.",
            file=sys.stderr,
        )
        return 1

    if os.environ.get("ANTHROPIC_API_KEY"):
        run_id = run_with_live_claude(reporter)
        mode = "live_claude"
    else:
        run_id = run_synthetic(reporter)
        mode = "synthetic"

    print(
        json.dumps(
            {
                "status": "sent_to_forge",
                "mode": mode,
                "run_id": run_id,
                "system_id": reporter.system_id,
                "project_id": reporter.project_id,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
