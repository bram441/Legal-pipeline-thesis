"""Tests for --ignore-local-config and configure_runtime."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from pipeline.config import (
    CONFIG_PROFILE_ENV,
    IGNORE_LOCAL_CONFIG_ENV,
    configure_runtime,
    get_effective_config,
    load_config_files,
    reload_config,
    save_effective_config,
)

_ROOT = Path(__file__).resolve().parents[1]
_ABLATION_SCRIPT = _ROOT / "scripts" / "run_config_ablation.py"


@pytest.fixture
def config_tree(tmp_path, monkeypatch):
    default = tmp_path / "default.json"
    default.write_text(
        json.dumps({"json_ir": {"max_kb_llm_calls": 8}, "extraction": {"max_retries": 6}}),
        encoding="utf-8",
    )
    local = tmp_path / "local.json"
    local.write_text(json.dumps({"json_ir": {"max_kb_llm_calls": 99}}), encoding="utf-8")
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"json_ir": {"max_kb_llm_calls": 3}}), encoding="utf-8")
    monkeypatch.setattr("pipeline.config._DEFAULT_CONFIG_PATH", default)
    monkeypatch.setattr("pipeline.config._LOCAL_CONFIG_PATH", local)
    monkeypatch.delenv(CONFIG_PROFILE_ENV, raising=False)
    monkeypatch.delenv(IGNORE_LOCAL_CONFIG_ENV, raising=False)
    reload_config()
    yield tmp_path, profile
    configure_runtime(None, ignore_local_config=False)
    reload_config()


def test_local_json_affects_config_without_ignore(config_tree):
  _tmp, _profile = config_tree
  reload_config()
  cfg = get_effective_config()
  assert cfg["json_ir"]["max_kb_llm_calls"] == 99


def test_local_json_ignored_with_ignore_local_config(config_tree):
    _tmp, _profile = config_tree
    configure_runtime(None, ignore_local_config=True)
    cfg = get_effective_config()
    assert cfg["json_ir"]["max_kb_llm_calls"] == 8


def test_config_profile_applies_when_local_ignored(config_tree):
    _tmp, profile = config_tree
    configure_runtime(profile, ignore_local_config=True)
    cfg = get_effective_config()
    assert cfg["json_ir"]["max_kb_llm_calls"] == 3


def test_env_vars_still_override_profile(config_tree, monkeypatch):
    _tmp, profile = config_tree
    configure_runtime(profile, ignore_local_config=True)
    monkeypatch.setenv("JSON_IR_MAX_KB_LLM_CALLS", "42")
    reload_config()
    cfg = get_effective_config()
    assert cfg["json_ir"]["max_kb_llm_calls"] == 42


def test_save_effective_config_records_ignore_local_config(config_tree, tmp_path):
    _tmp, profile = config_tree
    configure_runtime(profile, ignore_local_config=True)
    out = tmp_path / "effective_config.json"
    artifact = save_effective_config(out)
    assert artifact["ignore_local_config"] is True
    assert artifact["config_profile"] == str(profile.resolve())
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["ignore_local_config"] is True


def test_run_config_ablation_includes_ignore_local_config():
    proc = subprocess.run(
        [
            sys.executable,
            str(_ABLATION_SCRIPT),
            "--profiles",
            "config/balanced.json",
            "--runs",
            "run_001",
            "--dry-run",
        ],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--ignore-local-config" in proc.stdout
