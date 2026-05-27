"""Tests for scripts/run_model_sweep.py (no live API calls)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SWEEP_PATH = _ROOT / "scripts" / "run_model_sweep.py"


def _load_sweep():
    spec = importlib.util.spec_from_file_location("run_model_sweep", _SWEEP_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_load_models_from_text_file(tmp_path):
    sweep = _load_sweep()
    path = tmp_path / "models.txt"
    path.write_text(
        "# header comment\n"
        "openai/gpt-5.4-mini\n"
        "\n"
        "anthropic/claude-sonnet-4.5  # inline comment\n",
        encoding="utf-8",
    )
    assert sweep.load_models_from_file(path) == [
        "openai/gpt-5.4-mini",
        "anthropic/claude-sonnet-4.5",
    ]


def test_resolve_models_merges_file_and_cli(tmp_path):
    sweep = _load_sweep()
    path = tmp_path / "models.txt"
    path.write_text("openai/gpt-5.4-mini\n", encoding="utf-8")
    got = sweep.resolve_models(["openai/gpt-5.5"], str(path))
    assert got == ["openai/gpt-5.4-mini", "openai/gpt-5.5"]


@pytest.mark.parametrize(
    "model,expected",
    [
        ("openai/gpt-5.5", "openai_gpt-5.5"),
        ("anthropic/claude-sonnet-4.5", "anthropic_claude-sonnet-4.5"),
        ("google/gemini-2.5-pro", "google_gemini-2.5-pro"),
    ],
)
def test_sanitize_model_name(model, expected):
    sweep = _load_sweep()
    assert sweep.sanitize_model_name(model) == expected


def test_aggregate_matrix_from_fake_file(tmp_path):
    sweep = _load_sweep()
    matrix = {
        "runs": ["run_001"],
        "strategies": ["direct_json_ir_no_translate"],
        "cells": {
            "run_001": {
                "direct_json_ir_no_translate": {
                    "scored": True,
                    "correct_decisive": 2,
                    "incorrect_decisive": 1,
                    "inconclusive": 0,
                    "failure_category": "completed",
                }
            }
        },
        "llm_call_summary": {
            "call_count": 5,
            "total_prompt_tokens": 100,
            "total_completion_tokens": 50,
            "total_tokens": 150,
            "estimated_total_cost_usd": 0.12,
        },
        "evaluation_cli": {"model": "openai/gpt-5.5", "provider": "openrouter"},
    }
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(json.dumps(matrix), encoding="utf-8")
    row = sweep._aggregate_matrix(
        matrix_path,
        model="openai/gpt-5.5",
        provider="openrouter",
        output_dir=tmp_path,
        exit_code=0,
        duration_sec=12.5,
    )
    assert row["total_cells"] == 1
    assert row["scored_cells"] == 1
    assert row["correct_decisive"] == 2
    assert row["wrong_decisive"] == 1
    assert row["strict_accuracy"] == 2.0
    assert row["coverage"] == 1.0
    assert row["decisive_precision"] == pytest.approx(2 / 3)
    assert row["total_llm_calls"] == 5
    assert row["estimated_cost_usd"] == 0.12


def test_subprocess_command_includes_config_and_ignore_local(tmp_path):
    sweep = _load_sweep()
    calls: list[list[str]] = []

    def fake_call(cmd, env=None, cwd=None):
        calls.append(list(cmd))
        out = Path(cmd[cmd.index("--output-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "matrix.json").write_text(
            json.dumps(
                {
                    "runs": [],
                    "strategies": [],
                    "cells": {},
                    "llm_call_summary": {"call_count": 0},
                }
            ),
            encoding="utf-8",
        )
        return 0

    models_file = tmp_path / "models.txt"
    models_file.write_text("openai/gpt-5.4-mini\nopenai/gpt-5.5\n", encoding="utf-8")
    argv = [
        "run_model_sweep.py",
        "--models-file",
        str(models_file),
        "--input-dir",
        "inputs/json_final_clean",
        "--strategies",
        "direct_json_ir_no_translate",
        "le_json_ir_no_translate",
        "--config",
        "config/ablation_balanced.json",
        "--ignore-local-config",
        "--output-root",
        str(tmp_path / "sweep_out"),
        "--provider",
        "openrouter",
    ]
    with patch.object(subprocess, "call", side_effect=fake_call):
        with patch.object(sys, "argv", argv):
            rc = sweep.main()
    assert rc == 0
    assert len(calls) == 2
    for cmd in calls:
        assert "--config" in cmd
        assert "--ignore-local-config" in cmd
        assert "--input-dir" in cmd
        idx = cmd.index("--input-dir")
        assert cmd[idx + 1] == "inputs/json_final_clean"


def test_sweep_continues_after_model_failure(tmp_path):
    sweep = _load_sweep()
    outcomes = [1, 0]

    def fake_call(cmd, env=None, cwd=None):
        rc = outcomes.pop(0)
        out = Path(cmd[cmd.index("--output-dir") + 1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "matrix.json").write_text(
            json.dumps({"runs": [], "strategies": [], "cells": {}}),
            encoding="utf-8",
        )
        return rc

    argv = [
        "run_model_sweep.py",
        "--models",
        "model_a",
        "model_b",
        "--input-dir",
        "inputs/json",
        "--strategies",
        "direct_json_ir_no_translate",
        "--config",
        "config/ablation_balanced.json",
        "--output-root",
        str(tmp_path / "sweep_fail"),
    ]
    with patch.object(subprocess, "call", side_effect=fake_call):
        with patch.object(sys, "argv", argv):
            rc = sweep.main()
    assert rc == 1
    summary = json.loads((tmp_path / "sweep_fail" / "model_sweep_summary.json").read_text(encoding="utf-8"))
    assert len(summary["rows"]) == 2
    assert summary["rows"][0]["exit_code"] == 1
    assert summary["rows"][1]["exit_code"] == 0
