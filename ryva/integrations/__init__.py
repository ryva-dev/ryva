"""Optional runtime integrations for production apps."""

from ryva.integrations.anthropic import instrumented_client

__all__ = ["instrumented_client"]
