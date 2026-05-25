"""Evaluation harness: score presence vs exit code (reporting contract)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.eval_support import (  # noqa: E402
    build_eval_cell,
    classify_exit_zero_outcome,
    classify_failure,
)


def test_exit_zero_valid_score_completed(tmp_path: Path) -> None:
    work = tmp_path / "ok"
    work.mkdir()
    (work / "run.json").write_text(
        json.dumps({"questions": [{"id": "q1", "expected": True}]}),
        encoding="utf-8",
    )
    (work / "results.json").write_text(
        json.dumps({"questions": [{"id": "q1", "pipeline": {}}]}),
        encoding="utf-8",
    )
    (work / "score.json").write_text(
        json.dumps(
            {
                "id": "run_x",
                "total": 1,
                "correct": 1,
                "correct_decisive": 1,
                "incorrect_decisive": 0,
                "inconclusive": 0,
                "accuracy_decisive": 1.0,
                "items": [{"match": True, "symbolic_status": "ok"}],
            }
        ),
        encoding="utf-8",
    )
    cell = build_eval_cell(work, 0, path=str(work), duration_sec=1.0, strategy_metadata={})
    assert cell["scored"] is True
    assert cell["score_present"] is True
    assert cell["ok"] is True
    assert cell["failure_category"] == "completed"
    assert cell["total"] == 1


def test_exit_zero_missing_score_evaluation_no_score(tmp_path: Path) -> None:
    work = tmp_path / "no_score"
    work.mkdir()
    (work / "run.json").write_text(
        json.dumps({"questions": [{"id": "q1", "expected": True}]}),
        encoding="utf-8",
    )
    outcome = classify_exit_zero_outcome(work)
    assert outcome["failure_category"] == "evaluation_no_score"
    assert outcome["scored"] is False
    assert outcome["score_present"] is False
    cell = build_eval_cell(work, 0, path=str(work), duration_sec=2.8, strategy_metadata={})
    assert cell["ok"] is False
    assert cell["failure_category"] == "evaluation_no_score"
    assert cell["missing_score_reason"] in {
        "score_file_missing",
        "main_exited_before_scoring",
        "no_questions_found",
    }


def test_exit_zero_malformed_score_bad(tmp_path: Path) -> None:
    work = tmp_path / "bad"
    work.mkdir()
    (work / "score.json").write_text("{not json", encoding="utf-8")
    outcome = classify_exit_zero_outcome(work)
    assert outcome["failure_category"] == "evaluation_bad_score"
    cell = build_eval_cell(work, 0, path=str(work), duration_sec=1.0, strategy_metadata={})
    assert cell["ok"] is False
    assert cell["failure_category"] == "evaluation_bad_score"


def test_nonzero_exit_law_compilation(tmp_path: Path) -> None:
    work = tmp_path / "compile"
    work.mkdir()
    (work / "run_trace.txt").write_text("Law compilation failed: repair stalled", encoding="utf-8")
    cat = classify_failure(work, 1, ok=False)
    assert cat == "law_compilation"
    cell = build_eval_cell(work, 1, path=str(work), duration_sec=5.0, strategy_metadata={})
    assert cell["ok"] is False
    assert cell["failure_category"] == "law_compilation"
    assert cell["scored"] is False


def test_scoring_missing_legacy_path(tmp_path: Path) -> None:
    work = tmp_path / "legacy"
    work.mkdir()
    (work / "results.json").write_text(
        json.dumps({"questions": [{"id": "q1", "expected": True}]}),
        encoding="utf-8",
    )
    cat = classify_failure(work, 0, ok=True)
    assert cat == "evaluation_no_score"
