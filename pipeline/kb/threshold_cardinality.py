"""
Detect unsafe encoding of 'not more than one criterion exceeded' threshold logic in JSON_IR rules.

Law-agnostic: uses law-text phrases and rule-structure patterns only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# English / Dutch phrases indicating at-most-one / more-than-one criterion cardinality.
_AT_MOST_ONE_CRITERION_PHRASES: tuple[str, ...] = (
    "not more than one",
    "no more than one",
    "at most one",
    "more than one criterion",
    "more than one criteria",
    "more than one of the following criteria",
    "more than one of the following criterion",
    "two or more criteria",
    "two or more criterion",
    "at least two criteria",
    "at least two criterion",
    "exceeded for the second time",
    "one of the following criteria",
    "one of the following criterion",
    "criteria are exceeded",
    "criteria is exceeded",
    "niet meer dan één",
    "niet meer dan een",
    "meer dan één",
    "meer dan een",
    "hoogstens één",
    "minstens twee",
    "twee of meer",
    "criteria overschrijden",
    "criteria worden overschreden",
    "één van de volgende criteria",
    "een van de volgende criteria",
    "één der volgende criteria",
    "een der volgende criteria",
)

# Disambiguate: "one of the following" alone can mean any-one-sufficient provisions.
_AT_MOST_ONE_STRONG_PHRASES: tuple[str, ...] = (
    "not more than one",
    "no more than one",
    "at most one",
    "more than one criterion",
    "more than one criteria",
    "more than one of the",
    "niet meer dan één",
    "niet meer dan een",
    "meer dan één",
    "meer dan een",
    "hoogstens één",
    "minstens twee",
    "twee of meer",
    "criteria overschrijden",
    "criteria worden overschreden",
)

_ANY_ONE_SUFFICIENT_PHRASES: tuple[str, ...] = (
    "if any of the following",
    "when any of the following",
    "any of the following conditions is sufficient",
    "any one of the following conditions",
    "sufficient if any",
    "indien een van de volgende voorwaarden",
    "wanneer een van de volgende voorwaarden",
)

_EXCEEDED_OPS = frozenset({">", ">="})
_WITHIN_OPS = frozenset({"<", "<=", "=<"})

_AT_LEAST_TWO_PRED_RE = re.compile(
    r"(?i)(at_least_two|two_or_more|more_than_one|meer_dan_een|minstens_twee|"
    r"at_least_2|two_criteria|multiple_criteria_exceeded)"
)


@dataclass(frozen=True)
class ThresholdCompare:
    func_name: str
    op: str
    is_exceeded: bool
    is_within: bool


def _norm_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def law_text_has_at_most_one_criterion_language(law_text: str | None) -> bool:
    """True when scoped/full law text mentions at-most-one / more-than-one criterion logic."""
    tl = _norm_text(law_text or "")
    if not tl:
        return False
    if any(p in tl for p in _AT_MOST_ONE_STRONG_PHRASES):
        return True
    if any(p in tl for p in _AT_MOST_ONE_CRITERION_PHRASES):
        # Require cardinality cue together with criterion/threshold wording.
        if "criteri" in tl or "threshold" in tl or "drempel" in tl or "overschrij" in tl:
            return True
    return False


def law_text_has_any_one_sufficient_language(law_text: str | None) -> bool:
    """True when law text clearly allows 'any one condition is enough' (exempt simple OR)."""
    if law_text_has_at_most_one_criterion_language(law_text):
        return False
    tl = _norm_text(law_text or "")
    return any(p in tl for p in _ANY_ONE_SUFFICIENT_PHRASES)


def _normalize_compare_op(op: str) -> str:
    o = str(op or "").strip()
    if o == "=<":
        return "<="
    return o


def _is_numeric_literal(raw: Any) -> bool:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return True
    if isinstance(raw, str):
        s = raw.strip()
        return bool(re.match(r"^-?\d+(?:\.\d+)?$", s))
    return False


def _extract_threshold_compare(expr: Any) -> ThresholdCompare | None:
    if not isinstance(expr, dict):
        return None
    comp = None
    if "compare" in expr:
        comp = expr.get("compare")
    elif {"left", "op", "right"}.issubset(expr.keys()):
        comp = expr
    if not isinstance(comp, dict):
        return None

    left, right = comp.get("left"), comp.get("right")
    op = _normalize_compare_op(comp.get("op"))

    func_name = None
    if isinstance(left, dict) and ("func" in left or "function" in left):
        func_name = str(left.get("func") or left.get("function") or "").strip()
        if _is_numeric_literal(right):
            pass
        else:
            return None
    elif isinstance(right, dict) and ("func" in right or "function" in right):
        func_name = str(right.get("func") or right.get("function") or "").strip()
        if _is_numeric_literal(left):
            if op in _EXCEEDED_OPS:
                op = {"<": ">", "<=": ">="}.get(op, op)
            elif op in _WITHIN_OPS:
                op = {">": "<", ">=": "<="}.get(op, op)
        else:
            return None
    else:
        return None

    if not func_name:
        return None
    is_exceeded = op in _EXCEEDED_OPS
    is_within = op in _WITHIN_OPS
    if not is_exceeded and not is_within:
        return None
    return ThresholdCompare(func_name=func_name, op=op, is_exceeded=is_exceeded, is_within=is_within)


def _is_single_threshold_compare(expr: Any) -> bool:
    return _extract_threshold_compare(expr) is not None


def _compare_kind(expr: Any) -> str | None:
    tc = _extract_threshold_compare(expr)
    if not tc:
        return None
    if tc.is_exceeded:
        return "exceeded"
    if tc.is_within:
        return "within"
    return None


def _is_pairwise_or_of_thresholds(expr: Any, *, kind: str | None = None) -> bool:
    """OR of AND nodes, each AND containing >=2 threshold compares (optionally same kind)."""
    if not isinstance(expr, dict) or "or" not in expr:
        return False
    children = expr.get("or") or []
    if len(children) < 2:
        return False
    for child in children:
        if not isinstance(child, dict) or "and" not in child:
            return False
        and_children = child.get("and") or []
        matches = 0
        for ac in and_children:
            ck = _compare_kind(ac)
            if ck is None:
                continue
            if kind is not None and ck != kind:
                continue
            matches += 1
        if matches < 2:
            return False
    return True


def _is_negated_simple_or_of_thresholds(expr: Any) -> bool:
    """
    Safe pattern: NOT (cmp1 OR cmp2 OR cmp3) — negated disjunction of single threshold compares.
    """
    if not isinstance(expr, dict) or "not" not in expr:
        return False
    inner = expr.get("not")
    if not isinstance(inner, dict) or "or" not in inner:
        return False
    children = inner.get("or") or []
    if len(children) < 2:
        return False
    return all(_is_single_threshold_compare(c) for c in children)


def _is_unsafe_simple_or_of_thresholds(expr: Any, *, kind: str) -> bool:
    """OR with >=2 disjuncts, each a single threshold compare of the given kind."""
    if not isinstance(expr, dict) or "or" not in expr:
        return False
    children = expr.get("or") or []
    if len(children) < 2:
        return False
    for child in children:
        if _compare_kind(child) != kind:
            return False
    return True


def _expr_uses_at_least_two_helper(expr: Any) -> bool:
    """True if antecedent negates or uses a helper named like at_least_two_exceeded."""
    if isinstance(expr, list):
        return any(_expr_uses_at_least_two_helper(x) for x in expr)
    if not isinstance(expr, dict):
        return False
    if "pred" in expr or "symbol" in expr:
        name = str(expr.get("pred") or expr.get("symbol") or "")
        if _AT_LEAST_TWO_PRED_RE.search(name):
            return True
    if "not" in expr:
        inner = expr.get("not")
        if isinstance(inner, dict) and ("pred" in inner or "symbol" in inner):
            name = str(inner.get("pred") or inner.get("symbol") or "")
            if _AT_LEAST_TWO_PRED_RE.search(name):
                return True
    if "and" in expr:
        return any(_expr_uses_at_least_two_helper(x) for x in (expr.get("and") or []))
    if "or" in expr:
        return any(_expr_uses_at_least_two_helper(x) for x in (expr.get("or") or []))
    return False


def _scan_unsafe_threshold_or(
    expr: Any,
    *,
    rule_index: int,
    path: str,
) -> str | None:
    """Return error detail if expr is an unsafe simple OR of threshold compares."""
    if _is_negated_simple_or_of_thresholds(expr):
        return None
    if _is_pairwise_or_of_thresholds(expr, kind="exceeded"):
        return None
    if _is_pairwise_or_of_thresholds(expr, kind="within"):
        return None
    if _expr_uses_at_least_two_helper(expr):
        return None

    if _is_unsafe_simple_or_of_thresholds(expr, kind="exceeded"):
        return (
            "rules[%d].%s uses OR over individual exceeded-threshold comparisons to support a "
            "favorable derived conclusion; one exceeded criterion is not enough when the law "
            "limits how many criteria may be exceeded."
            % (rule_index, path)
        )
    if _is_unsafe_simple_or_of_thresholds(expr, kind="within"):
        return (
            "rules[%d].%s uses OR over individual within-threshold comparisons to support a "
            "favorable derived conclusion; one within-threshold check is too weak when the law "
            "requires at least two criteria to stay within threshold (not more than one exceeded)."
            % (rule_index, path)
        )
    return None


def _walk_if_for_unsafe_or(
    expr: Any,
    *,
    rule_index: int,
    path: str,
    violations: list[str] | None = None,
) -> str | None:
    """Return first violation detail, or append all to violations when collect-all mode."""
    if isinstance(expr, list):
        for i, x in enumerate(expr):
            err = _walk_if_for_unsafe_or(
                x, rule_index=rule_index, path=path + "[%d]" % i, violations=violations
            )
            if err and violations is None:
                return err
        return None
    if not isinstance(expr, dict):
        return None

    err = _scan_unsafe_threshold_or(expr, rule_index=rule_index, path=path)
    if err:
        if violations is not None:
            violations.append(err)
        else:
            return err

    if "not" in expr:
        inner = expr.get("not")
        if _is_negated_simple_or_of_thresholds(expr):
            return None
        if _is_pairwise_or_of_thresholds(inner):
            return None
        sub = _walk_if_for_unsafe_or(
            inner, rule_index=rule_index, path=path + ".not", violations=violations
        )
        if sub and violations is None:
            return sub
        return None

    if "and" in expr:
        for i, x in enumerate(expr.get("and") or []):
            err = _walk_if_for_unsafe_or(
                x, rule_index=rule_index, path=path + ".and[%d]" % i, violations=violations
            )
            if err and violations is None:
                return err
        return None

    if "or" in expr:
        for i, x in enumerate(expr.get("or") or []):
            err = _walk_if_for_unsafe_or(
                x, rule_index=rule_index, path=path + ".or[%d]" % i, violations=violations
            )
            if err and violations is None:
                return err
        return None

    return None


def collect_threshold_cardinality_violations(
    ir: dict,
    pred_kinds: dict[str, str],
    *,
    law_text_for_lints: str | None,
) -> list[str]:
    """All cardinality violation messages (non-raising)."""
    if not law_text_for_lints or not law_text_has_at_most_one_criterion_language(law_text_for_lints):
        return []
    if law_text_has_any_one_sufficient_language(law_text_for_lints):
        return []

    out: list[str] = []
    for idx, raw_rule in enumerate(ir.get("rules") or []):
        if not isinstance(raw_rule, dict):
            continue
        if not _rule_has_favorable_derived_then(raw_rule, pred_kinds):
            continue
        if_side, _ = _rule_expr_sides(raw_rule)
        _walk_if_for_unsafe_or(if_side, rule_index=idx, path="if", violations=out)
    return out


_DERIVED_OUTPUT_KINDS = frozenset({"derived", "conclusion"})


def _rule_expr_sides(raw_rule: dict) -> tuple[Any, Any]:
    if_side = raw_rule.get("if", [])
    then_side = raw_rule.get("then", []) if "then" in raw_rule else raw_rule.get("formula")
    return if_side, then_side


def _rule_has_favorable_derived_then(raw_rule: dict, pred_kinds: dict[str, str]) -> bool:
    _, then_side = _rule_expr_sides(raw_rule)
    for atom in _iter_pred_atoms_simple(then_side):
        pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
        if pred_kinds.get(pn) in _DERIVED_OUTPUT_KINDS:
            return True
    return False


def _iter_pred_atoms_simple(expr: Any):
    """Lightweight atom iterator (duplicated minimal to avoid circular imports)."""
    if isinstance(expr, list):
        for x in expr:
            yield from _iter_pred_atoms_simple(x)
        return
    if not isinstance(expr, dict):
        return
    if "pred" in expr or "symbol" in expr:
        yield expr
        return
    if "not" in expr:
        yield from _iter_pred_atoms_simple(expr.get("not"))
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            yield from _iter_pred_atoms_simple(x)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            yield from _iter_pred_atoms_simple(x)
        return
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        for side in (comp.get("left"), comp.get("right")):
            yield from _iter_pred_atoms_simple(side)


def validate_threshold_cardinality_rules(
    ir: dict,
    pred_kinds: dict[str, str],
    law_text_for_lints: str | None,
) -> None:
    """
    Raise JSONIRCompilationError (via caller) when rules encode at-most-one criterion logic incorrectly.

    No-op when law_text_for_lints is absent or law lacks cardinality phrases, or law allows any-one-sufficient OR.
    """
    from pipeline.kb.json_ir import JSONIRCompilationError, RULE_DESIGN_TAG

    if not law_text_for_lints or not law_text_has_at_most_one_criterion_language(law_text_for_lints):
        return
    if law_text_has_any_one_sufficient_language(law_text_for_lints):
        return

    violations = collect_threshold_cardinality_violations(
        ir, pred_kinds, law_text_for_lints=law_text_for_lints
    )
    if violations:
        detail = violations[0]
        raise JSONIRCompilationError(
            RULE_DESIGN_TAG
            + ": "
            + detail
            + " The law text contains at-most-one / more-than-one criteria language. Do not encode "
            "this as a simple OR over individual threshold comparisons. Use pairwise combinations "
            "(A and B) or (A and C) or (B and C), or define a helper for at_least_two_exceeded and "
            "negate it for the favorable conclusion. Repair layer: rules."
        )
