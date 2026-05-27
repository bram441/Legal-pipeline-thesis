"""Central LLM client and model resolution (OpenAI direct + OpenRouter)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from pipeline.config import config_section

_OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_DEFAULT_MODEL = "gpt-4.1-mini"


def get_llm_provider() -> str:
    """Return ``openai`` or ``openrouter``."""
    raw = (os.getenv("LLM_PROVIDER") or config_section("llm").get("provider") or "openai")
    p = str(raw).strip().lower()
    if p in ("openrouter", "open_router"):
        return "openrouter"
    return "openai"


def _cfg_model() -> str | None:
    m = config_section("llm").get("model")
    if m is None:
        return None
    s = str(m).strip()
    return s or None


def _cfg_base_url() -> str | None:
    u = config_section("llm").get("base_url")
    if u is None:
        return None
    s = str(u).strip()
    return s or None


def get_llm_api_key() -> str | None:
    """Resolve API key without logging it."""
    if get_llm_provider() == "openrouter":
        for key in ("LLM_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY"):
            v = (os.getenv(key) or "").strip()
            if v:
                return v
        return None
    for key in ("LLM_API_KEY", "OPENAI_API_KEY"):
        v = (os.getenv(key) or "").strip()
        if v:
            return v
    return None


def get_llm_base_url() -> str | None:
    """Resolved base URL, or None for OpenAI default endpoint."""
    if get_llm_provider() == "openrouter":
        for key in ("LLM_BASE_URL", "OPENROUTER_BASE_URL"):
            v = (os.getenv(key) or "").strip()
            if v:
                return v
        cfg = _cfg_base_url()
        return cfg or _OPENROUTER_DEFAULT_BASE_URL
    for key in ("LLM_BASE_URL", "OPENAI_BASE_URL"):
        v = (os.getenv(key) or "").strip()
        if v:
            return v
    return _cfg_base_url()


def get_llm_model(*, stage: str | None = None) -> str:
    """Resolved model id for chat completions."""
    if stage == "nl_explanation":
        expl = (os.getenv("OPENAI_EXPLAINER_MODEL") or "").strip()
        if expl:
            return expl

    if get_llm_provider() == "openrouter":
        for key in ("LLM_MODEL", "OPENROUTER_MODEL", "OPENAI_MODEL"):
            v = (os.getenv(key) or "").strip()
            if v:
                return v
    else:
        for key in ("LLM_MODEL", "OPENAI_MODEL"):
            v = (os.getenv(key) or "").strip()
            if v:
                return v

    cfg = _cfg_model()
    if cfg:
        return cfg
    return _DEFAULT_MODEL


def base_url_host(base_url: str | None = None) -> str | None:
    """Hostname for reporting (no credentials)."""
    url = (base_url or get_llm_base_url() or "").strip()
    if not url:
        return None
    try:
        parsed = urlparse(url)
        if parsed.netloc:
            return parsed.netloc
        if parsed.path:
            return parsed.path.lstrip("/").split("/")[0] or None
    except Exception:
        return None
    return None


def reset_llm_client_cache() -> None:
    get_llm_client.cache_clear()


@lru_cache(maxsize=1)
def get_llm_client() -> Any:
    """Cached OpenAI SDK client (works for OpenAI direct and OpenRouter)."""
    api_key = get_llm_api_key()
    if not api_key:
        provider = get_llm_provider()
        if provider == "openrouter":
            raise RuntimeError(
                "Missing API key for OpenRouter (set OPENROUTER_API_KEY or LLM_API_KEY)"
            )
        raise RuntimeError("Missing API key (set OPENAI_API_KEY or LLM_API_KEY)")

    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("OpenAI SDK not installed/importable: " + str(e)) from e

    kwargs: dict[str, Any] = {"api_key": api_key}
    base_url = get_llm_base_url()
    if base_url:
        kwargs["base_url"] = base_url

    if get_llm_provider() == "openrouter":
        headers: dict[str, str] = {}
        referer = (os.getenv("OPENROUTER_HTTP_REFERER") or "").strip()
        title = (os.getenv("OPENROUTER_APP_TITLE") or "").strip()
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        if headers:
            kwargs["default_headers"] = headers

    timeout = config_section("llm").get("timeout_seconds")
    if timeout is not None:
        try:
            kwargs["timeout"] = float(timeout)
        except (TypeError, ValueError):
            pass

    return OpenAI(**kwargs)


def llm_config_for_artifact() -> dict[str, Any]:
    """Sanitized LLM settings for effective_config / matrix (no secrets)."""
    openai_model = (os.getenv("OPENAI_MODEL") or "").strip() or None
    openrouter_model = (os.getenv("OPENROUTER_MODEL") or "").strip() or None
    resolved = get_llm_model()
    out: dict[str, Any] = {
        "provider": get_llm_provider(),
        "model": resolved,
        "base_url_host": base_url_host(),
    }
    if openai_model:
        out["openai"] = {"model": openai_model}
    if openrouter_model and openrouter_model != resolved:
        out["openrouter"] = {"model": openrouter_model}
    return out
