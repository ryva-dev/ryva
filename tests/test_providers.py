from __future__ import annotations

import pytest

from ryva.providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    get_provider,
)


class TestGetProvider:
    def test_anthropic(self):
        assert isinstance(get_provider("anthropic", {}), AnthropicProvider)

    def test_openai(self):
        assert isinstance(get_provider("openai", {}), OpenAIProvider)

    def test_ollama(self):
        assert isinstance(get_provider("ollama", {}), OllamaProvider)

    def test_gemini(self):
        assert isinstance(get_provider("gemini", {}), GeminiProvider)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("unknown-provider", {})

    def test_unknown_lists_available(self):
        with pytest.raises(ValueError, match="anthropic"):
            get_provider("bad", {})


class TestAnthropicProvider:
    def test_uses_env_key(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key-123")
        provider = get_provider("anthropic", {})
        assert provider.api_key == "env-key-123"

    def test_config_key_overrides_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        provider = get_provider("anthropic", {"api_key": "config-key"})
        assert provider.api_key == "config-key"

    def test_empty_key_raises_on_complete(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = AnthropicProvider(api_key="")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            provider.complete("hello", "claude-sonnet-4-5", 100)

    def test_empty_key_raises_on_complete_with_usage(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        provider = AnthropicProvider(api_key="")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            provider.complete_with_usage("hello", "claude-sonnet-4-5", 100)


class TestOpenAIProvider:
    def test_uses_env_key(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "oai-env-key")
        provider = get_provider("openai", {})
        assert provider.api_key == "oai-env-key"

    def test_config_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = get_provider("openai", {"api_key": "oai-cfg-key"})
        assert provider.api_key == "oai-cfg-key"

    def test_empty_key_raises_on_complete(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = OpenAIProvider(api_key="")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            provider.complete("hello", "gpt-4o", 100)

    def test_empty_key_raises_on_complete_with_usage(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = OpenAIProvider(api_key="")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            provider.complete_with_usage("hello", "gpt-4o", 100)


class TestOllamaProvider:
    def test_default_base_url(self):
        provider = get_provider("ollama", {})
        assert provider.base_url == "http://localhost:11434"

    def test_custom_base_url(self):
        provider = get_provider("ollama", {"base_url": "http://custom:8080"})
        assert provider.base_url == "http://custom:8080"


class TestGeminiProvider:
    def test_uses_env_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gemini-env-key")
        provider = get_provider("gemini", {})
        assert provider.api_key == "gemini-env-key"

    def test_empty_key_raises_on_complete(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        provider = GeminiProvider(api_key="")
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            provider.complete("hello", "gemini-1.5-pro", 100)

    def test_empty_key_raises_on_complete_with_usage(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        provider = GeminiProvider(api_key="")
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            provider.complete_with_usage("hello", "gemini-1.5-pro", 100)


class TestBedrockProvider:
    def test_bedrock_provider_available(self):
        from ryva.providers import PROVIDERS
        assert "bedrock" in PROVIDERS

    def test_get_provider_bedrock(self):
        from ryva.providers import BedrockProvider
        provider = get_provider("bedrock", {})
        assert isinstance(provider, BedrockProvider)

    def test_default_region(self, monkeypatch):
        monkeypatch.delenv("AWS_DEFAULT_REGION", raising=False)
        from ryva.providers import BedrockProvider
        p = BedrockProvider()
        assert p.region == "us-east-1"

    def test_region_from_env(self, monkeypatch):
        monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
        from ryva.providers import BedrockProvider
        p = BedrockProvider()
        assert p.region == "eu-west-1"

    def test_region_from_config(self):
        provider = get_provider("bedrock", {"region": "ap-southeast-1"})
        assert provider.region == "ap-southeast-1"

    def test_bedrock_request_format_claude(self, monkeypatch):
        """Verify anthropic_version is included in the request body for Claude models."""
        import json as _json
        import sys
        from unittest.mock import MagicMock

        from ryva.providers import BedrockProvider

        fake_response_body = {
            "content": [{"text": "hello"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        mock_client = MagicMock()
        mock_client.invoke_model.return_value = {
            "body": MagicMock(read=lambda: _json.dumps(fake_response_body).encode())
        }
        mock_boto3 = MagicMock()
        mock_boto3.client.return_value = mock_client
        monkeypatch.setitem(sys.modules, "boto3", mock_boto3)

        p = BedrockProvider(region="us-east-1")
        text, usage = p.complete_with_usage("hello", "anthropic.claude-3-haiku", 100)

        call_kwargs = mock_boto3.client.return_value.invoke_model.call_args[1]
        body = _json.loads(call_kwargs["body"])
        assert "anthropic_version" in body
        assert body["anthropic_version"] == "bedrock-2023-05-31"
        assert text == "hello"
        assert usage["input_tokens"] == 10


class TestAzureOpenAIProvider:
    def test_azure_openai_provider_available(self):
        from ryva.providers import PROVIDERS
        assert "azure_openai" in PROVIDERS

    def test_get_provider_azure_openai(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://my.openai.azure.com")
        from ryva.providers import AzureOpenAIProvider
        provider = get_provider("azure_openai", {})
        assert isinstance(provider, AzureOpenAIProvider)
        assert provider.api_key == "az-key"
        assert provider.endpoint == "https://my.openai.azure.com"

    def test_raises_without_creds(self, monkeypatch):
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        from ryva.providers import AzureOpenAIProvider
        p = AzureOpenAIProvider()
        with pytest.raises(ValueError, match="AZURE_OPENAI"):
            p.complete_with_usage("hello", "my-deployment", 100)

    def test_default_api_version(self, monkeypatch):
        monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
        from ryva.providers import AzureOpenAIProvider
        p = AzureOpenAIProvider(api_key="k", endpoint="https://e.com")
        assert p.api_version == "2024-02-01"

    def test_api_version_from_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2025-01-01")
        from ryva.providers import AzureOpenAIProvider
        p = AzureOpenAIProvider(api_key="k", endpoint="https://e.com")
        assert p.api_version == "2025-01-01"
