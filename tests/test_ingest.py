from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ryva.ingest import (
    ForgeReporter,
    extract_output_text,
    extract_usage_tokens,
    serialize_messages_for_hash,
)
from ryva.integrations.anthropic import instrumented_client


@pytest.fixture
def reporter() -> ForgeReporter:
    return ForgeReporter(
        project_id="proj-1",
        system_id="sys-1",
        ingestion_token="test-token",
        cloud_url="https://forge.example.com",
        async_delivery=False,
    )


def test_from_env_requires_configuration(monkeypatch):
    monkeypatch.delenv("RYVA_PROJECT_ID", raising=False)
    monkeypatch.delenv("RYVA_SYSTEM_ID", raising=False)
    monkeypatch.delenv("RYVA_INGESTION_TOKEN", raising=False)
    with pytest.raises(ValueError, match="Missing required Forge ingest configuration"):
        ForgeReporter.from_env()
    assert ForgeReporter.from_env(optional=True) is None


def test_from_env_reads_configuration(monkeypatch):
    monkeypatch.setenv("RYVA_PROJECT_ID", "proj-abc")
    monkeypatch.setenv("RYVA_SYSTEM_ID", "sys-abc")
    monkeypatch.setenv("RYVA_INGESTION_TOKEN", "token-abc")
    reporter = ForgeReporter.from_env()
    assert reporter is not None
    assert reporter.project_id == "proj-abc"
    assert reporter.system_id == "sys-abc"
    assert reporter.ingestion_token == "token-abc"


def test_serialize_messages_for_hash_is_stable():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    assert serialize_messages_for_hash(messages) == serialize_messages_for_hash(messages)


def test_extract_output_text_from_response_object():
    block = MagicMock()
    block.text = "routed to scheduling"
    response = MagicMock(content=[block])
    assert extract_output_text(response=response) == "routed to scheduling"


def test_extract_usage_tokens_from_dict():
    assert extract_usage_tokens({"input_tokens": 10, "output_tokens": 4}) == (10, 4)


def test_build_trace_payload_includes_cost(reporter: ForgeReporter):
    payload = reporter.build_trace_payload(
        run_id="run-1",
        model="claude-sonnet-4-5",
        duration_ms=120,
        input_tokens=1000,
        output_tokens=200,
    )
    assert payload["run_id"] == "run-1"
    assert payload["provider"] == "anthropic"
    assert payload["estimated_cost"] > 0
    assert payload["pii_masked"] is True
    assert len(payload["steps"]) == 2


def test_build_lineage_payload_hashes_content(reporter: ForgeReporter):
    payload = reporter.build_lineage_payload(
        run_id="run-1",
        input_messages=[{"role": "user", "content": "intake text"}],
        output_text="route to nurse review",
        model="claude-sonnet-4-5",
        input_tokens=100,
        output_tokens=20,
    )
    assert payload["input_hash"].startswith("sha256:")
    assert payload["output_hash"].startswith("sha256:")
    assert payload["prompt_hash"].startswith("sha256:")


@patch("ryva.ingest.sync_external_trace")
@patch("ryva.ingest.sync_external_lineage")
def test_record_claude_call_posts_trace_and_lineage(
    mock_lineage,
    mock_trace,
    reporter: ForgeReporter,
):
    run_id = reporter.record_claude_call(
        run_id="run-42",
        model="claude-sonnet-4-5",
        input_messages=[{"role": "user", "content": "help"}],
        output_text="done",
        usage={"input_tokens": 12, "output_tokens": 3},
        duration_ms=50,
    )
    assert run_id == "run-42"
    mock_trace.assert_called_once()
    mock_lineage.assert_called_once()
    trace_kwargs = mock_trace.call_args.kwargs
    assert trace_kwargs["project_id"] == "proj-1"
    assert trace_kwargs["system_id"] == "sys-1"
    assert trace_kwargs["payload"]["run_id"] == "run-42"


@patch("ryva.ingest.sync_external_trace")
@patch("ryva.ingest.sync_external_lineage")
def test_instrumented_client_records_calls(mock_lineage, mock_trace, reporter: ForgeReporter):
    messages = MagicMock()
    response = MagicMock()
    response.usage = MagicMock(input_tokens=8, output_tokens=2)
    response.content = [MagicMock(text="ok")]
    messages.create.return_value = response

    client = MagicMock(messages=messages)
    wrapped = instrumented_client(client=client, reporter=reporter)
    wrapped.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=64,
        messages=[{"role": "user", "content": "hello"}],
    )
    mock_trace.assert_called_once()
    mock_lineage.assert_called_once()
