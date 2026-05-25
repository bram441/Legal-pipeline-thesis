"""KB compiler backend selection (JSON-IR only)."""

from __future__ import annotations

import os
from contextlib import contextmanager

KB_BACKEND_CHOICES = ("json_ir",)


def get_kb_backend_from_env() -> str:
    return "json_ir"


@contextmanager
def kb_backend_env_override(backend: str | None):
    if backend is None:
        yield
        return
    if backend != "json_ir":
        raise ValueError("Unknown kb backend: " + str(backend) + " (only json_ir is supported)")
    key = "PIPELINE_KB_BACKEND"
    saved = os.environ.get(key)
    try:
        os.environ[key] = "json_ir"
        yield
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved
