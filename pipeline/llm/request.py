"""Build OpenAI-compatible chat completion kwargs with provider-safe optional params."""

from __future__ import annotations

import os
from typing import Any

from pipeline.config import config_section
from pipeline.llm.client import get_llm_provider


def _llm_flags() -> dict[str, bool]:
    sec = config_section("llm")
    provider = get_llm_provider()
    provider_defaults = {
        "use_seed": provider != "openrouter",
        "use_response_format": provider != "openrouter",
        "use_reasoning_effort": False,
    }

    def _flag(name: str) -> bool:
        val = sec.get(name)
        if val is None:
            return provider_defaults[name]
        if isinstance(val, bool):
            return val
        return str(val).strip().lower() in ("1", "true", "yes", "on")

    return {name: _flag(name) for name in provider_defaults}


def _openai_sampling_from_config() -> dict[str, Any]:
    """Temperature / top_p / seed from config openai section and legacy env vars."""
    out: dict[str, Any] = {}
    sec = config_section("openai")

    raw_t = os.getenv("PIPELINE_OPENAI_TEMPERATURE")
    if raw_t is None or not str(raw_t).strip():
        temp = sec.get("temperature")
        raw_t = str(temp) if temp is not None else "0"
    try:
        out["temperature"] = float(str(raw_t).strip())
    except ValueError:
        out["temperature"] = 0.0

    raw_p = os.getenv("PIPELINE_OPENAI_TOP_P")
    if raw_p is None or not str(raw_p).strip():
        top_p = sec.get("top_p")
        raw_p = str(top_p) if top_p is not None else "1"
    try:
        top_p = float(str(raw_p).strip())
    except ValueError:
        top_p = 1.0
    if top_p > 0.0:
        out["top_p"] = top_p

    seed_s = (os.getenv("PIPELINE_OPENAI_SEED") or "").strip()
    if not seed_s:
        seed_cfg = sec.get("seed")
        if seed_cfg is not None and str(seed_cfg).strip() != "":
            seed_s = str(seed_cfg).strip()
    if seed_s and _llm_flags()["use_seed"]:
        try:
            out["seed"] = int(seed_s)
        except ValueError:
            pass
    return out


def chat_completion_sampling_kwargs() -> dict[str, Any]:
    """Backward-compatible sampling kwargs (temperature, top_p, optional seed)."""
    return _openai_sampling_from_config()


def build_chat_completion_kwargs(
    *,
    model: str,
    messages: Any,
    response_format: Any | None = None,
    reasoning_effort: Any | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """
    Assemble kwargs for ``client.chat.completions.create``.

    Optional OpenAI-specific parameters are included only when enabled in config.
    """
    flags = _llm_flags()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        **_openai_sampling_from_config(),
    }

    if response_format is not None and flags["use_response_format"]:
        kwargs["response_format"] = response_format

    if reasoning_effort is not None and flags["use_reasoning_effort"]:
        kwargs["reasoning_effort"] = reasoning_effort

    for key, val in extra.items():
        if val is None:
            continue
        if key == "response_format" and not flags["use_response_format"]:
            continue
        if key == "seed" and not flags["use_seed"]:
            continue
        if key == "reasoning_effort" and not flags["use_reasoning_effort"]:
            continue
        kwargs[key] = val

    return kwargs
