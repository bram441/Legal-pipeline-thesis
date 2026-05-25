"""
Routed symbolic execution: intent classification, pre-query SAT, intent dispatch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pipeline.config import config_section
from pipeline.semantic.intent_routing import (
    INTENT_DEDUCTION,
    INTENT_EXPLAIN,
    INTENT_GET_RANGE,
    INTENT_MODEL_EXPANSION,
    INTENT_OPTIMIZATION,
    INTENT_PROPAGATION,
    INTENT_RELEVANCE,
    INTENT_SATISFIABLE,
    classify_symbolic_intent,
    write_symbolic_intent_routing,
)
from pipeline.symbolic.consistency_check import (
    run_pre_query_satisfiability_check,
    should_abort_on_satisfiability_error,
    should_block_query_after_unsat,
    write_satisfiability_check,
)
from pipeline.symbolic.model_expansion_outputs import extract_possible_outputs
from pipeline.symbolic.router import run_query


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _model_expansion_max_models() -> int:
    cfg = config_section("evaluation") or {}
    raw = cfg.get("model_expansion_max_models", 3)
    try:
        val = int(raw)
    except (TypeError, ValueError):
        val = 3
    return max(1, min(5, val))


def _optimization_supported() -> bool:
    try:
        from importlib import import_module

        mod = import_module("idp_z3.intents.optimization")
        return getattr(mod, "run", None) is not None
    except Exception:
        return False


def build_execution_query(
    validated_query: dict,
    routing: dict[str, Any],
    *,
    kb_schema: dict | None = None,
) -> dict:
    """Map routing + validated query to the query shape expected by router/executor."""
    intent = str(routing.get("selected_intent") or "").lower()
    q = dict(validated_query) if isinstance(validated_query, dict) else {}

    if intent == INTENT_DEDUCTION:
        if str(q.get("type") or "").lower() == "predicate":
            return {**q, "mode": "boolean", "explain": False}
        pred = str(q.get("predicate") or "").strip()
        if pred:
            return {
                "type": "predicate",
                "predicate": pred,
                "mode": "boolean",
                "args": list(q.get("args") or []),
                "explain": False,
            }
        raise ValueError("deduction requires a boolean predicate target")

    if intent == INTENT_MODEL_EXPANSION:
        focus = list(routing.get("legal_output_symbols") or [])
        if q.get("focus_symbols"):
            focus = list(q.get("focus_symbols"))
        return {
            "type": "intent",
            "intent": INTENT_MODEL_EXPANSION,
            "max_models": int(q.get("max_models") or _model_expansion_max_models()),
            "focus_symbols": focus,
            "focus_entities": list(q.get("focus_entities") or []),
        }

    if intent in (INTENT_GET_RANGE, INTENT_OPTIMIZATION):
        fn = str(q.get("function") or q.get("symbol") or "").strip()
        if not fn and kb_schema:
            for f in kb_schema.get("functions") or []:
                if isinstance(f, dict) and f.get("name"):
                    fn = str(f["name"])
                    break
        if not fn:
            raise ValueError(intent + " requires query.function or query.symbol")
        out = {
            "type": "intent",
            "intent": intent,
            "function": fn,
            "symbol": fn,
            "args": list(q.get("args") or []),
            "entity": q.get("entity"),
        }
        if intent == INTENT_OPTIMIZATION:
            direction = str(q.get("direction") or "min").lower()
            if "maximum" in (routing.get("question") or "").lower():
                direction = "max"
            out["direction"] = direction
            out["objective"] = q.get("objective") or fn
        return out

    if intent == INTENT_SATISFIABLE:
        return {"type": "intent", "intent": INTENT_SATISFIABLE}

    if intent == INTENT_EXPLAIN:
        if str(q.get("type") or "").lower() == "predicate" and q.get("predicate"):
            return {
                "type": "intent",
                "intent": INTENT_EXPLAIN,
                "target": {
                    "type": "predicate",
                    "predicate": q.get("predicate"),
                    "args": list(q.get("args") or []),
                },
                "predicate": q.get("predicate"),
                "args": list(q.get("args") or []),
            }
        return {"type": "intent", "intent": INTENT_EXPLAIN, "target": q.get("target")}

    if intent in (INTENT_RELEVANCE, INTENT_PROPAGATION):
        return {"type": "intent", "intent": intent, **{k: v for k, v in q.items() if k != "type"}}

    if str(q.get("type") or "").lower() == "intent":
        return q
    raise ValueError("unsupported or unknown selected_intent: " + intent)


def build_unified_symbolic_result(
    *,
    routing: dict[str, Any],
    sat_check: dict[str, Any],
    normalized: dict[str, Any],
    exec_query: dict,
) -> dict[str, Any]:
    """Attach routing, satisfiability, and intent-specific sections to normalized result."""
    intent = str(normalized.get("intent") or routing.get("selected_intent") or "").lower()
    status = str(normalized.get("status") or "ok").lower()
    sym_status = status
    if sat_check.get("status") == "unsat" and sat_check.get("kb_case_satisfiable") is False:
        if intent != INTENT_SATISFIABLE:
            sym_status = "inconsistent"
    if status in ("unsupported", "error"):
        sym_status = status

    out: dict[str, Any] = {
        "intent": intent,
        "symbolic_status": sym_status,
        "status": sym_status if sym_status != "ok" else normalized.get("status", "ok"),
        "scorable": bool(routing.get("scorable")),
        "detected_question_type": routing.get("detected_question_type"),
        "selected_intent": routing.get("selected_intent"),
        "selected_reason": routing.get("selected_reason"),
        "routing": routing,
        "satisfiability_check": sat_check,
        "warnings": list(routing.get("warnings") or []) + list(normalized.get("warnings") or []),
        "deduction": None,
        "model_expansion": None,
        "get_range": None,
        "satisfiable": None,
        "explanation": None,
        "execution_query": exec_query,
    }

    for key in (
        "output_kind",
        "certainty_class",
        "predicate",
        "args",
        "label",
        "possible",
        "certain",
        "message",
        "sat",
        "antecedent_coverage",
        "extraction_repair_hint",
    ):
        if key in normalized:
            out[key] = normalized[key]

    if intent == INTENT_DEDUCTION:
        out["deduction"] = {k: normalized.get(k) for k in normalized if k not in ("routing",)}
        out["status"] = normalized.get("status", "ok")
        out["symbolic_status"] = sym_status if sym_status != "inconsistent" else sym_status
    elif intent == INTENT_MODEL_EXPANSION:
        models = normalized.get("models") or []
        possible = extract_possible_outputs(
            models,
            focus_symbols=exec_query.get("focus_symbols"),
            legal_output_symbols=routing.get("legal_output_symbols"),
        )
        max_m = int(exec_query.get("max_models") or _model_expansion_max_models())
        me = {
            "possible_outputs": possible,
            "model_count": len(models),
            "max_models": max_m,
            "complete": False,
            "warnings": [
                "model expansion enumerates examples, not guaranteed exhaustive unless backend proves complete"
            ],
        }
        if not possible and status == "ok":
            me["status"] = "no_output_symbols_available"
            me["warnings"].append("no legal_output symbols matched in expanded models")
            out["symbolic_status"] = "unsupported"
            out["status"] = "unsupported"
            out["message"] = "no_output_symbols_available"
        out["model_expansion"] = me
        out["models"] = models
    elif intent == INTENT_GET_RANGE:
        conf = normalized.get("confidence") or "idp_get_range"
        out["get_range"] = {
            "target": {
                "function": normalized.get("function") or exec_query.get("function"),
                "args": normalized.get("args") or exec_query.get("args"),
            },
            "range": normalized.get("range"),
            "values": normalized.get("values"),
            "min": normalized.get("min"),
            "max": normalized.get("max"),
            "confidence": conf,
            "warnings": list(normalized.get("warnings") or []),
        }
    elif intent == INTENT_OPTIMIZATION:
        out["get_range"] = {
            "target": {"function": exec_query.get("objective") or exec_query.get("function")},
            "value": normalized.get("value"),
            "direction": normalized.get("direction"),
            "confidence": "optimization" if status == "ok" else status,
            "warnings": list(routing.get("warnings") or []),
        }
        out["intent"] = INTENT_OPTIMIZATION
    elif intent == INTENT_SATISFIABLE:
        sat_val = normalized.get("satisfiable")
        if sat_check.get("kb_case_satisfiable") is not None and sat_check.get("status") in ("ok", "unsat"):
            sat_val = bool(sat_check.get("kb_case_satisfiable"))
        out["satisfiable"] = {
            "kb_case_satisfiable": sat_val,
            "answer": bool(sat_val) if sat_val is not None else None,
            "symbolic_status": "ok" if status == "ok" else status,
        }
    elif intent in (INTENT_EXPLAIN, INTENT_RELEVANCE, INTENT_PROPAGATION):
        out["explanation"] = {
            "intent": intent,
            "answer": normalized.get("explanation") or normalized.get("message") or "",
            "support": normalized.get("support") or normalized.get("relevant_symbols"),
            "parsed": status == "ok",
            "warnings": list(normalized.get("warnings") or []),
            "raw": normalized,
        }

    if sym_status == "inconsistent":
        out["message"] = out.get("message") or sat_check.get("details")
    return out


def _inconsistent_result(routing: dict, sat_check: dict, exec_query: dict) -> dict[str, Any]:
    return build_unified_symbolic_result(
        routing=routing,
        sat_check=sat_check,
        normalized={
            "intent": routing.get("selected_intent"),
            "status": "inconsistent",
            "message": sat_check.get("details") or "KB+case unsatisfiable",
        },
        exec_query=exec_query,
    )


def _unsupported_result(routing: dict, sat_check: dict, message: str) -> dict[str, Any]:
    return build_unified_symbolic_result(
        routing=routing,
        sat_check=sat_check,
        normalized={
            "intent": routing.get("selected_intent"),
            "status": "unsupported",
            "message": message,
        },
        exec_query={},
    )


def _maybe_run_intent_diagnostics(
    case,
    query,
    base_kb_text,
    *,
    kb_schema=None,
    user_question=None,
    artifact_dir: Path | None,
) -> dict[str, Any] | None:
    cfg = config_section("evaluation") or {}
    if not cfg.get("enable_intent_diagnostics_on_unknown"):
        return None
    try:
        from pipeline.symbolic.executor import execute_intent

        diag: dict[str, Any] = {}
        for intent in (INTENT_RELEVANCE, INTENT_PROPAGATION):
            try:
                _, raw = execute_intent(
                    intent,
                    case,
                    {"type": "intent", "intent": intent},
                    base_kb_text,
                    kb_schema=kb_schema,
                    user_question=user_question,
                )
                diag[intent] = raw
            except Exception as e:
                diag[intent] = {"status": "error", "message": str(e)}
        if artifact_dir:
            _write_json(artifact_dir / "intent_diagnostics.json", diag)
        return diag
    except Exception:
        return None


def execute_routed_symbolic_query(
    case: dict,
    query: dict,
    base_kb_text: str,
    *,
    user_question: str | None = None,
    expected: dict | None = None,
    kb_schema: dict | None = None,
    schema_environment: dict | None = None,
    artifact_dir: str | Path | None = None,
) -> tuple[bool | None, dict[str, Any], dict[str, Any]]:
    """
    Classify intent, run pre-query SAT, execute selected intent, return unified result.
    """
    art = Path(artifact_dir) if artifact_dir else None

    routing = classify_symbolic_intent(
        question_text=user_question or "",
        expected=expected,
        query=query,
        kb_schema=kb_schema,
        schema_environment=schema_environment,
        optimization_supported=_optimization_supported(),
    )
    if art:
        write_symbolic_intent_routing(art / "symbolic_intent_routing.json", routing)

    sat_check = run_pre_query_satisfiability_check(case, base_kb_text, kb_schema=kb_schema)
    if art:
        write_satisfiability_check(art / "satisfiability_check.json", sat_check)

    selected = str(routing.get("selected_intent") or "").lower()
    if selected == "unknown":
        return None, _unsupported_result(
            routing, sat_check, "unknown_intent: no concrete symbolic target"
        ), routing

    if should_abort_on_satisfiability_error(sat_check):
        return None, _unsupported_result(
            routing, sat_check, "satisfiability_check_error: " + str(sat_check.get("details"))
        ), routing

    try:
        exec_query = build_execution_query(query, routing, kb_schema=kb_schema)
    except ValueError as e:
        return None, _unsupported_result(routing, sat_check, str(e)), routing

    if should_block_query_after_unsat(routing, sat_check):
        return False, _inconsistent_result(routing, sat_check, exec_query), routing

    if selected == INTENT_SATISFIABLE and sat_check.get("kb_case_satisfiable") is not None:
        sat_val = bool(sat_check["kb_case_satisfiable"])
        normalized = {
            "intent": INTENT_SATISFIABLE,
            "status": "ok",
            "satisfiable": sat_val,
            "output_kind": "boolean",
        }
        unified = build_unified_symbolic_result(
            routing=routing,
            sat_check=sat_check,
            normalized=normalized,
            exec_query=exec_query,
        )
        if art:
            _write_json(art / "symbolic_result.json", unified)
        return sat_val, unified, routing

    sat, normalized = run_query(
        case,
        exec_query,
        base_kb_text,
        kb_schema=kb_schema,
        user_question=user_question,
    )

    unified = build_unified_symbolic_result(
        routing=routing,
        sat_check=sat_check,
        normalized=normalized,
        exec_query=exec_query,
    )

    if (
        unified.get("symbolic_status") == "ok"
        and unified.get("deduction")
        and str(unified.get("label") or unified.get("certainty_class") or "").lower()
        in ("unknown", "inconclusive")
    ):
        _maybe_run_intent_diagnostics(
            case,
            query,
            base_kb_text,
            kb_schema=kb_schema,
            user_question=user_question,
            artifact_dir=art,
        )

    if art:
        _write_json(art / "symbolic_result.json", unified)

    return sat, unified, routing
