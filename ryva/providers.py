from __future__ import annotations

import json
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


class BedrockProvider(BaseProvider):
    """AWS Bedrock provider — uses boto3 credential chain (env vars, ~/.aws, IAM roles).

    Supports Anthropic Claude, Meta Llama, Amazon Titan, Mistral, and Cohere.
    No API key required; authentication is handled by the AWS SDK.
    Set AWS_DEFAULT_REGION or pass region= to the constructor.
    """

    def __init__(self, region: str = ""):
        self.region = region or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    def complete_with_usage(
        self, prompt: str, model: str, max_tokens: int
    ) -> tuple[str, dict]:
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for Bedrock support. "
                "Install it with: pip install boto3"
            )

        client = boto3.client("bedrock-runtime", region_name=self.region)

        if "anthropic.claude" in model:
            body: dict = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            }
        elif "amazon.titan" in model:
            body = {
                "inputText": prompt,
                "textGenerationConfig": {"maxTokenCount": max_tokens},
            }
        elif "meta.llama" in model:
            body = {"prompt": prompt, "max_gen_len": max_tokens}
        elif "mistral" in model:
            body = {
                "prompt": f"<s>[INST] {prompt} [/INST]",
                "max_tokens": max_tokens,
            }
        else:
            body = {"prompt": prompt, "max_tokens": max_tokens}

        response = client.invoke_model(
            modelId=model,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        response_body = json.loads(response["body"].read())

        if "anthropic.claude" in model:
            content = response_body.get("content", [{}])[0].get("text", "")
            input_tokens = response_body.get("usage", {}).get("input_tokens", 0)
            output_tokens = response_body.get("usage", {}).get("output_tokens", 0)
        elif "amazon.titan" in model:
            content = response_body.get("results", [{}])[0].get("outputText", "")
            input_tokens = response_body.get("inputTextTokenCount", 0)
            output_tokens = response_body.get("results", [{}])[0].get("tokenCount", 0)
        elif "meta.llama" in model:
            content = response_body.get("generation", "")
            input_tokens = response_body.get("prompt_token_count", 0)
            output_tokens = response_body.get("generation_token_count", 0)
        else:
            content = str(response_body)
            input_tokens = 0
            output_tokens = 0

        return content, {"input_tokens": input_tokens, "output_tokens": output_tokens}


class AzureOpenAIProvider(BaseProvider):
    """Azure OpenAI provider — HIPAA BAA available from Microsoft.

    Required env vars: AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT.
    Optional:         AZURE_OPENAI_API_VERSION (default 2024-02-01).
    The model parameter should be your Azure deployment name.
    """

    def __init__(self, api_key: str = "", endpoint: str = "", api_version: str = ""):
        self.api_key = api_key or os.environ.get("AZURE_OPENAI_API_KEY", "")
        self.endpoint = endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self.api_version = (
            api_version
            or os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")
        )

    def complete_with_usage(
        self, prompt: str, model: str, max_tokens: int
    ) -> tuple[str, dict]:
        if not self.api_key or not self.endpoint:
            raise ValueError(
                "Azure OpenAI requires AZURE_OPENAI_API_KEY and "
                "AZURE_OPENAI_ENDPOINT environment variables."
            )
        try:
            from openai import AzureOpenAI
        except ImportError:
            raise ImportError("Run: uv add openai")

        client = AzureOpenAI(
            api_key=self.api_key,
            azure_endpoint=self.endpoint,
            api_version=self.api_version,
        )
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


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
    "bedrock": BedrockProvider,
    "azure_openai": AzureOpenAIProvider,
}


def get_provider(name: str, config: dict | None = None) -> BaseProvider:
    config = config or {}
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
    elif name == "bedrock":
        return cls(region=config.get("region", ""))
    elif name == "azure_openai":
        from ryva.utils import resolve_env_vars
        api_key = resolve_env_vars(config.get("api_key", ""))
        endpoint = resolve_env_vars(config.get("endpoint", ""))
        api_version = config.get("api_version", "")
        return cls(api_key=api_key, endpoint=endpoint, api_version=api_version)

    return cls()
