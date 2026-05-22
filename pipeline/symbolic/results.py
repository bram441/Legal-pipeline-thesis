"""Normalize symbolic intent outputs to stable JSON shapes."""

from __future__ import annotations

import re
from typing import Any

from pipeline.eval.boolean_belief import summarize_boolean_symbolic


def _epistemic_label(possible: bool | None, certain: bool | None) -> str:
    if certain:
        return "entailed"
    if possible is False:
        return "contradicted"
    return "unknown"


def _atom_dict(pred: str, args: list) -> dict:
    return {"predicate": pred, "args": [str(a) for a in args]}


def _func_dict(fn: str, args: list, value: Any) -> dict:
    return {"function": fn, "args": [str(a) for a in args], "value": value}


def unsupported_result(intent: str, message: str, *, output_kind: str = "unknown") -> dict:
    return {
        "intent": intent,
        "status": "unsupported",
        "output_kind": output_kind,
        "message": message,
    }


def error_result(intent: str, message: str, *, output_kind: str = "unknown") -> dict:
    return {
        "intent": intent,
        "status": "error",
        "output_kind": output_kind,
        "message": message,
    }


def normalize_deduction(raw: dict, query: dict) -> dict:
    possible = bool(raw.get("possible"))
    certain = bool(raw.get("certain"))
    label = _epistemic_label(possible, certain)
    return {
        "intent": "deduction",
        "status": "ok",
        "output_kind": "epistemic_boolean",
        "predicate": query.get("predicate"),
        "args": list(query.get("args") or []),
        "possible": possible,
        "certain": certain,
        "label": label,
        "atom": raw.get("atom"),
        "constraint": raw.get("constraint"),
        "certainty_class": "decisive" if label in ("entailed", "contradicted") else "inconclusive",
    }


def normalize_deduction_set(raw: dict, query: dict) -> dict:
    certain = [str(x) for x in (raw.get("entailed") or raw.get("certain") or [])]
    contradicted = [str(x) for x in (raw.get("contradicted") or [])]
    unknown = [str(x) for x in (raw.get("unknown") or [])]
    legacy_possible = raw.get("possible") or []
    if legacy_possible and not unknown:
        for x in legacy_possible:
            sx = str(x)
            if sx not in certain and sx not in contradicted:
                unknown.append(sx)
    return {
        "intent": "deduction_set",
        "status": "ok",
        "output_kind": "entity_set",
        "predicate": query.get("predicate") or raw.get("predicate"),
        "entailed": certain,
        "contradicted": contradicted,
        "unknown": unknown,
        "certainty_class": "decisive",
    }


def normalize_propagation(raw: dict, query: dict) -> dict:
    if raw.get("status") == "unsupported":
        return unsupported_result(
            "propagation",
            str(raw.get("message") or "Propagation unavailable."),
            output_kind="certain_facts",
        )
    return {
        "intent": "propagation",
        "status": "ok",
        "output_kind": "certain_facts",
        "certain_true": list(raw.get("certain_true") or []),
        "certain_false": list(raw.get("certain_false") or []),
        "function_values": list(raw.get("function_values") or []),
        "unknown": list(raw.get("unknown") or []),
        "focus_symbols": list(query.get("focus_symbols") or raw.get("focus_symbols") or []),
        "warnings": list(raw.get("warnings") or []),
        "raw": raw.get("structure") or raw.get("raw"),
        "certainty_class": "decisive",
    }


def _parse_model_text(text: str) -> dict:
    true_atoms: list[dict] = []
    false_atoms: list[dict] = []
    function_values: list[dict] = []
    if not text:
        return {"true_atoms": true_atoms, "false_atoms": false_atoms, "function_values": function_values, "raw": text}
    for line in str(text).splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.match(r"^(\w+)\(([^)]*)\)\s*=\s*(.+)$", s)
        if m:
            fn = m.group(1)
            args = [a.strip().strip("'\"") for a in m.group(2).split(",") if a.strip()]
            function_values.append(_func_dict(fn, args, m.group(3).strip()))
            continue
        m2 = re.match(r"^(\w+)\(([^)]*)\)\s*$", s)
        if m2:
            pred = m2.group(1)
            args = [a.strip().strip("'\"") for a in m2.group(2).split(",") if a.strip()]
            true_atoms.append(_atom_dict(pred, args))
    return {"true_atoms": true_atoms, "false_atoms": false_atoms, "function_values": function_values, "raw": text}


def normalize_model_expansion(raw: dict, query: dict) -> dict:
    if raw.get("status") == "unsupported":
        return unsupported_result(
            "model_expansion",
            str(raw.get("message") or "Model expansion unavailable."),
            output_kind="models",
        )
    models_out = []
    for m in raw.get("models") or []:
        if isinstance(m, dict) and "true_atoms" in m:
            models_out.append(m)
        else:
            models_out.append(_parse_model_text(str(m)))
    return {
        "intent": "model_expansion",
        "status": "ok",
        "output_kind": "models",
        "models": models_out,
        "sat": bool(raw.get("sat")),
        "focus_symbols": list(query.get("focus_symbols") or []),
        "certainty_class": "possible_model",
    }


def normalize_get_range(raw: dict, query: dict) -> dict:
    if raw.get("status") == "unsupported":
        return unsupported_result("get_range", str(raw.get("message") or "get_range unavailable."), output_kind="range")
    values = raw.get("values")
    if values is None and raw.get("range") is not None:
        rng = str(raw.get("range"))
        values = [v.strip() for v in re.split(r"[,;]", rng) if v.strip()] if "," in rng or ";" in rng else [rng]
    return {
        "intent": "get_range",
        "status": "ok",
        "output_kind": "range",
        "function": query.get("function") or raw.get("symbol") or query.get("symbol"),
        "args": list(query.get("args") or []),
        "values": values or [],
        "min": raw.get("min"),
        "max": raw.get("max"),
        "range": raw.get("range"),
        "entity": query.get("entity") or raw.get("entity"),
        "certainty_class": "range",
    }


def normalize_satisfiable(raw: dict, query: dict) -> dict:
    sat = bool(raw.get("satisfiable") if "satisfiable" in raw else raw.get("sat"))
    return {
        "intent": "satisfiable",
        "status": "ok",
        "output_kind": "boolean",
        "satisfiable": sat,
        "certainty_class": "consistency",
    }


def normalize_optimization(raw: dict, query: dict) -> dict:
    if raw.get("status") == "unsupported":
        return unsupported_result("optimization", str(raw.get("message") or "Optimization unavailable."), output_kind="optimum")
    return {
        "intent": "optimization",
        "status": "ok",
        "output_kind": "optimum",
        "direction": query.get("direction") or raw.get("direction"),
        "objective": query.get("objective") or raw.get("objective"),
        "value": raw.get("value") if "value" in raw else raw.get("result"),
        "model": raw.get("model"),
        "certainty_class": "decisive",
    }


def normalize_relevance(raw: dict, query: dict) -> dict:
    if raw.get("status") == "unsupported":
        return unsupported_result("relevance", str(raw.get("message") or "Relevance unavailable."), output_kind="symbols")
    syms = raw.get("relevant_symbols") or raw.get("relevance")
    if isinstance(syms, str):
        syms = [s.strip() for s in syms.split() if s.strip()]
    return {
        "intent": "relevance",
        "status": "ok",
        "output_kind": "symbols",
        "relevant_symbols": syms or [],
        "raw": raw.get("raw") or raw.get("relevance"),
        "certainty_class": "manual",
    }


def normalize_explain(raw: dict, query: dict) -> dict:
    if raw.get("status") == "unsupported":
        return unsupported_result("explain", str(raw.get("message") or "Explain unavailable."), output_kind="explanation")
    label = raw.get("label")
    if not label and "possible" in raw:
        summ = summarize_boolean_symbolic(raw)
        label = summ.get("label")
    return {
        "intent": "explain",
        "status": "ok",
        "output_kind": "explanation",
        "target": query.get("target") or raw.get("target"),
        "label": label,
        "explanation": raw.get("explanation") or raw.get("message") or "",
        "support": list(raw.get("support") or []),
        "raw": raw.get("raw"),
        "predicate": raw.get("predicate") or (query.get("target") or {}).get("predicate"),
        "args": raw.get("args") or (query.get("target") or {}).get("args"),
        "possible": raw.get("possible"),
        "certain": raw.get("certain"),
        "certainty_class": "manual",
    }


_NORMALIZERS = {
    "deduction": normalize_deduction,
    "deduction_set": normalize_deduction_set,
    "propagation": normalize_propagation,
    "model_expansion": normalize_model_expansion,
    "get_range": normalize_get_range,
    "satisfiable": normalize_satisfiable,
    "optimization": normalize_optimization,
    "relevance": normalize_relevance,
    "explain": normalize_explain,
}


def normalize_intent_result(intent: str, raw: dict, query: dict, sat: bool | None = None) -> dict:
    key = (intent or "").strip().lower()
    fn = _NORMALIZERS.get(key)
    if fn is None:
        return error_result(key, "No normalizer for intent: " + key)
    out = fn(raw or {}, query)
    if sat is not None and "sat" not in out:
        out["sat"] = sat
    spec_kind = out.get("output_kind")
    if spec_kind and "scoring_mode" not in out:
        out["internal_intent"] = key
    return out
