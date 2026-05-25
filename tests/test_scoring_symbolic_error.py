"""Scoring must not treat symbolic failures as legal contradiction."""

from __future__ import annotations

import pytest

from pipeline.eval.boolean_belief import summarize_boolean_symbolic, symbolic_result_is_inconclusive
from pipeline.eval.scoring import score_question


@pytest.mark.parametrize(
    "status",
    ["error", "unsupported", "timeout", "malformed", "missing_result"],
)
def test_symbolic_error_status_is_inconclusive(status: str) -> None:
    sym = {"status": status, "certain": False, "possible": True}
    assert symbolic_result_is_inconclusive(sym) is True
    summ = summarize_boolean_symbolic(sym)
    assert summ["label"] == "unknown"
    scored = score_question({"mode": "boolean", "value": True}, sym)
    assert scored["epistemic_label"] == "unknown"
    assert scored["inconclusive"] is True
    assert scored["decisive"] is False
    assert scored["match"] is False


def test_missing_certain_and_possible_is_unknown_not_contradiction() -> None:
    sym = {"status": "ok"}
    assert symbolic_result_is_inconclusive(sym) is True
    scored = score_question({"mode": "boolean", "value": False}, sym)
    assert scored["epistemic_label"] == "unknown"
    assert scored["inconclusive"] is True
    assert scored["match"] is False
    assert scored.get("got") is None


def test_possible_without_certain_is_inconclusive_not_correct() -> None:
    sym = {"status": "ok", "certain": False, "possible": True}
    scored = score_question({"mode": "boolean", "value": True}, sym)
    assert scored["epistemic_label"] == "unknown"
    assert scored["inconclusive"] is True
    assert scored["match"] is False


def test_model_expansion_not_decisive_entailment() -> None:
    sym = {
        "intent": "model_expansion",
        "status": "ok",
        "certain": True,
        "possible": True,
    }
    scored = score_question({"mode": "boolean", "value": True}, sym)
    assert scored["inconclusive"] is True
    assert scored["decisive"] is False
    assert scored["match"] is False
