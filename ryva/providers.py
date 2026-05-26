from __future__ import annotations

import os
from abc import ABC, abstractmethod


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text.split()) * 1.3))


class BaseProvider(ABC):
    def complete(self, prompt: str, model: str, max_tokens: int) -> str:
        text, _ = self.complete_with_usage(prompt, model, max_tokens)
        return text

    @abstractmethod
    def complete_with_usage(
        self, prompt: str, model: str, max_tokens: int
    ) -> tuple[str, dict]:
        """Return (response_text, {"input_tokens": int, "output_tokens": int})."""


class AnthropicProvider(BaseProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def complete_with_usage(
        self, prompt: str, model: str, max_tokens: int
    ) -> tuple[str, dict]:
        if not self.api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Export it as an environment variable or set api_key in project.yml."
            )
        try:
            import anthropic
        except ImportError:
            raise ImportError("Run: uv add anthropic")

        client = anthropic.Anthropic(api_key=self.api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }
        return msg.content[0].text, usage


class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def complete_with_usage(
        self, prompt: str, model: str, max_tokens: int
    ) -> tuple[str, dict]:
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Export it as an environment variable or set api_key in project.yml."
            )
        try:
            import openai
        except ImportError:
            raise ImportError("Run: uv add openai")

        client = openai.OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        usage = {
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens,
        }
        return resp.choices[0].message.content, usage


class OllamaProvider(BaseProvider):
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    def complete_with_usage(
        self, prompt: str, model: str, max_tokens: int
    ) -> tuple[str, dict]:
        try:
            import httpx
        except ImportError:
            raise ImportError("Run: uv add httpx")

        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": max_tokens},
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("response", "")
        # Ollama returns token counts when stream=False
        usage = {
            "input_tokens": data.get("prompt_eval_count") or _estimate_tokens(prompt),
            "output_tokens": data.get("eval_count") or _estimate_tokens(text),
        }
        return text, usage


class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    def complete_with_usage(
        self, prompt: str, model: str, max_tokens: int
    ) -> tuple[str, dict]:
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. "
                "Export it as an environment variable or set api_key in project.yml."
            )
        try:
            import httpx
        except ImportError:
            raise ImportError("Run: uv add httpx")

        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"maxOutputTokens": max_tokens},
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        meta = data.get("usageMetadata", {})
        usage = {
            "input_tokens": meta.get("promptTokenCount") or _estimate_tokens(prompt),
            "output_tokens": meta.get("candidatesTokenCount") or _estimate_tokens(text),
        }
        return text, usage


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
}


def get_provider(name: str, config: dict) -> BaseProvider:
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: '{name}'. Available: {', '.join(PROVIDERS.keys())}"
        )

    cls = PROVIDERS[name]

    if name in ("anthropic", "openai", "gemini"):
        from ryva.utils import resolve_env_vars
        api_key = resolve_env_vars(config.get("api_key", ""))
        return cls(api_key=api_key)
    elif name == "ollama":
        return cls(base_url=config.get("base_url", "http://localhost:11434"))

    return cls()
