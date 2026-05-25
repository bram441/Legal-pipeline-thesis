# pipeline/symbolic/router.py

from debug import debug_log

from pipeline.symbolic.antecedent_coverage import (
    compute_antecedent_coverage,
    format_missing_observable_feedback,
    missing_observable_symbols,
)
from pipeline.symbolic.executor import execute_intent
from pipeline.symbolic.intent_registry import get_intent_spec
from pipeline.symbolic.query_validate import validate_and_finalize_query


def _normalize_predicate_query_to_intent(query: dict) -> dict:
    """Map predicate surface form to internal intent execution query."""
    pred = (query.get("predicate") or "").strip()
    if not pred:
        raise ValueError("Predicate query missing 'predicate'")

    mode = (query.get("mode") or "").strip().lower()
    explain = bool(query.get("explain", False))
    args = query.get("args") or []
    if not isinstance(args, list):
        raise ValueError("query.args must be a list")

    if mode == "boolean":
        if explain:
            return {
                "type": "intent",
                "intent": "explain",
                "target": {"type": "predicate", "predicate": pred, "args": args},
                "predicate": pred,
                "args": args,
            }
        if len(args) < 1:
            raise ValueError("Boolean predicate query requires at least 1 argument")
        debug_log("router._normalize", "predicate boolean -> deduction")
        return {
            "type": "intent",
            "intent": "deduction",
            "predicate": pred,
            "mode": "boolean",
            "args": args,
        }

    if mode == "set":
        debug_log("router._normalize", "predicate set -> deduction_set")
        return {
            "type": "intent",
            "intent": "deduction_set",
            "predicate": pred,
            "mode": "set",
            "args": [],
        }

    raise ValueError("Unsupported predicate query mode: " + str(mode))


def _intent_from_query(query: dict) -> str:
    if str(query.get("type") or "").lower() == "intent":
        return str(query.get("intent") or query.get("internal_intent") or "").strip().lower()
    if str(query.get("type") or "").lower() == "predicate":
        mode = str(query.get("mode") or "boolean").lower()
        return "deduction_set" if mode == "set" else "deduction"
    raise ValueError("Cannot determine intent from query")


def run_query(case, query, base_kb_text, *, kb_schema=None, user_question=None):
    """Run symbolic reasoning; returns (sat, normalized symbolic_result)."""
    q_type = (query.get("type") or "").strip().lower()
    debug_log("router.run_query", "type=" + str(q_type))

    if q_type == "predicate":
        exec_query = _normalize_predicate_query_to_intent(query)
    elif q_type == "intent":
        exec_query = dict(query)
    else:
        raise ValueError("Unsupported query.type: " + str(q_type))

    intent = _intent_from_query(exec_query)
    get_intent_spec(intent)

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

    if effective_schema and isinstance(case_for_run, dict) and "kb_schema" not in case_for_run:
        case_for_run = {**case_for_run, "kb_schema": effective_schema}

    sat, result = execute_intent(
        intent,
        case_for_run,
        exec_query,
        effective_kb,
        kb_schema=effective_schema,
        user_question=user_question,
    )

    if effective_schema and isinstance(result, dict):
        coverage = compute_antecedent_coverage(
            case_for_run, query, effective_schema, symbolic_result=result
        )
        if coverage:
            result["antecedent_coverage"] = coverage
        label = str(result.get("label") or result.get("epistemic_label") or "").lower()
        if label == "unknown" or (result.get("possible") and not result.get("certain")):
            missing = missing_observable_symbols(coverage)
            if missing:
                hint = format_missing_observable_feedback(missing, effective_schema)
                if hint:
                    result["extraction_repair_hint"] = hint

    return sat, result
