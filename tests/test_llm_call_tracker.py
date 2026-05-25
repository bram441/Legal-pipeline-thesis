"""Tests for pipeline.utils.llm_call_tracker."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipeline.utils import llm_call_tracker as tracker


class _Usage:
    def __init__(self, prompt_tokens: int, completion_tokens: int):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


def _fake_response(content: str = "ok", *, prompt: int = 10, completion: int = 5):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=_Usage(prompt, completion),
    )


@pytest.fixture(autouse=True)
def _reset_tracker(tmp_path):
    tracker.clear_session_records()
    tracker.reset_eval_call_count()
    tracker.reset_cell_call_count()
    tracker.set_budget_limits(max_eval_calls=None, max_cell_calls=None, eval_calls_before=0)
    tracker.set_run_context(run_id="run_test", strategy="direct_json_ir_translate", artifact_dir=tmp_path)
    tracker.enable_eval_tracking(force=True)
    yield
    tracker.enable_eval_tracking(force=False)
    tracker.set_budget_limits(max_eval_calls=None, max_cell_calls=None, eval_calls_before=0)


def test_tracked_call_logs_usage_and_summary(tmp_path):
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_response("hello world")

    tracker.tracked_chat_completion_create(
        client,
        stage="translation",
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "translate this"}],
        metadata={"attempt": 1},
    )

    jsonl = tmp_path / "llm_calls.jsonl"
    assert jsonl.is_file()
    rec = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[0])
    assert rec["stage"] == "translation"
    assert rec["run_id"] == "run_test"
    assert rec["prompt_tokens"] == 10
    assert rec["completion_tokens"] == 5
    assert rec["input_char_count"] > 0

    summary = tracker.write_cell_summary(tmp_path)
    assert summary is not None
    assert summary["call_count"] == 1
    assert summary["by_stage"]["translation"] == 1
    assert summary["by_model"]["gpt-4.1-mini"] == 1


def test_eval_summary_groups_by_stage_and_model(tmp_path):
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _fake_response("a", prompt=8, completion=2),
        _fake_response("b", prompt=12, completion=3),
    ]

    tracker.tracked_chat_completion_create(
        client,
        stage="kb_symbols",
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "symbols"}],
    )
    tracker.tracked_chat_completion_create(
        client,
        stage="case_extraction",
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "case"}],
    )

    report = tmp_path / "report"
    summary = tracker.write_eval_summary(report)
    assert summary["call_count"] == 2
    assert summary["by_stage"]["kb_symbols"] == 1
    assert summary["by_stage"]["case_extraction"] == 1
    assert summary["by_model"]["gpt-4.1-mini"] == 1
    assert summary["by_model"]["gpt-4o-mini"] == 1
    assert summary["total_prompt_tokens"] == 20
    assert (report / "llm_call_summary.json").is_file()


def test_cell_budget_guard_writes_marker_and_raises(tmp_path):
    tracker.set_budget_limits(max_cell_calls=1)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_response()

    tracker.tracked_chat_completion_create(
        client,
        stage="kb_rules",
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "one"}],
    )

    with pytest.raises(tracker.LLMBudgetExceeded) as exc:
        tracker.tracked_chat_completion_create(
            client,
            stage="kb_rules",
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": "two"}],
        )
    assert exc.value.scope == "cell"
    guard = json.loads((tmp_path / "llm_budget_guard.json").read_text(encoding="utf-8"))
    assert guard["scope"] == "cell"


def test_eval_budget_with_offset(tmp_path):
    tracker.set_budget_limits(max_eval_calls=2, eval_calls_before=1)
    client = MagicMock()
    client.chat.completions.create.return_value = _fake_response()

    tracker.tracked_chat_completion_create(
        client,
        stage="translation",
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": "x"}],
    )

    with pytest.raises(tracker.LLMBudgetExceeded) as exc:
        tracker.tracked_chat_completion_create(
            client,
            stage="translation",
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": "y"}],
        )
    assert exc.value.scope == "eval"
    assert exc.value.count == 2


def test_eval_support_build_cell_detects_guard(tmp_path):
    from scripts import eval_support

    (tmp_path / "llm_budget_guard.json").write_text(
        json.dumps({"scope": "cell", "limit": 3, "count": 3}),
        encoding="utf-8",
    )
    cell = eval_support.build_eval_cell(
        tmp_path,
        1,
        path=str(tmp_path),
        duration_sec=1.0,
        strategy_metadata={},
    )
    assert cell["failure_category"] == "llm_budget_guard"
    assert cell["ok"] is False
