"""Execute symbolic intents via registry with normalized outputs."""

from __future__ import annotations

from importlib import import_module

from debug import debug_log

from pipeline.symbolic.fallbacks import (
    run_deduction_set_fallback,
    run_explain_fallback,
    run_propagation_fallback,
)
from pipeline.symbolic.intent_registry import get_intent_spec
from pipeline.symbolic.results import error_result, normalize_intent_result, unsupported_result


def _import_intent_module(intent: str):
    try:
        return import_module("idp_z3.intents." + intent)
    except ModuleNotFoundError as e:
        raise ValueError("Unsupported intent (module missing): " + intent) from e
    except Exception as e:
        raise ValueError("Unsupported intent: " + intent + " (" + str(e) + ")") from e


def _run_module(intent: str, case, query, base_kb_text):
    mod = _import_intent_module(intent)
    run_fn = getattr(mod, "run", None)
    if run_fn is None:
        raise ValueError("Intent handler has no run(): " + intent)
    return run_fn(case=case, base_kb_text=base_kb_text, query=query)


def execute_intent(
    intent: str,
    case,
    query,
    base_kb_text: str,
    *,
    kb_schema=None,
    user_question: str | None = None,
) -> tuple[bool | None, dict]:
    """Run intent and return (sat, normalized_result)."""
    key = (intent or "").strip().lower()
    get_intent_spec(key)
    debug_log("executor.execute_intent", "intent=" + key)

    try:
        if key == "deduction_set":
            try:
                sat, raw = _run_module(key, case, query, base_kb_text)
            except ValueError:
                raw = run_deduction_set_fallback(case, base_kb_text, query, kb_schema)
                sat = True
            else:
                if not raw.get("entailed") and not raw.get("certain") and raw.get("mode") == "set":
                    raw = run_deduction_set_fallback(case, base_kb_text, query, kb_schema)
            return sat, normalize_intent_result(key, raw, query, sat)

        if key == "propagation":
            raw = None
            sat = True
            try:
                sat, raw = _run_module(key, case, query, base_kb_text)
            except (RuntimeError, ValueError, Exception):
                raw = None
            if not raw or (raw.get("structure") and not raw.get("certain_true")):
                fb = run_propagation_fallback(
                    case, base_kb_text, query, kb_schema, user_question=user_question
                )
                if raw and raw.get("structure"):
                    fb["structure"] = raw.get("structure")
                raw = fb
            return sat, normalize_intent_result(key, raw, query, sat)

        if key == "model_expansion":
            try:
                sat, raw = _run_module(key, case, query, base_kb_text)
            except Exception as e:
                return None, unsupported_result("model_expansion", str(e), output_kind="models")
            return sat, normalize_intent_result(key, raw, query, sat)

        if key == "explain":
            raw = run_explain_fallback(case, base_kb_text, query, kb_schema)
            return True, normalize_intent_result(key, raw, query, True)

        if key in ("relevance", "optimization"):
            try:
                sat, raw = _run_module(key, case, query, base_kb_text)
            except Exception as e:
                return None, unsupported_result(key, str(e), output_kind=get_intent_spec(key).output_kind)
            if raw.get("error") == "intent_not_implemented":
                return None, unsupported_result(key, "Intent not implemented in IDP bindings.", output_kind=get_intent_spec(key).output_kind)
            return sat, normalize_intent_result(key, raw, query, sat)

        sat, raw = _run_module(key, case, query, base_kb_text)
        return sat, normalize_intent_result(key, raw, query, sat)

    except ValueError as e:
        return None, error_result(key, str(e))
    except Exception as e:
        return None, error_result(key, str(e))
