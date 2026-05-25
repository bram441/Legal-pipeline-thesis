"""JSON-IR KB cache manifest invalidates stale kb.fo artifacts."""

from __future__ import annotations

import os

from pipeline.kb.cache_version import (
    JSON_IR_KB_CACHE_VERSION,
    cache_manifest_matches,
    invalidate_kb_cache_files,
    write_cache_manifest,
)


def test_stale_manifest_invalidates_json_ir_cache(tmp_path):
    cache_dir = tmp_path / "translated" / "json_ir"
    cache_dir.mkdir(parents=True)
    kb_path = cache_dir / "kb.fo"
    kb_path.write_text("vocabulary V {\n", encoding="utf-8")
    assert cache_manifest_matches(str(cache_dir), kb_backend="json_ir") is False


def test_current_manifest_matches(tmp_path):
    cache_dir = tmp_path / "json_ir"
    cache_dir.mkdir()
    write_cache_manifest(str(cache_dir), kb_backend="json_ir")
    assert cache_manifest_matches(str(cache_dir), kb_backend="json_ir") is True


def test_invalidate_removes_kb_files(tmp_path):
    cache_dir = tmp_path / "json_ir"
    cache_dir.mkdir()
    (cache_dir / "kb.fo").write_text("x", encoding="utf-8")
    (cache_dir / "kb_schema.json").write_text("{}", encoding="utf-8")
    invalidate_kb_cache_files(str(cache_dir))
    assert not os.path.isfile(cache_dir / "kb.fo")
    assert not os.path.isfile(cache_dir / "kb_schema.json")
