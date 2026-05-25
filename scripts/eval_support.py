"""
Shared helpers for KB strategy evaluation (used by run_evaluation.py).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.kb.compile_strategy import (  # noqa: E402
    CANONICAL_JSON_IR_STRATEGIES,
    STRATEGY_CHOICES,
    default_strategies_for_pipeline,
    get_strategy_spec,
    resolve_translate,
    strategy_metadata,
)


def copy_run_json(src_run_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_run_dir / "run.json", dest_dir / "run.json")


def run_main_json(
    run_dir: Path,
    strategy: str,
    *,
    translate_override: bool | None = None,
    cli_no_translate: bool = False,
    belief_scoring: bool = False,
    llm_call_tracking: bool = False,
    max_llm_calls: int | None = None,
    max_llm_calls_per_cell: int | None = None,
    llm_eval_calls_before: int = 0,
) -> int:
    """Invoke ``main.py --mode json`` (JSON-IR pipeline only).

    Translation: strategy config wins unless ``translate_override`` is set (explicit per-cell
    override) or ``cli_no_translate`` forces skip (global eval ``--no-translate``).
    """
    get_strategy_spec(strategy)
    if translate_override is not None:
        use_translate = translate_override
    else:
        use_translate = resolve_translate(strategy, cli_no_translate=cli_no_translate)

    cmd = [
        sys.executable,
        str(_ROOT / "main.py"),
        "--mode",
        "json",
        "--run",
        str(run_dir),
        "--kb-strategy",
        strategy,
    ]
    if not use_translate:
        cmd.append("--no-translate")
    env = os.environ.copy()
    if belief_scoring:
        env["SCORE_TREAT_OPEN_WITH_BELIEF"] = "1"
        env.setdefault("SCORE_BOOLEAN_BELIEF_THRESHOLD", "0.5")
    else:
        env["SCORE_TREAT_OPEN_WITH_BELIEF"] = "0"
        env.pop("SCORE_BOOLEAN_BELIEF_THRESHOLD", None)
    if llm_call_tracking:
        env["PIPELINE_LLM_CALL_TRACKING"] = "1"
    if max_llm_calls is not None:
        env["PIPELINE_LLM_MAX_EVAL_CALLS"] = str(max_llm_calls)
    if max_llm_calls_per_cell is not None:
        env["PIPELINE_LLM_MAX_CELL_CALLS"] = str(max_llm_calls_per_cell)
    if llm_eval_calls_before > 0:
        env["PIPELINE_LLM_EVAL_CALLS_BEFORE"] = str(llm_eval_calls_before)
    return subprocess.call(cmd, cwd=str(_ROOT), env=env)


def read_llm_budget_guard(work_dir: Path) -> dict | None:
    path = work_dir / "llm_budget_guard.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def read_cell_llm_call_count(work_dir: Path) -> int:
    summary_path = work_dir / "llm_call_summary.json"
    if summary_path.is_file():
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                cc = data.get("cell_call_count")
                if isinstance(cc, int):
                    return cc
                return int(data.get("call_count") or 0)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    jsonl = work_dir / "llm_calls.jsonl"
    if not jsonl.is_file():
        return 0
    try:
        return sum(1 for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def count_eval_llm_calls(work_root: Path) -> int:
    total = 0
    if not work_root.is_dir():
        return 0
    for jsonl in work_root.rglob("llm_calls.jsonl"):
        try:
            total += sum(
                1 for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()
            )
        except OSError:
            continue
    return total


def read_score(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _classify_score_warning(message: str) -> str:
    w = (message or "").strip()
    wl = w.lower()
    if w.startswith("Expected legal Boolean answer was evaluated using observable predicate"):
        return "observable_query_target"
    if w.startswith("Antecedent diagnostics:"):
        return "antecedent_diagnostic"
    if "observable antecedent required by the kb rule" in wl:
        return "antecedent_diagnostic"
    return "other"


def summarize_score_diagnostics(score: dict | None) -> dict[str, Any]:
    """First-item + run-level fields for matrix reporting."""
    if not score:
        return {}
    item = None
    for it in score.get("items") or []:
        if isinstance(it, dict):
            item = it
            break
    out: dict[str, Any] = {
        "pragmatic_factual_criteria_mode": score.get("pragmatic_factual_criteria_mode"),
        "scoring_mode": score.get("scoring_mode"),
    }
    if item:
        out.update(
            {
                "selected_intent": item.get("selected_intent"),
                "detected_question_type": item.get("detected_question_type"),
                "satisfiability_status": item.get("satisfiability_status"),
                "symbolic_status": item.get("symbolic_status"),
                "factual_criteria_used": item.get("factual_criteria_used"),
            }
        )
    return out


def summarize_query_targets(score: dict | None) -> dict:
    """Per-question query predicate/kind and classified score warnings."""
    if not score:
        return {
            "items": [],
            "observable_query_target_warning_count": 0,
            "antecedent_diagnostic_warning_count": 0,
        }
    items_out = []
    oqt_count = 0
    ant_count = 0
    for it in score.get("items") or []:
        pred = it.get("query_predicate")
        kind = it.get("query_predicate_kind")
        warns = it.get("warnings") or []
        if not pred and not kind and not warns:
            continue
        for w in warns:
            kind_w = _classify_score_warning(str(w))
            if kind_w == "observable_query_target":
                oqt_count += 1
            elif kind_w == "antecedent_diagnostic":
                ant_count += 1
        items_out.append(
            {
                "id": it.get("id"),
                "predicate": pred,
                "predicate_kind": kind,
                "warnings": warns,
            }
        )
    return {
        "items": items_out,
        "observable_query_target_warning_count": oqt_count,
        "antecedent_diagnostic_warning_count": ant_count,
    }


def discover_json_runs(runs_dir: Path) -> list[Path]:
    """Subdirectories of runs_dir that contain run.json, sorted by name."""
    if not runs_dir.is_dir():
        return []
    out = []
    for p in sorted(runs_dir.iterdir()):
        if p.is_dir() and (p / "run.json").is_file():
            out.append(p.resolve())
    return out


def parse_runs_selection(runs_dir: Path, spec: str) -> list[Path]:
    """
    spec: 'all' or comma-separated folder names (e.g. run_001,run_003).
    Paths are resolved under runs_dir.
    """
    spec = (spec or "all").strip()
    if spec.lower() == "all":
        return discover_json_runs(runs_dir)
    names = [x.strip() for x in spec.split(",") if x.strip()]
    out = []
    for name in names:
        p = runs_dir / name
        if not (p / "run.json").is_file():
            raise FileNotFoundError("No run.json in " + str(p.resolve()))
        out.append(p.resolve())
    return out


def parse_strategies_selection(spec: str) -> list[str]:
    spec = (spec or "all").strip()
    if spec.lower() == "all":
        return default_strategies_for_pipeline()
    names = [x.strip() for x in spec.split(",") if x.strip()]
    for n in names:
        if n not in STRATEGY_CHOICES:
            raise ValueError(
                "Unknown strategy %r. Expected one of: %s" % (n, ", ".join(STRATEGY_CHOICES))
            )
    return names


def strategy_metadata_for_eval(
    strategy: str,
    *,
    belief_scoring: bool,
    translate_override: bool | None = None,
    cli_no_translate: bool = False,
) -> dict:
    """Matrix/report metadata; reflects effective translation after overrides."""
    return strategy_metadata(
        strategy,
        belief_scoring=belief_scoring,
        cli_no_translate=cli_no_translate,
        translate_override=translate_override,
        translation_source_prefix="eval_",
    )


def work_dir_name(run_folder: Path, strategy: str) -> str:
    """Filesystem-safe unique name, e.g. ``run_003__direct_json_ir_no_translate``."""
    return run_folder.name + "__" + strategy


def _gather_eval_diag_text(work_dir: Path) -> str:
    """Concatenate run trace and KB compile logs for heuristic failure classification."""
    parts: list[str] = []
    trace = work_dir / "run_trace.txt"
    if trace.is_file():
        try:
            parts.append(trace.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    try:
        for log in sorted(work_dir.rglob("kb_compile.log")):
            try:
                parts.append(log.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    except OSError:
        pass
    return "\n".join(parts)


# Categories that indicate the pipeline did not complete cleanly (not merely wrong answers).
EVAL_PIPELINE_FAILURE_CATEGORIES = frozenset(
    {
        "completed_with_errors",
        "completed_with_symbolic_errors",
        "scoring_missing",
        "evaluation_no_score",
        "evaluation_bad_score",
        "completed_no_score",
        "process_error",
        "translation",
        "case_extraction",
        "kb_repair_exhausted",
        "law_compilation",
        "kb_lint",
        "kb_idp_parse",
        "kb_semantic",
        "reasoning_symbol_mismatch",
        "case_query_validation",
        "kb_compile_validation",
        "llm_budget_guard",
        "inconsistent_kb_case",
        "intent_execution_error",
        "unsupported_intent",
        "unscored_intent",
        "unknown",
    }
)

# Cells with a valid score.json and score.total present (accuracy may still be 0/0).
EVAL_SCORED_CATEGORIES = frozenset(
    {
        "completed",
        "completed_with_symbolic_errors",
    }
)


def score_has_symbolic_errors(score: dict | None) -> bool:
    if not score:
        return False
    for it in score.get("items") or []:
        if (it or {}).get("symbolic_status") == "error":
            return True
    return False


def is_eval_pipeline_failure(
    *,
    exit_code: int,
    failure_category: str | None,
    score: dict | None = None,
) -> bool:
    """True when a matrix cell failed for infra/compile/symbolic reasons (not wrong entailment)."""
    if exit_code != 0:
        return True
    cat = (failure_category or "").strip()
    if cat in EVAL_PIPELINE_FAILURE_CATEGORIES:
        return True
    if cat == "completed_no_score":
        return True
    if not (score and score.get("total") is not None):
        if exit_code == 0 and cat not in EVAL_SCORED_CATEGORIES:
            return True
    if score_has_symbolic_errors(score):
        return True
    return False


def _load_run_json(work_dir: Path) -> dict | None:
    path = work_dir / "run.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _load_results_json(work_dir: Path) -> dict | None:
    path = work_dir / "results.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def diagnose_missing_score_reason(work_dir: Path) -> str:
    """
    Heuristic reason when exit_code=0 but score.json is absent or unusable.
    """
    work_dir = work_dir.resolve()
    run_obj = _load_run_json(work_dir) or {}
    questions = run_obj.get("questions") or []
    if not questions:
        return "no_questions_found"

    results = _load_results_json(work_dir)
    if results is not None:
        res_q = results.get("questions") or []
        if res_q and not (work_dir / "score.json").is_file():
            return "scoring_skipped"
        for q in res_q:
            pipe = (q or {}).get("pipeline") or {}
            if pipe.get("error_stage") or pipe.get("error"):
                return "question_pipeline_error_before_score"

    blob_l = _gather_eval_diag_text(work_dir).lower()
    if "translation failed" in blob_l:
        return "translation_failed"
    if "case extraction failed" in blob_l:
        return "case_extraction_failed"
    if "law file not found" in blob_l:
        return "law_file_not_found"
    if "wrote:" in blob_l and "score.json" in blob_l:
        return "score_file_missing_after_reported_write"
    if "loading from cache" in blob_l and "case" not in blob_l:
        return "main_exited_before_scoring"
    if "json ir compilation failed" in blob_l or "law compilation failed" in blob_l:
        return "law_compilation_failed"
    if (work_dir / "kb_compile.log").is_file() or list(work_dir.rglob("kb_compile.log")):
        if not results:
            return "main_exited_before_scoring"
    if results is None:
        return "main_exited_before_scoring"
    return "unknown"


def assess_score_file(score_path: Path) -> tuple[dict | None, bool, str | None]:
    """
    Return (score_dict, score_present, missing_reason).

    score_present requires valid JSON and a non-null ``total`` field.
    """
    if not score_path.is_file():
        return None, False, "score_file_missing"
    try:
        raw = json.loads(score_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None, False, "score_malformed_json"
    if not isinstance(raw, dict):
        return None, False, "score_malformed_json"
    if raw.get("total") is None:
        return raw, False, "score_missing_total"
    return raw, True, None


def classify_failure(work_dir: Path, exit_code: int, *, ok: bool) -> str:
    """
    Coarse category for evaluation matrix cells (debugging poor benchmark runs).

    ok=True, exit_code=0: requires valid score.json with ``total`` for ``completed``.

    ok=False or non-zero exit: infer from run_trace.txt / kb_compile.log when present.
    """
    work_dir = work_dir.resolve()

    if ok and exit_code == 0:
        outcome = classify_exit_zero_outcome(work_dir)
        return outcome["failure_category"]

    if read_llm_budget_guard(work_dir):
        return "llm_budget_guard"

    blob_l = _gather_eval_diag_text(work_dir).lower()

    if exit_code != 0 and not blob_l.strip():
        return "process_error"

    if "translation failed" in blob_l:
        return "translation"
    if "case extraction failed" in blob_l:
        return "case_extraction"
    if "kb compilation failed after" in blob_l:
        return "kb_repair_exhausted"
    if "law compilation failed" in blob_l or "kb compilation failed (llm call)" in blob_l:
        return "law_compilation"
    if "kb lint:" in blob_l or "kb lint failed" in blob_l:
        return "kb_lint"
    if "idp failed to parse" in blob_l or "failed to parse compiled kb" in blob_l:
        return "kb_idp_parse"
    if "kbsemanticerror" in blob_l or "theory is unsatisfiable" in blob_l:
        return "kb_semantic"
    if "symbolic reasoning failed" in blob_l or "symbol not in vocabulary" in blob_l:
        return "reasoning_symbol_mismatch"
    if "validation failed (case/query)" in blob_l:
        return "case_query_validation"
    if "validation failed" in blob_l and "(error)" in blob_l:
        return "kb_compile_validation"
    if exit_code != 0:
        return "process_error"
    return "unknown"


def classify_exit_zero_outcome(work_dir: Path) -> dict:
    """
    Classify a cell where main.py returned exit code 0.

    Returns dict with failure_category, score_present, score_path, missing_score_reason, scored.
    """
    work_dir = work_dir.resolve()
    score_path = work_dir / "score.json"
    sc, score_present, score_issue = assess_score_file(score_path)

    if score_issue == "score_malformed_json":
        return {
            "failure_category": "evaluation_bad_score",
            "score_present": False,
            "score_path": str(score_path),
            "missing_score_reason": "score_malformed_json",
            "scored": False,
            "score": None,
        }

    if not score_present:
        return {
            "failure_category": "evaluation_no_score",
            "score_present": False,
            "score_path": str(score_path) if score_path.is_file() else None,
            "missing_score_reason": score_issue or diagnose_missing_score_reason(work_dir),
            "scored": False,
            "score": sc,
        }

    results = _load_results_json(work_dir)
    if results:
        for q in results.get("questions") or []:
            pipe = (q or {}).get("pipeline") or {}
            if pipe.get("error_stage") or pipe.get("error"):
                return {
                    "failure_category": "completed_with_errors",
                    "score_present": True,
                    "score_path": str(score_path),
                    "missing_score_reason": None,
                    "scored": True,
                    "score": sc,
                }

    if score_has_symbolic_errors(sc):
        return {
            "failure_category": "completed_with_symbolic_errors",
            "score_present": True,
            "score_path": str(score_path),
            "missing_score_reason": None,
            "scored": True,
            "score": sc,
        }

    return {
        "failure_category": "completed",
        "score_present": True,
        "score_path": str(score_path),
        "missing_score_reason": None,
        "scored": True,
        "score": sc,
    }


def build_eval_cell(
    work_dir: Path,
    exit_code: int,
    *,
    path: str,
    duration_sec: float,
    strategy_metadata: dict,
) -> dict:
    """Build a matrix cell with score-presence fields and accurate ok/failure_category."""
    work_dir = work_dir.resolve()
    score_path = work_dir / "score.json"
    guard = read_llm_budget_guard(work_dir)

    if guard:
        return {
            "ok": False,
            "scored": False,
            "score_present": False,
            "score_path": None,
            "missing_score_reason": "llm_budget_guard",
            "exit_code": exit_code if exit_code != 0 else 1,
            "path": path,
            "failure_category": "llm_budget_guard",
            "duration_sec": duration_sec,
            "strategy_metadata": strategy_metadata,
            "llm_budget_scope": guard.get("scope"),
            "llm_budget_limit": guard.get("limit"),
            "llm_budget_count": guard.get("count"),
            "llm_cell_call_count": read_cell_llm_call_count(work_dir),
        }

    if exit_code != 0:
        sc = read_score(score_path)
        failure_category = classify_failure(work_dir, exit_code, ok=False)
        return {
            "ok": False,
            "scored": False,
            "score_present": score_path.is_file() and sc is not None and sc.get("total") is not None,
            "score_path": str(score_path) if score_path.is_file() else None,
            "missing_score_reason": diagnose_missing_score_reason(work_dir)
            if not score_path.is_file()
            else None,
            "exit_code": exit_code,
            "path": path,
            "accuracy": None,
            "accuracy_decisive": None,
            "correct": None,
            "correct_decisive": None,
            "incorrect_decisive": None,
            "inconclusive": None,
            "total": None,
            "scoring_mode": sc.get("scoring_mode") if sc else None,
            "score_id": sc.get("id") if sc else None,
            "query_targets": summarize_query_targets(sc).get("items") or [],
            "observable_query_target_warning_count": 0,
            "antecedent_diagnostic_warning_count": 0,
            "failure_category": failure_category,
            "duration_sec": duration_sec,
            "strategy_metadata": strategy_metadata,
        }

    outcome = classify_exit_zero_outcome(work_dir)
    sc = outcome.get("score")
    qt = summarize_query_targets(sc)
    failure_category = outcome["failure_category"]
    scored = bool(outcome.get("scored"))
    cell_ok = scored and failure_category == "completed"

    cell = {
        "ok": cell_ok,
        "scored": scored,
        "score_present": bool(outcome.get("score_present")),
        "score_path": outcome.get("score_path"),
        "missing_score_reason": outcome.get("missing_score_reason"),
        "exit_code": 0,
        "path": path,
        "failure_category": failure_category,
        "duration_sec": duration_sec,
        "strategy_metadata": strategy_metadata,
        "query_targets": qt.get("items") or [],
        "observable_query_target_warning_count": qt.get("observable_query_target_warning_count", 0),
        "antecedent_diagnostic_warning_count": qt.get("antecedent_diagnostic_warning_count", 0),
    }

    cell.update(summarize_score_diagnostics(sc))
    cell["llm_cell_call_count"] = read_cell_llm_call_count(work_dir)
    llm_summary_path = work_dir / "llm_call_summary.json"
    if llm_summary_path.is_file():
        try:
            llm_data = json.loads(llm_summary_path.read_text(encoding="utf-8"))
            if isinstance(llm_data, dict):
                cell["llm_total_tokens"] = llm_data.get("total_tokens")
                cell["llm_estimated_cost_usd"] = llm_data.get("estimated_cost_usd")
        except (json.JSONDecodeError, OSError):
            pass

    if scored and sc:
        cell.update(
            {
                "accuracy": sc.get("accuracy"),
                "accuracy_decisive": sc.get("accuracy_decisive")
                if sc.get("accuracy_decisive") is not None
                else sc.get("accuracy"),
                "correct": sc.get("correct"),
                "correct_decisive": sc.get("correct_decisive"),
                "incorrect_decisive": sc.get("incorrect_decisive"),
                "inconclusive": sc.get("inconclusive"),
                "total": sc.get("total"),
                "scoring_mode": sc.get("scoring_mode"),
                "score_id": sc.get("id"),
            }
        )
    else:
        cell.update(
            {
                "accuracy": None,
                "accuracy_decisive": None,
                "correct": None,
                "correct_decisive": None,
                "incorrect_decisive": None,
                "inconclusive": None,
                "total": None,
                "scoring_mode": None,
                "score_id": None,
            }
        )
    return cell


def summarize_matrix_status(cells: dict, runs: list[str], strategies: list[str]) -> dict:
    """Aggregate cell status counts for matrix summary and report.md."""
    counts = {
        "cells_total": 0,
        "scored_cells": 0,
        "evaluation_no_score_cells": 0,
        "completed_no_score_cells": 0,
        "evaluation_bad_score_cells": 0,
        "law_compilation_cells": 0,
        "other_failure_cells": 0,
        "accuracy_decisive_over_scored": None,
    }
    decisive_correct = 0
    decisive_total = 0

    for r in runs:
        for s in strategies:
            c = (cells.get(r) or {}).get(s)
            if not c:
                continue
            counts["cells_total"] += 1
            cat = c.get("failure_category") or ""
            if c.get("scored"):
                counts["scored_cells"] += 1
                decisive_correct += int(c.get("correct_decisive") or 0)
                decisive_total += int(c.get("correct_decisive") or 0) + int(
                    c.get("incorrect_decisive") or 0
                )
            elif cat == "evaluation_no_score":
                counts["evaluation_no_score_cells"] += 1
                counts["completed_no_score_cells"] += 1
            elif cat == "evaluation_bad_score":
                counts["evaluation_bad_score_cells"] += 1
            elif cat == "law_compilation":
                counts["law_compilation_cells"] += 1
            elif not c.get("ok"):
                counts["other_failure_cells"] += 1

    if decisive_total > 0:
        counts["accuracy_decisive_over_scored"] = decisive_correct / decisive_total
    return counts
