"""Tests for OpenAI/OpenRouter client resolution and request builder."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.config import reload_config, save_effective_config
from pipeline.llm.client import (
    base_url_host,
    get_llm_base_url,
    get_llm_client,
    get_llm_model,
    get_llm_provider,
    reset_llm_client_cache,
)
from pipeline.llm.request import build_chat_completion_kwargs


@pytest.fixture(autouse=True)
def _clear_llm_cache(monkeypatch):
    reset_llm_client_cache()
    reload_config()
    yield
    reset_llm_client_cache()
    reload_config()


def test_openai_direct_no_base_url_by_default(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    reset_llm_client_cache()
    assert get_llm_provider() == "openai"
    assert get_llm_base_url() is None


def test_openrouter_resolves_default_base_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    reset_llm_client_cache()
    assert get_llm_provider() == "openrouter"
    assert get_llm_base_url() == "https://openrouter.ai/api/v1"


def test_llm_model_overrides_openai_model(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "custom/model-a")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    reset_llm_client_cache()
    assert get_llm_model() == "custom/model-a"


def test_openrouter_model_from_openrouter_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-5.5")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    reset_llm_client_cache()
    assert get_llm_model() == "openai/gpt-5.5"


def test_effective_config_excludes_api_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-secret-key")
    monkeypatch.setenv("LLM_API_KEY", "llm-secret")
    reset_llm_client_cache()
    out = tmp_path / "effective_config.json"
    save_effective_config(out)
    text = out.read_text(encoding="utf-8")
    assert "sk-secret" not in text
    assert "or-secret" not in text
    assert "llm-secret" not in text
    loaded = json.loads(text)
    assert "llm_runtime" in loaded
    assert loaded["llm_runtime"].get("provider") in ("openai", "openrouter")


def test_request_builder_omits_seed_when_disabled(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    reload_config()
    kwargs = build_chat_completion_kwargs(
        model="openai/gpt-5.5",
        messages=[{"role": "user", "content": "hi"}],
        seed=42,
        response_format={"type": "json_object"},
    )
    assert "seed" not in kwargs
    assert "response_format" not in kwargs
    assert kwargs["model"] == "openai/gpt-5.5"


def test_request_builder_includes_response_format_when_enabled(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    reload_config()
    rf = {"type": "json_object"}
    kwargs = build_chat_completion_kwargs(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "hi"}],
        response_format=rf,
    )
    assert kwargs.get("response_format") == rf


def test_get_llm_client_openai_no_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    reset_llm_client_cache()
    with patch("openai.OpenAI") as mock_openai:
        get_llm_client()
        _, kwargs = mock_openai.call_args
        assert "base_url" not in kwargs or kwargs.get("base_url") is None


def test_base_url_host_parsing():
    assert base_url_host("https://openrouter.ai/api/v1") == "openrouter.ai"


def test_openrouter_client_passes_optional_headers(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://example.com")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "Legal Pipeline")
    reset_llm_client_cache()
    with patch("openai.OpenAI") as mock_openai:
        get_llm_client()
        _, kwargs = mock_openai.call_args
        headers = kwargs.get("default_headers") or {}
        assert headers.get("HTTP-Referer") == "https://example.com"
        assert headers.get("X-Title") == "Legal Pipeline"
