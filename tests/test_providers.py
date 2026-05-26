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
