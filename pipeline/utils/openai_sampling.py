"""Reproducible defaults for OpenAI chat completions (thesis / benchmarks).

Override with environment variables (no law- or case-specific logic):
  PIPELINE_OPENAI_TEMPERATURE  default 0
  PIPELINE_OPENAI_TOP_P        default 1
  PIPELINE_OPENAI_SEED         optional integer (models that support ``seed``)
"""

from __future__ import annotations

import os
from typing import Any


def chat_completion_sampling_kwargs() -> dict[str, Any]:
    out: dict[str, Any] = {}
    raw_t = (os.getenv("PIPELINE_OPENAI_TEMPERATURE") or "0").strip()
    try:
        out["temperature"] = float(raw_t)
    except ValueError:
        out["temperature"] = 0.0

    raw_p = (os.getenv("PIPELINE_OPENAI_TOP_P") or "1").strip()
    try:
        top_p = float(raw_p)
    except ValueError:
        top_p = 1.0
    if top_p > 0.0:
        out["top_p"] = top_p

    seed_s = (os.getenv("PIPELINE_OPENAI_SEED") or "").strip()
    if seed_s:
        try:
            out["seed"] = int(seed_s)
        except ValueError:
            pass
    return out
