"""Evaluation failure classification helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.eval_support import classify_failure, is_eval_pipeline_failure  # noqa: E402


def test_scoring_missing_when_questions_but_no_score(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    (work / "results.json").write_text(
        json.dumps({"questions": [{"id": "q1", "expected": True}]}),
        encoding="utf-8",
    )
    cat = classify_failure(work, exit_code=0, ok=True)
    assert cat == "evaluation_no_score"
    assert is_eval_pipeline_failure(exit_code=0, failure_category=cat) is True


def test_completed_with_symbolic_errors_not_ok_category(tmp_path: Path) -> None:
    work = tmp_path / "work2"
    work.mkdir()
    (work / "results.json").write_text(json.dumps({"questions": []}), encoding="utf-8")
    (work / "score.json").write_text(
        json.dumps(
            {
                "total": 1,
                "correct": 0,
                "correct_decisive": 0,
                "incorrect_decisive": 0,
                "inconclusive": 1,
                "items": [
                    {
                        "match": False,
                        "epistemic_label": "unknown",
                        "symbolic_status": "error",
                        "inconclusive": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cat = classify_failure(work, exit_code=0, ok=True)
    assert cat == "completed_with_symbolic_errors"
    assert cat != "completed"
