"""
Lightweight accounting for OpenAI chat.completions.create calls.

Writes per-run llm_calls.jsonl + llm_call_summary.json when an artifact directory
is set. Evaluation runs can aggregate into the report output directory.
"""

from __future__ import annotations

import json
import os
import threading
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_session_records: list[dict[str, Any]] = []

_ctx_run_id: ContextVar[str | None] = ContextVar("llm_run_id", default=None)
_ctx_strategy: ContextVar[str | None] = ContextVar("llm_strategy", default=None)
_ctx_artifact_dir: ContextVar[str | None] = ContextVar("llm_artifact_dir", default=None)
_ctx_eval_report_dir: ContextVar[str | None] = ContextVar("llm_eval_report_dir", default=None)

_eval_mode_forced = False
_max_eval_calls: int | None = None
_max_cell_calls: int | None = None
_eval_calls_before: int = 0
_eval_call_count = 0
_cell_call_count = 0
_cell_record_start = 0

VALID_STAGES = frozenset(
    {
        "translation",
        "le",
        "kb_symbols",
        "kb_rules",
        "case_extraction",
        "query_extraction",
        "legacy_kb",
        "nl_explanation",
        "unknown",
    }
)

# USD per 1M tokens (input, output) — approximate; override via config debug.llm_pricing_usd
_DEFAULT_PRICING_USD_PER_1M: dict[str, dict[str, float]] = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
}


class LLMBudgetExceeded(Exception):
    """Raised when eval or per-cell LLM call budget is exceeded."""

    def __init__(self, message: str, *, scope: str, limit: int, count: int):
        super().__init__(message)
        self.scope = scope
        self.limit = limit
        self.count = count


def tracking_enabled() -> bool:
    if _eval_mode_forced:
        return True
    from pipeline.config import config_section

    return bool(config_section("debug").get("llm_call_tracking"))


def enable_eval_tracking(*, force: bool = True) -> None:
    """Enable tracking for evaluation runs regardless of config default."""
    global _eval_mode_forced
    _eval_mode_forced = force


def set_budget_limits(
    *,
    max_eval_calls: int | None = None,
    max_cell_calls: int | None = None,
    eval_calls_before: int | None = None,
) -> None:
    global _max_eval_calls, _max_cell_calls, _eval_calls_before
    _max_eval_calls = max_eval_calls
    _max_cell_calls = max_cell_calls
    if eval_calls_before is not None:
        _eval_calls_before = max(0, int(eval_calls_before))


def apply_budget_from_env() -> None:
    """Load eval/cell budgets and prior call count from subprocess environment."""
    global _max_eval_calls, _max_cell_calls, _eval_calls_before
    if os.environ.get("PIPELINE_LLM_CALL_TRACKING", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        enable_eval_tracking(force=True)
    raw_eval = os.environ.get("PIPELINE_LLM_MAX_EVAL_CALLS", "").strip()
    if raw_eval.isdigit():
        _max_eval_calls = int(raw_eval)
    raw_cell = os.environ.get("PIPELINE_LLM_MAX_CELL_CALLS", "").strip()
    if raw_cell.isdigit():
        _max_cell_calls = int(raw_cell)
    before = os.environ.get("PIPELINE_LLM_EVAL_CALLS_BEFORE", "").strip()
    if before.isdigit():
        _eval_calls_before = int(before)


def set_run_context(
    *,
    run_id: str | None = None,
    strategy: str | None = None,
    artifact_dir: str | Path | None = None,
) -> None:
    if run_id is not None:
        _ctx_run_id.set(run_id)
    if strategy is not None:
        _ctx_strategy.set(strategy)
    if artifact_dir is not None:
        _ctx_artifact_dir.set(str(Path(artifact_dir).resolve()))


def set_eval_report_dir(path: str | Path | None) -> None:
    _ctx_eval_report_dir.set(str(Path(path).resolve()) if path else None)


def reset_eval_call_count() -> None:
    global _eval_call_count
    with _lock:
        _eval_call_count = 0


def reset_cell_call_count() -> None:
    global _cell_call_count, _cell_record_start
    with _lock:
        _cell_call_count = 0
        _cell_record_start = len(_session_records)


def get_eval_call_count() -> int:
    with _lock:
        return _eval_call_count


def get_cell_call_count() -> int:
    with _lock:
        return _cell_call_count


def clear_session_records() -> None:
    with _lock:
        _session_records.clear()


def session_records() -> list[dict[str, Any]]:
    with _lock:
        return list(_session_records)


def _approx_tokens_from_chars(n: int) -> int:
    return max(0, int(n) // 4)


def _messages_char_count(messages: Any) -> int:
    total = 0
    if not messages:
        return 0
    for m in messages:
        if isinstance(m, dict):
            total += len(str(m.get("content") or ""))
        else:
            total += len(str(m))
    return total


def _output_char_count(resp: Any) -> int:
    try:
        return len(str(resp.choices[0].message.content or ""))
    except (AttributeError, IndexError, TypeError):
        return 0


def _usage_fields(resp: Any) -> dict[str, int | None]:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def _pricing_table() -> dict[str, dict[str, float]]:
    from pipeline.config import config_section

    custom = config_section("debug").get("llm_pricing_usd_per_1m")
    if isinstance(custom, dict) and custom:
        return {str(k): dict(v) for k, v in custom.items() if isinstance(v, dict)}
    return dict(_DEFAULT_PRICING_USD_PER_1M)


def _estimate_cost_usd(model: str, usage: dict[str, int | None]) -> float | None:
    pt = usage.get("prompt_tokens")
    ct = usage.get("completion_tokens")
    if pt is None and ct is None:
        return None
    table = _pricing_table()
    rates = None
    for key, val in table.items():
        if key in (model or ""):
            rates = val
            break
    if not rates:
        return None
    cost = 0.0
    if pt is not None:
        cost += (pt / 1_000_000.0) * float(rates.get("input", 0))
    if ct is not None:
        cost += (ct / 1_000_000.0) * float(rates.get("output", 0))
    return round(cost, 6)


def _write_budget_guard(*, scope: str, limit: int, count: int) -> None:
    payload = {
        "scope": scope,
        "limit": limit,
        "count": count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    artifact = _ctx_artifact_dir.get()
    if artifact:
        path = Path(artifact) / "llm_budget_guard.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_budget_before_call() -> None:
    global _eval_call_count, _cell_call_count
    with _lock:
        effective_eval = _eval_calls_before + _eval_call_count
        if _max_cell_calls is not None and _cell_call_count >= _max_cell_calls:
            _write_budget_guard(scope="cell", limit=_max_cell_calls, count=_cell_call_count)
            raise LLMBudgetExceeded(
                "Per-cell LLM call budget exceeded (%s >= %s)"
                % (_cell_call_count, _max_cell_calls),
                scope="cell",
                limit=_max_cell_calls,
                count=_cell_call_count,
            )
        if _max_eval_calls is not None and effective_eval >= _max_eval_calls:
            _write_budget_guard(scope="eval", limit=_max_eval_calls, count=effective_eval)
            raise LLMBudgetExceeded(
                "Evaluation LLM call budget exceeded (%s >= %s)"
                % (effective_eval, _max_eval_calls),
                scope="eval",
                limit=_max_eval_calls,
                count=effective_eval,
            )


def _increment_budget_counters() -> int:
    global _eval_call_count, _cell_call_count
    with _lock:
        _cell_call_count += 1
        _eval_call_count += 1
        return _eval_call_count


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _record_call(
    *,
    stage: str,
    model: str,
    messages: Any,
    resp: Any,
    metadata: dict[str, Any] | None,
    call_index: int,
) -> dict[str, Any]:
    stage_norm = stage if stage in VALID_STAGES else "unknown"
    in_chars = _messages_char_count(messages)
    out_chars = _output_char_count(resp)
    usage = _usage_fields(resp)
    est_usd = _estimate_cost_usd(model, usage)
    rec = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "call_index": call_index,
        "stage": stage_norm,
        "run_id": _ctx_run_id.get(),
        "strategy": _ctx_strategy.get(),
        "model": model,
        "metadata": metadata or {},
        "input_char_count": in_chars,
        "approx_input_tokens": _approx_tokens_from_chars(in_chars),
        "output_char_count": out_chars,
        "approx_output_tokens": _approx_tokens_from_chars(out_chars),
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "estimated_cost_usd": est_usd,
        "estimated_cost_eur": round(est_usd * 0.92, 6) if est_usd is not None else None,
    }
    with _lock:
        _session_records.append(rec)
    artifact = _ctx_artifact_dir.get()
    if artifact:
        _append_jsonl(Path(artifact) / "llm_calls.jsonl", rec)
    return rec


def tracked_chat_completion_create(
    client: Any,
    *,
    stage: str = "unknown",
    model: str | None = None,
    messages: Any = None,
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """
    Drop-in wrapper around client.chat.completions.create with accounting.
    """
    apply_budget_from_env()
    if not tracking_enabled():
        return client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )

    _check_budget_before_call()
    call_index = _increment_budget_counters()
    chosen_model = model or kwargs.get("model") or "unknown"

    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        **kwargs,
    )
    _record_call(
        stage=stage,
        model=str(chosen_model),
        messages=messages,
        resp=resp,
        metadata=metadata,
        call_index=call_index,
    )
    return resp


def _summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_stage: dict[str, int] = {}
    by_model: dict[str, int] = {}
    by_run: dict[str, int] = {}
    by_strategy: dict[str, int] = {}
    total_prompt = 0
    total_completion = 0
    total_tokens = 0
    cost_usd = 0.0
    cost_known = False

    for r in records:
        st = r.get("stage") or "unknown"
        by_stage[st] = by_stage.get(st, 0) + 1
        m = r.get("model") or "unknown"
        by_model[m] = by_model.get(m, 0) + 1
        rid = r.get("run_id") or "(none)"
        by_run[rid] = by_run.get(rid, 0) + 1
        strat = r.get("strategy") or "(none)"
        by_strategy[strat] = by_strategy.get(strat, 0) + 1
        pt = r.get("prompt_tokens")
        ct = r.get("completion_tokens")
        tt = r.get("total_tokens")
        if isinstance(pt, int):
            total_prompt += pt
        if isinstance(ct, int):
            total_completion += ct
        if isinstance(tt, int):
            total_tokens += tt
        c = r.get("estimated_cost_usd")
        if isinstance(c, (int, float)):
            cost_usd += float(c)
            cost_known = True

    top_by_tokens = sorted(
        records,
        key=lambda r: int(r.get("total_tokens") or 0),
        reverse=True,
    )[:10]

    return {
        "call_count": len(records),
        "by_stage": dict(sorted(by_stage.items())),
        "by_model": dict(sorted(by_model.items())),
        "by_run_id": dict(sorted(by_run.items())),
        "by_strategy": dict(sorted(by_strategy.items())),
        "total_prompt_tokens": total_prompt if total_prompt else None,
        "total_completion_tokens": total_completion if total_completion else None,
        "total_tokens": total_tokens if total_tokens else None,
        "estimated_total_cost_usd": round(cost_usd, 4) if cost_known else None,
        "top_calls_by_total_tokens": [
            {
                "call_index": r.get("call_index"),
                "stage": r.get("stage"),
                "run_id": r.get("run_id"),
                "strategy": r.get("strategy"),
                "model": r.get("model"),
                "total_tokens": r.get("total_tokens"),
                "prompt_tokens": r.get("prompt_tokens"),
                "completion_tokens": r.get("completion_tokens"),
                "metadata": r.get("metadata"),
            }
            for r in top_by_tokens
        ],
    }


def write_cell_summary(artifact_dir: str | Path | None = None) -> dict[str, Any] | None:
    """Summarize calls for the current cell (session records since last cell reset)."""
    if not tracking_enabled():
        return None
    with _lock:
        records = list(_session_records[_cell_record_start:])
    summary = _summarize_records(records)
    summary["cell_call_count"] = get_cell_call_count()
    path_dir = artifact_dir or _ctx_artifact_dir.get()
    if path_dir:
        out = Path(path_dir) / "llm_call_summary.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def write_eval_summary(
    report_dir: str | Path,
    *,
    work_root: str | Path | None = None,
) -> dict[str, Any]:
    """
    Write evaluation-level llm_call_summary.json (and optional per-work-dir aggregation).
    """
    report = Path(report_dir)
    report.mkdir(parents=True, exist_ok=True)

    records = session_records()
    if work_root:
        wr = Path(work_root)
        if wr.is_dir():
            for jsonl in sorted(wr.rglob("llm_calls.jsonl")):
                try:
                    for line in jsonl.read_text(encoding="utf-8").splitlines():
                        line = line.strip()
                        if line:
                            records.append(json.loads(line))
                except (OSError, json.JSONDecodeError):
                    continue

    summary = _summarize_records(records)
    summary["eval_call_count"] = get_eval_call_count()
    summary["budget_limits"] = {
        "max_eval_calls": _max_eval_calls,
        "max_cell_calls": _max_cell_calls,
        "eval_calls_before": _eval_calls_before,
    }
    out = report / "llm_call_summary.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    by_run_strategy: dict[str, dict[str, Any]] = {}
    for r in records:
        key = "%s::%s" % (r.get("run_id") or "?", r.get("strategy") or "?")
        bucket = by_run_strategy.setdefault(
            key,
            {"run_id": r.get("run_id"), "strategy": r.get("strategy"), "calls": 0, "total_tokens": 0},
        )
        bucket["calls"] += 1
        tt = r.get("total_tokens")
        if isinstance(tt, int):
            bucket["total_tokens"] += tt
    summary["by_run_and_strategy"] = by_run_strategy

    (report / "llm_eval_call_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
