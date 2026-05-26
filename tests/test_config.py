"""Versioned config loading, env overrides, and effective_config artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pipeline.config import (
    CONFIG_PROFILE_ENV,
    activate_config_profile,
    apply_env_overrides,
    get_effective_config,
    load_config_files,
    reload_config,
    save_effective_config,
)


def test_default_config_loads():
    cfg = load_config_files()
    assert "json_ir" in cfg
    assert cfg["json_ir"]["max_symbol_versions"] == 3
    assert cfg["extraction"]["backend"] == "json_ir"


def test_env_override_json_ir_limits(monkeypatch):
    monkeypatch.setenv("JSON_IR_MAX_KB_LLM_CALLS", "15")
    reload_config()
    cfg = get_effective_config()
    assert cfg["json_ir"]["max_kb_llm_calls"] == 15
    reload_config()


def test_missing_local_config_falls_back_to_default(tmp_path, monkeypatch):
    default = tmp_path / "default.json"
    default.write_text(json.dumps({"json_ir": {"max_kb_llm_calls": 4}}), encoding="utf-8")
    monkeypatch.setattr("pipeline.config._DEFAULT_CONFIG_PATH", default)
    monkeypatch.setattr("pipeline.config._LOCAL_CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.delenv("JSON_IR_MAX_KB_LLM_CALLS", raising=False)
    reload_config()
    cfg = apply_env_overrides(load_config_files())
    assert cfg["json_ir"]["max_kb_llm_calls"] == 4
    reload_config()


def test_config_profile_overlay(tmp_path, monkeypatch):
    default = tmp_path / "default.json"
    default.write_text(
        json.dumps({"json_ir": {"max_kb_llm_calls": 8}, "extraction": {"max_retries": 6}}),
        encoding="utf-8",
    )
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"json_ir": {"max_kb_llm_calls": 3}}), encoding="utf-8")
    monkeypatch.setattr("pipeline.config._DEFAULT_CONFIG_PATH", default)
    monkeypatch.setattr("pipeline.config._LOCAL_CONFIG_PATH", tmp_path / "missing.json")
    monkeypatch.delenv(CONFIG_PROFILE_ENV, raising=False)
    reload_config()
    cfg = load_config_files(profile)
    assert cfg["json_ir"]["max_kb_llm_calls"] == 3
    assert cfg["extraction"]["max_retries"] == 6
    activate_config_profile(None)
    reload_config()


def test_effective_config_artifact_written(tmp_path, monkeypatch):
    monkeypatch.delenv("JSON_IR_MAX_KB_LLM_CALLS", raising=False)
    reload_config()
    out = tmp_path / "effective_config.json"
    cfg = save_effective_config(out)
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["json_ir"]["max_symbol_versions"] == cfg["json_ir"]["max_symbol_versions"]
    assert loaded.get("ignore_local_config") is False
    reload_config()
