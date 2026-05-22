"""Diagnostics: which rule antecedents are present/missing for a Boolean derived query."""

from __future__ import annotations

import re
from typing import Any

from pipeline.kb.json_ir import (
    _collect_helper_symbol_usage,
    _iter_pred_atoms_with_args,
    _rule_expr_sides,
)

_atom_line = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_neg_atom_line = re.compile(r"^\s*(?:not|~|¬)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_bool_assign_line = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*=\s*(true|false)\s*\.\s*$",
    re.IGNORECASE,
)


def _norm(s: str) -> str:
    return str(s or "").strip().lower()


def _split_fact_args(blob: str) -> list[str]:
    return [_norm(p.strip()) for p in blob.split(",") if p.strip()]


def _index_case_facts(facts: list) -> tuple[set[tuple[str, tuple[str, ...]]], set[tuple[str, tuple[str, ...]]]]:
    pos: set[tuple[str, tuple[str, ...]]] = set()
    neg: set[tuple[str, tuple[str, ...]]] = set()
    for ln in facts or []:
        if not isinstance(ln, str):
            continue
        s = ln.strip()
        if not s.endswith("."):
            continue
        mneg = _neg_atom_line.match(s)
        if mneg:
            neg.add((_norm(mneg.group(1)), tuple(_split_fact_args(mneg.group(2)))))
            continue
        mb = _bool_assign_line.match(s)
        if mb:
            key = (_norm(mb.group(1)), tuple(_split_fact_args(mb.group(2))))
            if mb.group(3).strip().lower() == "true":
                pos.add(key)
            else:
                neg.add(key)
            continue
        m = _atom_line.match(s)
        if m:
            pos.add((_norm(m.group(1)), tuple(_split_fact_args(m.group(2)))))
    return pos, neg


def _term_var_name(term: Any) -> str | None:
    if isinstance(term, dict) and term.get("var"):
        return str(term["var"]).strip()
    if isinstance(term, str) and term.strip():
        t = term.strip()
        if t and not t[0].isdigit() and t.lower() not in ("true", "false"):
            return t
    return None


def _is_case_constant(term: Any, quant_vars: set[str]) -> bool:
    if isinstance(term, str):
        t = term.strip()
        return bool(t) and t not in quant_vars
    return False


def _resolve_term(term: Any, binding: dict[str, str], quant_vars: set[str]) -> str | None:
    if isinstance(term, dict) and term.get("var"):
        v = str(term["var"]).strip()
        if v in quant_vars:
            return binding.get(v)
        return binding.get(v, _norm(v))
    if isinstance(term, str):
        t = term.strip()
        if t in binding:
            return binding[t]
        if t in quant_vars:
            return binding.get(t)
        return _norm(t)
    return None


def _collect_rule_atoms(rule: dict) -> list[tuple[str, list]]:
    atoms: list[tuple[str, list]] = []
    if_side, then_side = _rule_expr_sides(rule)
    for side in (if_side, then_side):
        for atom in _iter_pred_atoms_with_args(side):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if pn:
                atoms.append((pn, list(atom.get("args") or [])))
    return atoms


def _extend_binding_from_case_facts(
    binding: dict[str, str],
    rule_atoms: list[tuple[str, list]],
    pos_facts: set[tuple[str, tuple[str, ...]]],
    quant_vars: set[str],
) -> dict[str, str]:
    """Unify quantified variables with case facts that match rule atom patterns."""
    out = dict(binding)
    max_rounds = len(quant_vars) + len(rule_atoms) + 2
    for _ in range(max_rounds):
        changed = False
        for pred, arg_terms in rule_atoms:
            pred_n = _norm(pred)
            arity = len(arg_terms)
            for fpred, fargs in pos_facts:
                if fpred != pred_n or len(fargs) != arity:
                    continue
                candidate = dict(out)
                ok = True
                for term, fact_arg in zip(arg_terms, fargs):
                    vn = _term_var_name(term)
                    if vn and vn in quant_vars:
                        prev = candidate.get(vn)
                        if prev is not None and prev != fact_arg:
                            ok = False
                            break
                        candidate[vn] = fact_arg
                    elif _is_case_constant(term, quant_vars):
                        if _norm(str(term).strip()) != fact_arg:
                            ok = False
                            break
                    else:
                        resolved = _resolve_term(term, candidate, quant_vars)
                        if resolved is not None and resolved != fact_arg:
                            ok = False
                            break
                if ok and candidate != out:
                    out = candidate
                    changed = True
        if not changed:
            break
    return out


def _bind_query_to_rule(query_pred: str, query_args: list[str], rule: dict) -> dict[str, str] | None:
    qpred = _norm(query_pred)
    qargs = [_norm(a) for a in query_args]
    forall = rule.get("forall") or []
    quant_vars = {str(q.get("var")).strip() for q in forall if isinstance(q, dict) and q.get("var")}

    _, then_side = _rule_expr_sides(rule)
    for atom in _iter_pred_atoms_with_args(then_side):
        pn = _norm(atom.get("pred") or atom.get("symbol") or "")
        if pn != qpred:
            continue
        rule_args = atom.get("args") or []
        if len(rule_args) != len(qargs):
            continue
        binding: dict[str, str] = {}
        ok = True
        for ra, qa in zip(rule_args, qargs):
            vn = _term_var_name(ra)
            if vn and vn in quant_vars:
                binding[vn] = qa
                continue
            resolved = _resolve_term(ra, {}, quant_vars)
            if resolved is None:
                ok = False
                break
            if resolved != qa:
                ok = False
                break
        if ok:
            return binding
    return None


def _atom_display(pred: str, args: list[str]) -> str:
    return pred + "(" + ",".join(args) + ")"


def _predicate_kinds_from_schema(kb_schema: dict | None) -> dict[str, str]:
    kinds: dict[str, str] = {}
    if not isinstance(kb_schema, dict):
        return kinds
    for p in kb_schema.get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            kinds[str(p["name"])] = str(p.get("kind") or "unknown").strip().lower()
    return kinds


def _query_target(query: dict) -> tuple[str | None, list[str]]:
    qtype = str(query.get("type") or "").strip().lower()
    if qtype == "predicate":
        return str(query.get("predicate") or "").strip() or None, list(query.get("args") or [])
    if qtype == "intent":
        pred = query.get("predicate")
        args = query.get("args")
        if pred:
            return str(pred).strip() or None, list(args or [])
        target = query.get("target") if isinstance(query.get("target"), dict) else {}
        return str(target.get("predicate") or "").strip() or None, list(target.get("args") or [])
    return None, []


def _rule_has_blocking_missing(conditions: list[dict]) -> bool:
    return any(c.get("status") == "missing" for c in conditions)


def _mark_non_blocking_alternative_rules(coverage: list[dict]) -> None:
    """If one rule path has all antecedents satisfied, missing facts on other rules are non-blocking."""
    satisfying = [
        block
        for block in coverage
        if block.get("conditions") and not _rule_has_blocking_missing(block["conditions"])
    ]
    if not satisfying:
        return
    sat_indices = {block.get("rule_index") for block in satisfying}
    for block in coverage:
        if block.get("rule_index") in sat_indices:
            continue
        for cond in block.get("conditions") or []:
            st = cond.get("status")
            if st == "missing":
                cond["status"] = "missing_non_blocking"
            elif st == "helper_floating":
                cond["status"] = "helper_floating_non_blocking"


def compute_antecedent_coverage(
    case: dict,
    query: dict,
    kb_schema: dict | None,
    symbolic_result: dict | None = None,
) -> list[dict]:
    """Return per-rule antecedent coverage for Boolean queries on derived predicates."""
    if not kb_schema or not isinstance(case, dict):
        return []

    pred, args = _query_target(query)
    if not pred or not args:
        return []

    pred_kinds = _predicate_kinds_from_schema(kb_schema)
    pk = pred_kinds.get(pred)
    if pk not in ("derived", "conclusion"):
        return []

    rules = kb_schema.get("rules") or []
    if not rules:
        return []

    fun_kinds: dict[str, str] = {}
    for f in kb_schema.get("functions") or []:
        if isinstance(f, dict) and f.get("name"):
            fun_kinds[str(f["name"])] = str(f.get("kind") or "unknown").strip().lower()

    _, _, def_then_p, _ = _collect_helper_symbol_usage(rules, pred_kinds, fun_kinds)
    pos_facts, neg_facts = _index_case_facts(case.get("facts") or [])

    out: list[dict] = []
    for idx, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        forall = rule.get("forall") or []
        quant_vars = {str(q.get("var")).strip() for q in forall if isinstance(q, dict) and q.get("var")}
        binding = _bind_query_to_rule(pred, args, rule)
        if not binding:
            continue

        rule_atoms = _collect_rule_atoms(rule)
        binding = _extend_binding_from_case_facts(binding, rule_atoms, pos_facts, quant_vars)

        if_side, _ = _rule_expr_sides(rule)
        conditions: list[dict] = []
        for atom in _iter_pred_atoms_with_args(if_side):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if not pn:
                continue
            resolved: list[str] = []
            for a in atom.get("args") or []:
                r = _resolve_term(a, binding, quant_vars)
                if r is None:
                    resolved = []
                    break
                resolved.append(r)
            if not resolved:
                conditions.append({"atom": pn, "status": "unknown"})
                continue

            key = (_norm(pn), tuple(resolved))
            display = _atom_display(pn, resolved)
            kind = pred_kinds.get(pn, "unknown")

            if key in pos_facts or key in neg_facts:
                status = "present"
            elif kind == "observable":
                status = "missing"
            elif kind == "helper":
                status = "helper_defined" if pn in def_then_p else "helper_floating"
            else:
                status = "unknown"

            conditions.append({"atom": display, "status": status})

        out.append(
            {
                "rule_index": idx,
                "target": _atom_display(pred, [_norm(a) for a in args]),
                "conditions": conditions,
            }
        )

    if symbolic_result and isinstance(symbolic_result, dict):
        label = str(symbolic_result.get("label") or "").lower()
        proved = label == "entailed" or symbolic_result.get("certain") is True
        if proved:
            _mark_non_blocking_alternative_rules(out)
    return out


def missing_observable_symbols(coverage: list[dict]) -> list[str]:
    missing: list[str] = []
    for block in coverage or []:
        for cond in block.get("conditions") or []:
            if cond.get("status") == "missing":
                atom = str(cond.get("atom") or "")
                pred = atom.split("(", 1)[0].strip()
                if pred and pred not in missing:
                    missing.append(pred)
    return missing


def format_missing_observable_feedback(missing_preds: list[str], kb_schema: dict | None) -> str:
    if not missing_preds:
        return ""
    descs: list[str] = []
    schema_preds = {
        str(p.get("name")): str(p.get("description") or "").strip()
        for p in (kb_schema or {}).get("predicates") or []
        if isinstance(p, dict) and p.get("name")
    }
    for name in missing_preds:
        d = schema_preds.get(name, "")
        descs.append(name + (": " + d if d else ""))
    symbols = "; ".join(descs)
    return (
        "The selected legal conclusion could not be proven because an observable antecedent "
        "required by the KB rule was not asserted from the case. Re-check the case text for facts "
        "matching these observable schema symbols: " + symbols + "."
    )
