"""Version key for JSON-IR KB disk cache invalidation.

Bump ``JSON_IR_KB_CACHE_VERSION`` when compile-loop semantics, symbol schema
metadata (e.g. legal_output), repair routing, or FO rendering expectations change
so smoke runs do not silently reuse stale ``kb.fo`` artifacts.
"""

from __future__ import annotations

import json
import os
from typing import Any

# Bump when JSON-IR KB compile / schema metadata semantics change materially.
JSON_IR_KB_CACHE_VERSION = "json_ir_kb_v20260524_1"

MANIFEST_FILENAME = "cache_manifest.json"


def cache_manifest_path(run_dir: str) -> str:
    return os.path.join(run_dir, MANIFEST_FILENAME)


def read_cache_manifest(run_dir: str) -> dict[str, Any] | None:
    path = cache_manifest_path(run_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def write_cache_manifest(run_dir: str, *, kb_backend: str) -> None:
    manifest = {
        "cache_version": JSON_IR_KB_CACHE_VERSION,
        "kb_backend": kb_backend,
    }
    path = cache_manifest_path(run_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")


def cache_manifest_matches(run_dir: str, *, kb_backend: str) -> bool:
    manifest = read_cache_manifest(run_dir)
    if not manifest:
        return False
    if str(manifest.get("cache_version") or "") != JSON_IR_KB_CACHE_VERSION:
        return False
    if str(manifest.get("kb_backend") or "") != str(kb_backend):
        return False
    return True


def invalidate_kb_cache_files(run_dir: str) -> None:
    for name in ("kb.fo", "kb_schema.json", MANIFEST_FILENAME, "kb_compile.log"):
        path = os.path.join(run_dir, name)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
