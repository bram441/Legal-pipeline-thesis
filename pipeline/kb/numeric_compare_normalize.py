"""Deterministic Int/Real literal coercion for JSON_IR compare nodes."""

from __future__ import annotations

import re
from typing import Any

from pipeline.kb.json_ir import (
    SymbolDecl,
    _infer_term_type,
    _normalize_quant_entry,
    _rule_expr_sides,
)


def _coerce_literal_for_sort(raw: Any, target_sort: str) -> Any:
    if target_sort == "Real":
        if isinstance(raw, int):
            return float(raw)
        if isinstance(raw, str) and re.fullmatch(r"\d+", raw.strip()):
            return float(int(raw.strip()))
        if isinstance(raw, str) and re.fullmatch(r"\d+\.0+", raw.strip()):
            return float(raw.strip())
    if target_sort == "Int":
        if isinstance(raw, float) and raw == int(raw):
            return int(raw)
        if isinstance(raw, str):
            s = raw.strip()
            if re.fullmatch(r"\d+", s):
                return int(s)
            if re.fullmatch(r"\d+\.0+", s):
                f = float(s)
                if f == int(f):
                    return int(f)
    return raw


def _normalize_compare_node(
    comp: dict,
    *,
    rule_index: int,
    symbols: dict[str, tuple[tuple[str, ...], str]],
    env: dict[str, str],
    path: str,
) -> None:
    left = comp.get("left")
    right = comp.get("right")
    try:
        lt = _infer_term_type(left, rule_index, symbols, env, path + ".left")
        rt = _infer_term_type(right, rule_index, symbols, env, path + ".right")
    except Exception:
        return
    if lt in {"Int", "Real"} and rt in {"Int", "Real"} and lt != rt:
        if lt == "Real":
            comp["right"] = _coerce_literal_for_sort(right, "Real")
            rt = _infer_term_type(comp.get("right"), rule_index, symbols, env, path + ".right")
        if rt == "Real" and lt == "Int":
            comp["left"] = _coerce_literal_for_sort(left, "Real")
            lt = _infer_term_type(comp.get("left"), rule_index, symbols, env, path + ".left")
        if lt == "Int" and rt == "Real":
            comp["right"] = _coerce_literal_for_sort(right, "Int")
        elif lt == "Real" and rt == "Int":
            comp["right"] = _coerce_literal_for_sort(right, "Real")


def _walk_expr_normalize_compares(
    expr: Any,
    *,
    rule_index: int,
    symbols: dict[str, tuple[tuple[str, ...], str]],
    env: dict[str, str],
    path: str,
) -> None:
    if isinstance(expr, list):
        for j, x in enumerate(expr):
            _walk_expr_normalize_compares(
                x, rule_index=rule_index, symbols=symbols, env=env, path="%s[%d]" % (path, j)
            )
        return
    if not isinstance(expr, dict):
        return
    if "not" in expr:
        _walk_expr_normalize_compares(
            expr.get("not"),
            rule_index=rule_index,
            symbols=symbols,
            env=env,
            path=path + ".not",
        )
        return
    if "and" in expr:
        for j, x in enumerate(expr.get("and") or []):
            _walk_expr_normalize_compares(
                x,
                rule_index=rule_index,
                symbols=symbols,
                env=env,
                path=path + ".and[%d]" % j,
            )
        return
    if "or" in expr:
        for j, x in enumerate(expr.get("or") or []):
            _walk_expr_normalize_compares(
                x,
                rule_index=rule_index,
                symbols=symbols,
                env=env,
                path=path + ".or[%d]" % j,
            )
        return
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        _normalize_compare_node(comp, rule_index=rule_index, symbols=symbols, env=env, path=path)


def normalize_json_ir_rule_compare_sorts(
    ir: dict,
    predicates: list[SymbolDecl],
    functions: list[SymbolDecl],
) -> None:
    """Mutate rule compare literals so Int/Real sides match (in-place)."""
    seen: dict[str, tuple[tuple[str, ...], str]] = {}
    for decl in predicates + functions:
        seen[decl.name] = (tuple(decl.args), decl.returns)

    for idx, raw_rule in enumerate(ir.get("rules") or []):
        if not isinstance(raw_rule, dict):
            continue
        q_raw = raw_rule.get("forall", [])
        if not isinstance(q_raw, list):
            continue
        env = {v: t for v, t in (_normalize_quant_entry(q, idx) for q in q_raw)}
        if "formula" in raw_rule:
            _walk_expr_normalize_compares(
                raw_rule.get("formula"),
                rule_index=idx,
                symbols=seen,
                env=env,
                path="formula",
            )
            continue
        if_side, then_side = _rule_expr_sides(raw_rule)
        _walk_expr_normalize_compares(
            if_side, rule_index=idx, symbols=seen, env=env, path="if"
        )
        _walk_expr_normalize_compares(
            then_side, rule_index=idx, symbols=seen, env=env, path="then"
        )
