from __future__ import annotations
import os
from abc import ABC, abstractmethod


class BaseProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, model: str, max_tokens: int) -> str:
        pass


class AnthropicProvider(BaseProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def complete(self, prompt: str, model: str, max_tokens: int) -> str:
        try:
            import anthropic
        except ImportError:
            raise ImportError("Run: uv add anthropic")

        client = anthropic.Anthropic(api_key=self.api_key)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return msg.content[0].text


class OpenAIProvider(BaseProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def complete(self, prompt: str, model: str, max_tokens: int) -> str:
        try:
            import openai
        except ImportError:
            raise ImportError("Run: uv add openai")

        client = openai.OpenAI(api_key=self.api_key)
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}]
        )
        return resp.choices[0].message.content


class OllamaProvider(BaseProvider):
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url

    def complete(self, prompt: str, model: str, max_tokens: int) -> str:
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
                "options": {"num_predict": max_tokens}
            },
            timeout=120.0
        )
        response.raise_for_status()
        return response.json().get("response", "")


class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")

    def complete(self, prompt: str, model: str, max_tokens: int) -> str:
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
                "generationConfig": {"maxOutputTokens": max_tokens}
            },
            timeout=60.0
        )
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


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

    if name == "anthropic":
        from ryva.utils import resolve_env_vars
        api_key = resolve_env_vars(config.get("api_key", ""))
        return cls(api_key=api_key)
    elif name == "openai":
        from ryva.utils import resolve_env_vars
        api_key = resolve_env_vars(config.get("api_key", ""))
        return cls(api_key=api_key)
    elif name == "ollama":
        return cls(base_url=config.get("base_url", "http://localhost:11434"))
    elif name == "gemini":
        from ryva.utils import resolve_env_vars
        api_key = resolve_env_vars(config.get("api_key", ""))
        return cls(api_key=api_key)

    return cls()