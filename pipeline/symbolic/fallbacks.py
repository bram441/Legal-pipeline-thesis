"""Generic fallback implementations when IDP APIs are unavailable."""

from __future__ import annotations

from idp_z3.predicate_solver import evaluate_atom

from pipeline.symbolic.ground_atoms import (
    derived_symbols,
    filter_symbols_by_question,
    function_sig,
    grounded_predicate_candidates,
    predicate_sig,
)


def run_deduction_set_fallback(case, base_kb_text, query, kb_schema=None) -> dict:
    predicate = (query.get("predicate") or "").strip()
    sig = predicate_sig(kb_schema, predicate)
    if not sig:
        raise ValueError("Unknown predicate: " + predicate)
    arg_types = list(sig.get("args") or [])
    if len(arg_types) != 1:
        raise ValueError(
            f"deduction_set currently supports only unary predicates. Predicate '{predicate}' has arity {len(arg_types)}."
        )
    candidates, warn = grounded_predicate_candidates(kb_schema, case, predicate)
    entailed: list[str] = []
    contradicted: list[str] = []
    unknown: list[str] = []
    for args in candidates:
        ent = args[0]
        res = evaluate_atom(case, base_kb_text, predicate, args)
        if res.get("certain"):
            entailed.append(ent)
        elif not res.get("possible"):
            contradicted.append(ent)
        else:
            unknown.append(ent)
    out = {
        "predicate": predicate,
        "entailed": entailed,
        "contradicted": contradicted,
        "unknown": unknown,
    }
    if warn:
        out["warnings"] = [warn]
    return out


def run_propagation_fallback(case, base_kb_text, query, kb_schema=None, user_question: str | None = None) -> dict:
    focus = list(query.get("focus_symbols") or [])
    if not focus:
        focus = derived_symbols(kb_schema, include_functions=False)
        if user_question:
            focus = filter_symbols_by_question(focus, kb_schema, user_question)
    focus_entities = [_safe(x) for x in (query.get("focus_entities") or []) if _safe(x)]
    include_unknown = bool(query.get("include_unknown", False))
    certain_true: list[dict] = []
    certain_false: list[dict] = []
    unknown: list[dict] = []
    warnings: list[str] = []

    for sym in focus:
        sig = predicate_sig(kb_schema, sym)
        if not sig or str(sig.get("returns") or "").lower() != "bool":
            continue
        combos, warn = grounded_predicate_candidates(
            kb_schema, case, sym, focus_entities=focus_entities or None
        )
        if warn:
            warnings.append(warn)
        for args in combos:
            atom = {"predicate": sym, "args": args}
            res = evaluate_atom(case, base_kb_text, sym, args)
            if res.get("certain"):
                certain_true.append(atom)
            elif not res.get("possible"):
                certain_false.append(atom)
            elif include_unknown:
                unknown.append(atom)

    return {
        "certain_true": certain_true,
        "certain_false": certain_false,
        "function_values": [],
        "unknown": unknown,
        "focus_symbols": focus,
        "warnings": warnings,
        "fallback": True,
    }


def _safe(v) -> str:
    s = str(v or "").strip().lower()
    return s if s else ""


def run_explain_fallback(case, base_kb_text, query, kb_schema=None) -> dict:
    target = query.get("target") or {}
    ttype = str(target.get("type") or "").strip().lower()
    if ttype == "satisfiable":
        from idp_z3.tasks import satisfiable_check

        sat = bool(satisfiable_check(case, base_kb_text=base_kb_text).get("sat"))
        msg = "The case and law are satisfiable (at least one model exists)." if sat else (
            "The case and law are inconsistent (no model exists)."
        )
        return {
            "target": target,
            "explanation": msg,
            "support": [],
            "satisfiable": sat,
        }
    pred = str(target.get("predicate") or query.get("predicate") or "").strip()
    args = list(target.get("args") or query.get("args") or [])
    if not pred or not args:
        raise ValueError("explain target requires predicate and args")
    res = evaluate_atom(case, base_kb_text, pred, [str(a) for a in args])
    label = "entailed" if res.get("certain") else ("contradicted" if not res.get("possible") else "unknown")
    support = []
    try:
        prop = run_propagation_fallback(case, base_kb_text, {"focus_symbols": [pred]}, kb_schema)
        for item in prop.get("certain_true") or []:
            if item.get("predicate") != pred:
                support.append(item)
    except Exception:
        pass
    return {
        "target": {"type": "predicate", "predicate": pred, "args": args},
        "predicate": pred,
        "args": args,
        "label": label,
        "possible": res.get("possible"),
        "certain": res.get("certain"),
        "explanation": (
            f"Target atom {pred}({', '.join(str(a) for a in args)}) is {label}. "
            "Detailed proof explanation is limited in this environment."
        ),
        "support": support,
        "raw": res,
    }
