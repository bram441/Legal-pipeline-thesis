"""Validate threshold numeric literals against scoped law text."""

from __future__ import annotations

from typing import Any

from pipeline.kb.json_ir import JSONIRCompilationError, RULE_DESIGN_TAG, _rule_expr_sides
from pipeline.kb.law_numeric_literals import (
    extract_numeric_values_from_law_text,
    format_law_numbers_for_message,
    is_logical_small_constant,
    numeric_value_matches_law,
    parse_numeric_token,
)


def _literal_to_float(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return float(raw)
    if isinstance(raw, float):
        return raw
    if isinstance(raw, str):
        return parse_numeric_token(raw)
    return None


def _iter_compare_nodes(expr: Any):
    if isinstance(expr, list):
        for x in expr:
            yield from _iter_compare_nodes(x)
        return
    if not isinstance(expr, dict):
        return
    if "pred" in expr or "symbol" in expr:
        return
    if "not" in expr:
        yield from _iter_compare_nodes(expr.get("not"))
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            yield from _iter_compare_nodes(x)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            yield from _iter_compare_nodes(x)
        return
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        yield comp


def _side_is_function_term(side: Any) -> bool:
    return isinstance(side, dict) and ("func" in side or "function" in side)


def collect_numeric_threshold_provenance_issues(
    ir: dict,
    *,
    law_text_for_lints: str | None,
) -> list[dict]:
    """Non-raising list of invented/out-of-law numeric thresholds in rules."""
    law_text = (law_text_for_lints or "").strip()
    if not law_text:
        return []
    law_values = extract_numeric_values_from_law_text(law_text)
    if not law_values:
        return []

    issues: list[dict] = []
    for idx, raw_rule in enumerate(ir.get("rules") or []):
        if not isinstance(raw_rule, dict):
            continue
        if_side, _ = _rule_expr_sides(raw_rule)
        for path, comp in _enumerate_compares(if_side, idx, "if"):
            issue = _check_compare_literal_issue(comp, law_values, path)
            if issue:
                issues.append(issue)
        if "formula" in raw_rule:
            for path, comp in _enumerate_compares(raw_rule.get("formula"), idx, "formula"):
                issue = _check_compare_literal_issue(comp, law_values, path)
                if issue:
                    issues.append(issue)
    return issues


def validate_numeric_threshold_literals_in_rules(
    ir: dict,
    *,
    law_text_for_lints: str | None,
) -> None:
    """
    Threshold compares against numeric literals must use values from scoped law text.
    """
    issues = collect_numeric_threshold_provenance_issues(
        ir, law_text_for_lints=law_text_for_lints
    )
    if issues:
        first = issues[0]
        raise JSONIRCompilationError(
            RULE_DESIGN_TAG
            + ": Rule %s uses numeric threshold %s, but this number does not appear in the scoped law text. "
            "Do not invent or alter legal thresholds during repair. Use one of the law-text thresholds: %s. "
            "Repair layer: rules."
            % (
                first["path"],
                first["threshold"],
                format_law_numbers_for_message(set(first.get("law_values") or [])),
            )
        )


def _enumerate_compares(expr: Any, rule_index: int, side: str):
    stack: list[tuple[Any, str]] = [(expr, side)]
    while stack:
        cur, path = stack.pop()
        if isinstance(cur, list):
            for j, x in enumerate(cur):
                stack.append((x, "%s[%d]" % (path, j)))
            continue
        if not isinstance(cur, dict):
            continue
        if "not" in cur:
            stack.append((cur.get("not"), path + ".not"))
            continue
        if "and" in cur:
            for j, x in enumerate(cur.get("and") or []):
                stack.append((x, "%s.and[%d]" % (path, j)))
            continue
        if "or" in cur:
            for j, x in enumerate(cur.get("or") or []):
                stack.append((x, "%s.or[%d]" % (path, j)))
            continue
        comp = cur.get("compare") if "compare" in cur else cur if {"left", "op", "right"}.issubset(cur.keys()) else None
        if isinstance(comp, dict):
            yield ("rules[%d].%s" % (rule_index, path), comp)


def _check_compare_literal_issue(
    comp: dict, law_values: set[float], path: str
) -> dict | None:
    left = comp.get("left")
    right = comp.get("right")
    for _side_name, side, literal in (
        ("left", left, right),
        ("right", right, left),
    ):
        if not _side_is_function_term(side):
            continue
        val = _literal_to_float(literal)
        if val is None:
            continue
        if is_logical_small_constant(val):
            continue
        if numeric_value_matches_law(val, law_values):
            continue
        shown = int(val) if val == int(val) else val
        return {
            "path": path,
            "threshold": shown,
            "law_values": sorted(law_values),
        }
    return None
