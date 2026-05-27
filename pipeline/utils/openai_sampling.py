"""Reproducible defaults for OpenAI chat completions (thesis / benchmarks).

Override with environment variables (no law- or case-specific logic):
  PIPELINE_OPENAI_TEMPERATURE  default 0
  PIPELINE_OPENAI_TOP_P        default 1
  PIPELINE_OPENAI_SEED         optional integer (models that support ``seed``)

Prefer ``pipeline.llm.request.build_chat_completion_kwargs`` for new code.
"""

from __future__ import annotations

from pipeline.llm.request import chat_completion_sampling_kwargs as _chat_completion_sampling_kwargs

# Re-export for backward compatibility.
chat_completion_sampling_kwargs = _chat_completion_sampling_kwargs
