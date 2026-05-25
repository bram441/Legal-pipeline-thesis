"""
Pre-query satisfiability / consistency check on KB + case FO theory.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _evaluation_config() -> dict[str, Any]:
    from pipeline.config import config_section

    return dict(config_section("evaluation") or {})


def pre_query_satisfiability_enabled() -> bool:
    cfg = _evaluation_config()
    return bool(cfg.get("run_pre_query_satisfiability_check", True))


def continue_if_satisfiability_unsupported() -> bool:
    cfg = _evaluation_config()
    return bool(cfg.get("continue_if_satisfiability_unsupported", True))


def continue_if_satisfiability_error() -> bool:
    cfg = _evaluation_config()
    return bool(cfg.get("continue_if_satisfiability_error", False))


def run_pre_query_satisfiability_check(
    case: dict,
    base_kb_text: str,
    *,
    kb_schema: dict | None = None,
) -> dict[str, Any]:
    """
    Run IDP satisfiable check on composed KB + case structure.
    """
    t0 = time.perf_counter()
    base: dict[str, Any] = {
        "stage": "pre_query",
        "kb_case_satisfiable": None,
        "status": "unsupported",
        "details": "",
        "intent_backend": "idp_z3.tasks.satisfiable_check",
        "duration_seconds": None,
    }

    if not pre_query_satisfiability_enabled():
        base["status"] = "skipped"
        base["details"] = "run_pre_query_satisfiability_check=false"
        base["duration_seconds"] = round(time.perf_counter() - t0, 4)
        return base

    case_for_run = dict(case) if isinstance(case, dict) else case
    effective_kb = base_kb_text
    effective_schema = kb_schema
    if isinstance(case_for_run, dict) and case_for_run.get("case_given_factual_inputs") and kb_schema:
        from pipeline.kb.case_given_bridge import augment_kb_for_case_given

        effective_kb, effective_schema = augment_kb_for_case_given(
            base_kb_text,
            kb_schema,
            case_for_run,
        )
        case_for_run = {**case_for_run, "kb_schema": effective_schema}

    try:
        from idp_z3.tasks import satisfiable_check

        out = satisfiable_check(case_for_run, effective_kb)
        sat = bool(out.get("sat"))
        base["kb_case_satisfiable"] = sat
        base["status"] = "ok" if sat else "unsat"
        base["details"] = "theory satisfiable" if sat else "KB+case theory is unsatisfiable"
    except ImportError as e:
        base["status"] = "unsupported"
        base["details"] = "satisfiability backend unavailable: " + str(e)
    except Exception as e:
        base["status"] = "error"
        base["details"] = str(e)

    base["duration_seconds"] = round(time.perf_counter() - t0, 4)
    return base


def should_block_query_after_unsat(
    routing: dict[str, Any],
    sat_check: dict[str, Any],
) -> bool:
    """True when normal legal reasoning must not run on an unsat theory."""
    if sat_check.get("status") == "skipped":
        return False
    if sat_check.get("status") == "unsupported":
        return False
    if sat_check.get("status") == "error":
        return not continue_if_satisfiability_error()
    if sat_check.get("kb_case_satisfiable") is False:
        intent = str(routing.get("selected_intent") or "").lower()
        return intent != "satisfiable"
    return False


def should_abort_on_satisfiability_error(sat_check: dict[str, Any]) -> bool:
    return sat_check.get("status") == "error" and not continue_if_satisfiability_error()


def write_satisfiability_check(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
