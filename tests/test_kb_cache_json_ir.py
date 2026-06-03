"""Outer KB cache must not multiply JSON_IR structured repair loops (Iteration 6.5)."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from pipeline.config import reload_config
from pipeline.kb.cache import (
    KBCacheError,
    get_or_compile_kb,
    json_ir_outer_cache_retries_enabled,
    resolve_max_repair_attempts,
)
from pipeline.kb.compile_strategy import strategy_metadata
from pipeline.kb.exceptions import LawCompilationError


def _law_compilation_error() -> LawCompilationError:
    return LawCompilationError(
        "JSON IR compilation failed.\nsymbol_versions=2, total_llm_calls=5, final_error=missing_helper_definition",
        repair_summary={
            "symbol_version_count": 2,
            "rules_attempt_count": 1,
            "total_kb_llm_calls": 5,
            "final_normalized_error_code": "missing_helper_definition",
        },
    )


@pytest.fixture(autouse=True)
def _clear_repair_env(monkeypatch):
    for key in (
        "PIPELINE_KB_MAX_REPAIR_ATTEMPTS",
        "JSON_IR_ALLOW_OUTER_CACHE_RETRIES",
        "JSON_IR_MAX_SYMBOL_VERSIONS",
        "JSON_IR_MAX_RULES_ATTEMPTS_PER_SYMBOL_VERSION",
        "JSON_IR_MAX_KB_LLM_CALLS",
    ):
        monkeypatch.delenv(key, raising=False)


@patch("pipeline.kb.cache.trace_enabled", return_value=False)
@patch("pipeline.kb.cache.get_kb_backend_from_env", return_value="json_ir")
@patch("pipeline.kb.cache.compile_law_to_kb_fo")
def test_json_ir_calls_compile_once_on_law_compilation_error(
    mock_compile, _backend, _trace, tmp_path
) -> None:
    mock_compile.side_effect = _law_compilation_error()
    with pytest.raises(KBCacheError) as exc_info:
        get_or_compile_kb(str(tmp_path), "sample law text")
    assert mock_compile.call_count == 1
    msg = str(exc_info.value)
    assert "structured_repair" in msg
    assert "total_kb_llm_calls=5" in msg
    assert "missing_helper_definition" in msg


def test_pipeline_kb_max_repair_attempts_ignored_for_json_ir_by_default(monkeypatch) -> None:
    monkeypatch.setenv("PIPELINE_KB_MAX_REPAIR_ATTEMPTS", "8")
    assert resolve_max_repair_attempts("json_ir", log_warnings=False) == 1


@patch("pipeline.kb.cache.trace_enabled", return_value=False)
@patch("pipeline.kb.cache.get_kb_backend_from_env", return_value="json_ir")
@patch("pipeline.kb.cache.compile_law_to_kb_fo")
def test_json_ir_outer_retries_only_when_explicitly_enabled(
    mock_compile, _backend, _trace, monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("JSON_IR_ALLOW_OUTER_CACHE_RETRIES", "1")
    monkeypatch.setenv("PIPELINE_KB_MAX_REPAIR_ATTEMPTS", "3")
    reload_config()
    mock_compile.side_effect = _law_compilation_error()
    with pytest.raises(KBCacheError):
        get_or_compile_kb(str(tmp_path), "sample law text")
    assert mock_compile.call_count == 3


def test_json_ir_allow_outer_cache_retries_env() -> None:
    os.environ["JSON_IR_ALLOW_OUTER_CACHE_RETRIES"] = "1"
    reload_config()
    try:
        assert json_ir_outer_cache_retries_enabled() is True
        assert resolve_max_repair_attempts("json_ir", log_warnings=False) == 8
    finally:
        os.environ.pop("JSON_IR_ALLOW_OUTER_CACHE_RETRIES", None)
        reload_config()


def test_strategy_metadata_json_ir_structured_repair(monkeypatch) -> None:
    monkeypatch.setenv("JSON_IR_MAX_SYMBOL_VERSIONS", "3")
    monkeypatch.setenv("JSON_IR_MAX_RULES_ATTEMPTS_PER_SYMBOL_VERSION", "3")
    monkeypatch.setenv("JSON_IR_MAX_KB_LLM_CALLS", "7")
    reload_config()
    meta = strategy_metadata("direct_json_ir_translate")
    assert meta["repair_enabled"] is True
    assert meta["json_ir_structured_repair_enabled"] is True
    assert meta["json_ir_max_symbol_versions"] == 3
    assert meta["json_ir_max_rules_attempts_per_symbol_version"] == 3
    assert meta["json_ir_max_kb_llm_calls"] == 7
    assert meta["json_ir_outer_cache_retries_enabled"] is False
    assert meta["json_ir_outer_cache_max_attempts"] == 1
