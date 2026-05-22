"""Validate and migrate normalized runtime queries (law-agnostic)."""

from __future__ import annotations

import re
from typing import Any

from pipeline.symbolic.ground_atoms import derived_symbols, entities_for_type, function_sig, predicate_sig
from pipeline.symbolic.intent_registry import (
    IntentAccessError,
    UnknownIntentError,
    get_intent_spec,
    list_public_intents,
    validate_intent_name,
)

_QUERY_WILDCARDS = frozenset({"?", "_", "*", "any"})
_MAX_MODELS = 5
_NUMERIC_RETURNS = frozenset({"int", "real", "float", "money", "percentage"})


def _norm_name(s: str) -> str:
    return (s or "").strip().lower().replace("_", "")


def _case_entity_set(case: dict | None) -> set[str]:
    out: set[str] = set()
    for vals in ((case or {}).get("entities") or {}).values():
        if isinstance(vals, list):
            for v in vals:
                if isinstance(v, str) and v.strip():
                    out.add(v.strip().lower())
    return out


def _resolve_predicate(name: str, kb_schema: dict | None) -> tuple[str, dict]:
    sig = predicate_sig(kb_schema, name)
    if not sig:
        raise ValueError("Unknown predicate in query (not in kb_schema): " + name)
    return str(sig["name"]), sig


def _resolve_function(name: str, kb_schema: dict | None) -> tuple[str, dict]:
    sig = function_sig(kb_schema, name)
    if not sig:
        raise ValueError("Unknown function in query (not in kb_schema): " + name)
    return str(sig["name"]), sig


def _validate_entity_refs(entities: list[str], case: dict | None) -> None:
    if not entities:
        return
    allowed = _case_entity_set(case)
    if not allowed:
        return
    for e in entities:
        if e and e.lower() not in allowed:
            raise ValueError(
                "focus_entities contains '{}' not present in case entities: {}.".format(
                    e, ", ".join(sorted(allowed))
                )
            )


def _validate_focus_symbols(symbols: list[str], kb_schema: dict | None) -> list[str]:
    if not kb_schema:
        return symbols
    known = set()
    for p in kb_schema.get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            known.add(str(p["name"]))
    for f in kb_schema.get("functions") or []:
        if isinstance(f, dict) and f.get("name"):
            known.add(str(f["name"]))
    out = []
    for s in symbols:
        s = str(s).strip()
        if not s:
            continue
        match = next((k for k in known if k == s or _norm_name(k) == _norm_name(s)), None)
        if not match:
            raise ValueError("focus_symbols entry not in KB schema: " + s)
        out.append(match)
    return out


def migrate_legacy_intent_query(raw: dict, kb_schema: dict | None = None) -> dict:
    """Convert deprecated direct deduction/deduction_set intents to predicate queries."""
    if str(raw.get("type") or "").lower() != "intent":
        return raw
    intent = str(raw.get("intent") or "").strip().lower()
    if intent == "deduction":
        pred = str(raw.get("predicate") or raw.get("predicate_hint") or "").strip()
        args = raw.get("args") or []
        if pred:
            return {
                "type": "predicate",
                "predicate": pred,
                "mode": "boolean",
                "args": args,
                "explain": bool(raw.get("explain", False)),
            }
        raise ValueError(
            "Direct intent=deduction is deprecated. Use type=predicate, mode=boolean with predicate and args."
        )
    if intent == "deduction_set":
        pred = str(raw.get("predicate") or raw.get("predicate_hint") or "").strip()
        if pred:
            return {
                "type": "predicate",
                "predicate": pred,
                "mode": "set",
                "args": ["?"],
                "explain": bool(raw.get("explain", False)),
            }
        raise ValueError(
            "Direct intent=deduction_set is deprecated. Use type=predicate, mode=set with predicate_hint."
        )
    if intent == "explain" and raw.get("predicate"):
        return {
            "type": "intent",
            "intent": "explain",
            "target": {
                "type": "predicate",
                "predicate": raw.get("predicate"),
                "args": raw.get("args") or [],
            },
            "explain": True,
        }
    return raw


def validate_and_finalize_query(raw_query: dict, case: dict | None, kb_schema: dict | None = None) -> dict:
    """Validate runtime query after extraction normalization."""
    if not isinstance(raw_query, dict):
        raise ValueError("query must be a dict")
    q = migrate_legacy_intent_query(dict(raw_query), kb_schema)
    q_type = str(q.get("type") or "").strip().lower()
    explain_flag = bool(q.get("explain", False))

    if q_type == "predicate" and explain_flag and not q.get("mode") == "set":
        return validate_and_finalize_query(
            {
                "type": "intent",
                "intent": "explain",
                "target": {
                    "type": "predicate",
                    "predicate": q.get("predicate"),
                    "args": q.get("args") or [],
                },
            },
            case,
            kb_schema,
        )

    if q_type == "intent":
        intent = validate_intent_name(str(q.get("intent") or ""), allow_internal=False)
        spec = get_intent_spec(intent)
        if intent == "get_range":
            fn = str(q.get("function") or q.get("symbol") or "").strip()
            if not fn:
                raise ValueError("get_range requires query.function")
            fn, fsig = _resolve_function(fn, kb_schema)
            args = [_norm_arg(a) for a in (q.get("args") or [])]
            arity = len(fsig.get("args") or [])
            if len(args) != arity:
                raise ValueError(f"get_range function {fn} expects {arity} args, got {len(args)}")
            ret = str(fsig.get("returns") or "").strip().lower()
            if ret == "bool":
                raise ValueError("get_range requires a numeric function, not a Boolean predicate")
            _validate_args_in_case(args, fsig.get("args") or [], case)
            return {
                "type": "intent",
                "intent": "get_range",
                "function": fn,
                "args": args,
                "entity": str(q.get("entity") or q.get("entity_hint") or "").strip().lower(),
                "explain": explain_flag,
                "query_type": "get_range",
                "internal_intent": "get_range",
            }
        if intent == "satisfiable":
            return {
                "type": "intent",
                "intent": "satisfiable",
                "explain": explain_flag,
                "query_type": "satisfiable",
                "internal_intent": "satisfiable",
            }
        if intent == "propagation":
            focus = _validate_focus_symbols(list(q.get("focus_symbols") or []), kb_schema)
            if not focus:
                focus = derived_symbols(kb_schema, include_functions=False)
            focus_entities = [str(x).strip().lower() for x in (q.get("focus_entities") or []) if str(x).strip()]
            _validate_entity_refs(focus_entities, case)
            return {
                "type": "intent",
                "intent": "propagation",
                "focus_symbols": focus,
                "focus_entities": focus_entities,
                "include_unknown": bool(q.get("include_unknown", False)),
                "explain": explain_flag,
                "query_type": "propagation",
                "internal_intent": "propagation",
            }
        if intent == "model_expansion":
            focus = _validate_focus_symbols(list(q.get("focus_symbols") or []), kb_schema)
            if not focus:
                focus = derived_symbols(kb_schema, include_functions=False)
            max_models = q.get("max_models")
            if max_models is None:
                max_models = 1
            max_models = int(max_models)
            if max_models < 1 or max_models > _MAX_MODELS:
                raise ValueError(f"model_expansion.max_models must be between 1 and {_MAX_MODELS}")
            focus_entities = [str(x).strip().lower() for x in (q.get("focus_entities") or []) if str(x).strip()]
            _validate_entity_refs(focus_entities, case)
            return {
                "type": "intent",
                "intent": "model_expansion",
                "focus_symbols": focus,
                "focus_entities": focus_entities,
                "max_models": max_models,
                "explain": explain_flag,
                "query_type": "model_expansion",
                "internal_intent": "model_expansion",
            }
        if intent == "optimization":
            direction = str(q.get("direction") or "").strip().lower()
            if direction not in ("min", "max"):
                raise ValueError("optimization.direction must be min or max")
            obj = q.get("objective") or {}
            if not isinstance(obj, dict):
                raise ValueError("optimization.objective must be an object")
            fn = str(obj.get("function") or "").strip()
            if not fn:
                raise ValueError("optimization.objective.function is required")
            fn, fsig = _resolve_function(fn, kb_schema)
            args = [_norm_arg(a) for a in (obj.get("args") or [])]
            if len(args) != len(fsig.get("args") or []):
                raise ValueError("optimization objective arity mismatch")
            ret = str(fsig.get("returns") or "").strip().lower()
            if ret not in _NUMERIC_RETURNS:
                raise ValueError("optimization objective must be a numeric function")
            _validate_args_in_case(args, fsig.get("args") or [], case)
            return {
                "type": "intent",
                "intent": "optimization",
                "direction": direction,
                "objective": {"function": fn, "args": args},
                "explain": explain_flag,
                "query_type": "optimization",
                "internal_intent": "optimization",
            }
        if intent == "relevance":
            focus = _validate_focus_symbols(list(q.get("focus_symbols") or []), kb_schema)
            return {
                "type": "intent",
                "intent": "relevance",
                "focus_symbols": focus,
                "explain": explain_flag,
                "query_type": "relevance",
                "internal_intent": "relevance",
            }
        if intent == "explain":
            target = q.get("target")
            if not isinstance(target, dict):
                raise ValueError("explain requires query.target")
            ttype = str(target.get("type") or "").strip().lower()
            if ttype == "satisfiable":
                return {
                    "type": "intent",
                    "intent": "explain",
                    "target": {"type": "satisfiable"},
                    "explain": True,
                    "query_type": "explain",
                    "internal_intent": "explain",
                }
            if ttype == "predicate":
                pred, sig = _resolve_predicate(str(target.get("predicate") or target.get("predicate_hint") or ""), kb_schema)
                args = [_norm_arg(a) for a in (target.get("args") or [])]
                if len(args) != len(sig.get("args") or []):
                    raise ValueError("explain predicate target arity mismatch")
                _validate_args_in_case(args, sig.get("args") or [], case)
                return {
                    "type": "intent",
                    "intent": "explain",
                    "target": {"type": "predicate", "predicate": pred, "args": args},
                    "predicate": pred,
                    "args": args,
                    "explain": True,
                    "query_type": "explain",
                    "internal_intent": "explain",
                }
            raise ValueError("explain.target.type must be predicate or satisfiable")
        raise ValueError("Unsupported public intent: " + intent)

    if q_type != "predicate":
        raise ValueError("Unsupported query.type: " + str(q.get("type")))

    pred, sig = _resolve_predicate(str(q.get("predicate") or ""), kb_schema)
    mode = str(q.get("mode") or "boolean").strip().lower()
    if mode not in ("boolean", "set"):
        raise ValueError("query.mode must be boolean or set")
    args = [_norm_arg(a) for a in (q.get("args") or [])]
    arity = len(sig.get("args") or [])
    if mode == "set":
        if arity != 1:
            raise ValueError(
                f"Predicate set queries currently support only unary predicates. '{pred}' has arity {arity}."
            )
        if args and not all(a in _QUERY_WILDCARDS for a in args):
            raise ValueError("Set mode requires args ['?'] or empty args")
        args = ["?"]
        internal = "deduction_set"
    else:
        if len(args) != arity:
            raise ValueError(f"Predicate arity mismatch for {pred}: expected {arity}, got {len(args)}")
        _validate_args_in_case(args, sig.get("args") or [], case)
        internal = "deduction"
    out = {
        "type": "predicate",
        "predicate": pred,
        "mode": mode,
        "args": args,
        "explain": explain_flag,
        "predicate_kind": str(q.get("predicate_kind") or sig.get("kind") or ""),
        "query_type": "predicate_" + mode,
        "internal_intent": internal,
    }
    return out


def _norm_arg(a: Any) -> str:
    if not isinstance(a, str):
        raise ValueError("query args must be strings")
    s = a.strip().lower()
    if s in _QUERY_WILDCARDS:
        return "?"
    return s


def _validate_args_in_case(args: list[str], arg_types: list[str], case: dict | None) -> None:
    allowed_all = _case_entity_set(case)
    if not allowed_all:
        return
    for arg, typ in zip(args, arg_types):
        if arg in _QUERY_WILDCARDS:
            continue
        pool = set(entities_for_type(case, str(typ)))
        if pool and arg not in pool and arg not in allowed_all:
            raise ValueError(f"Query arg '{arg}' is not a valid {typ} entity in the case")


def public_intent_enum() -> list[str]:
    return list(list_public_intents())
