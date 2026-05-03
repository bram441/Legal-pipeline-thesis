"""KB compiler backend selection."""

from __future__ import annotations

import os
from contextlib import contextmanager

KB_BACKEND_CHOICES = ("legacy_fo", "json_ir")


def get_kb_backend_from_env() -> str:
    raw = (os.getenv("PIPELINE_KB_BACKEND") or "").strip().lower()
    if not raw:
        return "json_ir"
    if raw in ("fo", "legacy", "legacy_fo"):
        return "legacy_fo"
    if raw in ("json", "json_ir"):
        return "json_ir"
    return "json_ir"


@contextmanager
def kb_backend_env_override(backend: str | None):
    if backend is None:
        yield
        return
    if backend not in KB_BACKEND_CHOICES:
        raise ValueError("Unknown kb backend: " + str(backend))
    key = "PIPELINE_KB_BACKEND"
    saved = os.environ.get(key)
    try:
        os.environ[key] = backend
        yield
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved

