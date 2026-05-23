"""Require exclusion/negative rules for threshold-based legal classifications."""

from __future__ import annotations

from pipeline.kb.json_ir import (
    JSONIRCompilationError,
    RULE_DESIGN_TAG,
    _collect_pred_atom_usages,
    _rule_expr_sides,
)
from pipeline.kb.json_ir import _DERIVED_OUTPUT_KINDS
from pipeline.kb.law_numeric_literals import extract_numeric_values_from_law_text, is_logical_small_constant
from pipeline.kb.numeric_threshold_provenance import _iter_compare_nodes, _literal_to_float, _side_is_function_term
from pipeline.kb.threshold_cardinality import (
    _AT_LEAST_TWO_PRED_RE,
    _is_negated_simple_or_of_thresholds,
    _rule_has_favorable_derived_then,
    law_text_has_at_most_one_criterion_language,
)


def _rules_have_numeric_threshold_comparisons(rules: list) -> bool:
    """IF compares an observable/function to a non-cardinality numeric literal."""
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            continue
        if_side, _ = _rule_expr_sides(raw_rule)
        for comp in _iter_compare_nodes(if_side):
            left = comp.get("left")
            right = comp.get("right")
            for side, literal in ((left, right), (right, left)):
                if not _side_is_function_term(side):
                    continue
                val = _literal_to_float(literal)
                if val is None or is_logical_small_constant(val):
                    continue
                return True
    return False


def _law_has_explicit_numeric_thresholds(law_text: str) -> bool:
    values = extract_numeric_values_from_law_text(law_text)
    return any(v >= 100 for v in values)


def _positive_classification_preds_in_then(rules: list, pred_kinds: dict[str, str]) -> set[str]:
    names: set[str] = set()
    for u in _collect_pred_atom_usages(rules):
        if u.side != "then" or u.negated:
            continue
        if pred_kinds.get(u.name, "") in _DERIVED_OUTPUT_KINDS:
            names.add(u.name)
    return names


def _has_negated_classification_in_then(rules: list, classification: str) -> bool:
    for u in _collect_pred_atom_usages(rules):
        if u.side == "then" and u.negated and u.name == classification:
            return True
    return False


def _if_has_negated_pairwise_threshold_structure(expr) -> bool:
    """IF uses NOT (OR of multi-threshold AND groups) — encodes at-most-one qualification."""
    if isinstance(expr, list):
        return any(_if_has_negated_pairwise_threshold_structure(x) for x in expr)
    if not isinstance(expr, dict):
        return False
    if _is_negated_simple_or_of_thresholds(expr):
        return True
    if "not" in expr:
        inner = expr.get("not")
        if isinstance(inner, dict) and "or" in inner:
            or_children = inner.get("or") or []
            if len(or_children) >= 2:
                and_pairs = sum(
                    1
                    for c in or_children
                    if isinstance(c, dict) and "and" in c and len(c.get("and") or []) >= 2
                )
                if and_pairs >= 2:
                    return True
        return _if_has_negated_pairwise_threshold_structure(inner)
    if "and" in expr:
        return any(_if_has_negated_pairwise_threshold_structure(x) for x in (expr.get("and") or []))
    if "or" in expr:
        return any(_if_has_negated_pairwise_threshold_structure(x) for x in (expr.get("or") or []))
    return False


def _if_uses_at_least_two_helper(expr) -> bool:
    if isinstance(expr, list):
        return any(_if_uses_at_least_two_helper(x) for x in expr)
    if not isinstance(expr, dict):
        return False
    if "pred" in expr or "symbol" in expr:
        name = str(expr.get("pred") or expr.get("symbol") or "")
        return bool(_AT_LEAST_TWO_PRED_RE.search(name))
    if "not" in expr:
        return _if_uses_at_least_two_helper(expr.get("not"))
    if "and" in expr:
        return any(_if_uses_at_least_two_helper(x) for x in (expr.get("and") or []))
    if "or" in expr:
        return any(_if_uses_at_least_two_helper(x) for x in (expr.get("or") or []))
    return False


def _disqualification_semantics_present(rules: list, classification_preds: set[str]) -> bool:
    for name in classification_preds:
        if _has_negated_classification_in_then(rules, name):
            return True
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            continue
        if_side, _ = _rule_expr_sides(raw_rule)
        if _if_has_negated_pairwise_threshold_structure(if_side):
            return True
        if _if_uses_at_least_two_helper(if_side):
            return True
    return False


def validate_threshold_classification_negative_support(
    ir: dict,
    pred_kinds: dict[str, str],
    *,
    law_text_for_lints: str | None,
) -> None:
    """
    When law text defines at-most-one threshold classification, the KB must support false answers:
    add an exclusion rule such as at_least_two_exceeded => not classification.
    """
    law_text = (law_text_for_lints or "").strip()
    if not law_text or not law_text_has_at_most_one_criterion_language(law_text):
        return

    rules = ir.get("rules") or []
    if not _rules_have_numeric_threshold_comparisons(rules) and not _law_has_explicit_numeric_thresholds(
        law_text
    ):
        return
    positive = _positive_classification_preds_in_then(rules, pred_kinds)
    if not positive:
        return

    has_favorable = any(
        isinstance(r, dict) and _rule_has_favorable_derived_then(r, pred_kinds) for r in rules
    )
    if not has_favorable:
        return

    if _disqualification_semantics_present(rules, positive):
        return

    missing = [p for p in sorted(positive) if not _has_negated_classification_in_then(rules, p)]
    if not missing:
        return

    preds = ", ".join(missing[:3])
    raise JSONIRCompilationError(
        RULE_DESIGN_TAG
        + ": This law defines a classification by threshold criteria (not more than one criterion exceeded). "
        "The rule set can prove favorable cases but cannot prove disqualification. "
        "To answer false cases, add an exclusion rule such as "
        "at_least_two_exceeded => not %s (negated predicate in THEN), or an equivalent disqualifying rule. "
        "Do not rely on absence of proof for a negative legal answer. "
        "Affected classification predicate(s): %s. Repair layer: rules."
        % (missing[0], preds)
    )
