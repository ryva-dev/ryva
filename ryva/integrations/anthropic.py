"""Drop-in Anthropic client instrumentation for Ryva Forge evidence capture."""
from __future__ import annotations

import time
from typing import Any

from ryva.ingest import ForgeReporter


class _InstrumentedMessages:
    def __init__(self, messages: Any, reporter: ForgeReporter | None) -> None:
        self._messages = messages
        self._reporter = reporter

    def create(self, *args: Any, **kwargs: Any) -> Any:
        started_perf = time.perf_counter()
        response = self._messages.create(*args, **kwargs)
        if self._reporter is not None:
            duration_ms = max(1, int((time.perf_counter() - started_perf) * 1000))
            self._reporter.record_claude_call(
                model=str(kwargs.get("model", "")),
                input_messages=kwargs.get("messages"),
                system_prompt=kwargs.get("system"),
                response=response,
                duration_ms=duration_ms,
                pii_masked=not self._reporter.include_raw_steps,
            )
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._messages, name)


class InstrumentedAnthropic:
    """Anthropic client wrapper that forwards traces to Ryva Forge when configured."""

    def __init__(
        self,
        client: Any | None = None,
        reporter: ForgeReporter | None = None,
        **kwargs: Any,
    ) -> None:
        import anthropic

        self._client = client or anthropic.Anthropic(**kwargs)
        self._reporter = (
            reporter if reporter is not None else ForgeReporter.from_env(optional=True)
        )

    @property
    def messages(self) -> _InstrumentedMessages:
        return _InstrumentedMessages(self._client.messages, self._reporter)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)


def instrumented_client(
    client: Any | None = None,
    reporter: ForgeReporter | None = None,
    **kwargs: Any,
) -> InstrumentedAnthropic:
    """Return an Anthropic-compatible client that reports calls to Forge."""
    return InstrumentedAnthropic(client=client, reporter=reporter, **kwargs)
