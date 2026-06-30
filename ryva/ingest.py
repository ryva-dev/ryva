"""Send production runtime evidence to Ryva Forge without the Ryva CLI project model."""
from __future__ import annotations

import atexit
import json
import logging
import os
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from ryva.cloud_sync import sync_external_lineage, sync_external_trace
from ryva.cost_tracker import calculate_cost
from ryva.lineage import hash_content, hash_data

logger = logging.getLogger(__name__)

RYVA_CLOUD_URL = os.environ.get(
    "RYVA_CLOUD_URL", "https://ryva-cloud-production.up.railway.app"
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def serialize_messages_for_hash(messages: list[Any] | None) -> str:
    """Stable JSON representation of chat messages for lineage hashing."""
    if not messages:
        return ""
    normalized: list[dict[str, str]] = []
    for item in messages:
        if isinstance(item, dict):
            role = str(item.get("role", "user"))
            content = item.get("content", "")
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        parts.append(str(block.get("text") or block.get("content") or block))
                    else:
                        parts.append(str(block))
                content = "\n".join(parts)
            normalized.append({"role": role, "content": str(content)})
        else:
            normalized.append({"role": "user", "content": str(item)})
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def extract_output_text(
    output_text: str | None = None,
    *,
    response: Any = None,
) -> str:
    if output_text:
        return output_text
    if response is None:
        return ""
    content = getattr(response, "content", None)
    if not content:
        return ""
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
            continue
        if isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
    return "\n".join(parts)


def extract_usage_tokens(usage: Any | None) -> tuple[int, int]:
    if usage is None:
        return 0, 0
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens", input_tokens)
        output_tokens = usage.get("output_tokens", output_tokens)
    return int(input_tokens or 0), int(output_tokens or 0)


class ForgeReporter:
    """Post signed trace and lineage evidence to Ryva Forge from a production app."""

    def __init__(
        self,
        *,
        project_id: str,
        system_id: str,
        ingestion_token: str,
        cloud_url: str = RYVA_CLOUD_URL,
        include_raw_steps: bool = False,
        async_delivery: bool = True,
    ) -> None:
        self.project_id = project_id
        self.system_id = system_id
        self.ingestion_token = ingestion_token
        self.cloud_url = cloud_url.rstrip("/")
        self.include_raw_steps = include_raw_steps
        self.async_delivery = async_delivery
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ryva-ingest")
        self._futures: list[Future[None]] = []
        atexit.register(self.flush)

    @classmethod
    def from_env(
        cls,
        *,
        optional: bool = False,
        project_id: str | None = None,
        system_id: str | None = None,
        ingestion_token: str | None = None,
        cloud_url: str | None = None,
        **kwargs: Any,
    ) -> ForgeReporter | None:
        resolved_project_id = project_id or os.environ.get("RYVA_PROJECT_ID")
        resolved_system_id = system_id or os.environ.get("RYVA_SYSTEM_ID")
        resolved_token = ingestion_token or os.environ.get("RYVA_INGESTION_TOKEN")
        if not resolved_project_id or not resolved_system_id or not resolved_token:
            if optional:
                return None
            missing = [
                name
                for name, value in [
                    ("RYVA_PROJECT_ID", resolved_project_id),
                    ("RYVA_SYSTEM_ID", resolved_system_id),
                    ("RYVA_INGESTION_TOKEN", resolved_token),
                ]
                if not value
            ]
            raise ValueError(
                "Missing required Forge ingest configuration: " + ", ".join(missing)
            )
        resolved_cloud_url = cloud_url or os.environ.get("RYVA_CLOUD_URL", RYVA_CLOUD_URL)
        return cls(
            project_id=resolved_project_id,
            system_id=resolved_system_id,
            ingestion_token=resolved_token,
            cloud_url=resolved_cloud_url,
            **kwargs,
        )

    def build_trace_payload(
        self,
        *,
        run_id: str,
        model: str,
        provider: str = "anthropic",
        status: str = "success",
        duration_ms: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        estimated_cost: float | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
        pii_masked: bool = True,
        steps: list[dict] | None = None,
    ) -> dict:
        finished = finished_at or _utc_now()
        started = started_at or finished
        cost = estimated_cost
        if cost is None:
            cost = calculate_cost(provider, model, input_tokens, output_tokens)
        if steps is None:
            steps = [
                {
                    "type": "request_received",
                    "timestamp": started,
                    "content": "Production request accepted",
                    "duration_ms": 0,
                },
                {
                    "type": "model_call",
                    "timestamp": finished,
                    "content": "Model invocation completed",
                    "duration_ms": duration_ms,
                },
            ]
        return {
            "run_id": run_id,
            "status": status,
            "duration_ms": duration_ms,
            "provider": provider,
            "model": model,
            "steps": steps,
            "pii_masked": pii_masked,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": cost,
            "started_at": started,
            "finished_at": finished,
        }

    def build_lineage_payload(
        self,
        *,
        run_id: str,
        input_messages: list[Any] | None = None,
        system_prompt: str | None = None,
        output_text: str = "",
        model: str = "",
        provider: str = "anthropic",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float | None = None,
        parent_run_id: str = "",
        trace_id: str = "",
        prompt_template: str = "",
    ) -> dict:
        input_blob = serialize_messages_for_hash(input_messages)
        if system_prompt:
            input_blob = json.dumps(
                {"system": system_prompt, "messages": input_messages or []},
                sort_keys=True,
                default=str,
            )
        prompt_source = prompt_template or system_prompt or input_blob
        cost = cost_usd
        if cost is None:
            cost = calculate_cost(provider, model, input_tokens, output_tokens)
        return {
            "run_id": run_id,
            "input_hash": hash_data(input_messages or []),
            "prompt_hash": hash_content(prompt_source) if prompt_source else "",
            "output_hash": hash_content(output_text) if output_text else "",
            "prompt_template": prompt_template or "",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cost_usd": cost,
            "parent_run_id": parent_run_id,
            "trace_id": trace_id,
            "retrieval_chunks": [],
            "tool_calls": [],
            "chain_depth": 1,
        }

    def _submit(self, fn: Any, *args: Any, **kwargs: Any) -> None:
        if self.async_delivery:
            self._futures.append(self._executor.submit(fn, *args, **kwargs))
            return
        fn(*args, **kwargs)

    def record_trace(self, payload: dict) -> None:
        self._submit(self._send_trace, payload)

    def record_lineage(self, payload: dict) -> None:
        self._submit(self._send_lineage, payload)

    def record_claude_call(
        self,
        *,
        run_id: str | None = None,
        model: str,
        input_messages: list[Any] | None = None,
        system_prompt: str | None = None,
        output_text: str | None = None,
        response: Any = None,
        usage: Any | None = None,
        duration_ms: int,
        status: str = "success",
        started_at: str | None = None,
        finished_at: str | None = None,
        pii_masked: bool = True,
        prompt_template: str = "",
        parent_run_id: str = "",
        trace_id: str = "",
    ) -> str:
        """Record a Claude/Anthropic call to Forge. Returns the run_id used."""
        resolved_run_id = run_id or str(uuid.uuid4())
        resolved_output = extract_output_text(output_text, response=response)
        resolved_usage = usage or getattr(response, "usage", None)
        input_tokens, output_tokens = extract_usage_tokens(resolved_usage)
        steps = None
        if self.include_raw_steps:
            steps = [
                {
                    "type": "model_call",
                    "timestamp": finished_at or _utc_now(),
                    "content": (
                        f"model={model} input_tokens={input_tokens} "
                        f"output_tokens={output_tokens}"
                    ),
                    "duration_ms": duration_ms,
                }
            ]
        trace_payload = self.build_trace_payload(
            run_id=resolved_run_id,
            model=model,
            provider="anthropic",
            status=status,
            duration_ms=duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            started_at=started_at,
            finished_at=finished_at,
            pii_masked=pii_masked,
            steps=steps,
        )
        lineage_payload = self.build_lineage_payload(
            run_id=resolved_run_id,
            input_messages=input_messages,
            system_prompt=system_prompt,
            output_text=resolved_output,
            model=model,
            provider="anthropic",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=trace_payload["estimated_cost"],
            parent_run_id=parent_run_id,
            trace_id=trace_id,
            prompt_template=prompt_template,
        )
        self.record_trace(trace_payload)
        self.record_lineage(lineage_payload)
        return resolved_run_id

    def _send_trace(self, payload: dict) -> None:
        try:
            sync_external_trace(
                project_id=self.project_id,
                system_id=self.system_id,
                ingestion_token=self.ingestion_token,
                payload=payload,
                cloud_url=self.cloud_url,
            )
        except Exception:
            logger.exception(
                "Ryva Forge trace ingest failed for run_id=%s", payload.get("run_id")
            )

    def _send_lineage(self, payload: dict) -> None:
        try:
            sync_external_lineage(
                project_id=self.project_id,
                system_id=self.system_id,
                ingestion_token=self.ingestion_token,
                payload=payload,
                cloud_url=self.cloud_url,
            )
        except Exception:
            logger.exception(
                "Ryva Forge lineage ingest failed for run_id=%s", payload.get("run_id")
            )

    def flush(self, timeout: float = 30.0) -> None:
        for future in self._futures:
            try:
                future.result(timeout=timeout)
            except Exception:
                logger.exception("Ryva Forge ingest delivery failed")
        self._futures.clear()

    def close(self) -> None:
        self.flush()
        self._executor.shutdown(wait=True, cancel_futures=False)
