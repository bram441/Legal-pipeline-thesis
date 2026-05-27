"""Provider-agnostic LLM client and request builders (OpenAI SDK + OpenRouter)."""

from pipeline.llm.client import (
    base_url_host,
    get_llm_api_key,
    get_llm_base_url,
    get_llm_client,
    get_llm_model,
    get_llm_provider,
    llm_config_for_artifact,
    reset_llm_client_cache,
)
from pipeline.llm.request import build_chat_completion_kwargs, chat_completion_sampling_kwargs

__all__ = [
    "base_url_host",
    "build_chat_completion_kwargs",
    "chat_completion_sampling_kwargs",
    "get_llm_api_key",
    "get_llm_base_url",
    "get_llm_client",
    "get_llm_model",
    "get_llm_provider",
    "llm_config_for_artifact",
    "reset_llm_client_cache",
]
