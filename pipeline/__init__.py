"""Pipeline package — lazy exports; avoid eager IDP / full-app imports."""

from __future__ import annotations

from typing import Any

__all__ = ["answer_legal_prompt"]


def __getattr__(name: str) -> Any:
    if name == "answer_legal_prompt":
        from pipeline.app.pipeline import answer_legal_prompt

        return answer_legal_prompt
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
