"""Structural progress detection for threshold-cardinality repair stall logic."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from pipeline.kb.threshold_cardinality import (
    _DERIVED_OUTPUT_KINDS,
    _is_pairwise_or_of_thresholds,
    _is_unsafe_simple_or_of_thresholds,
    _rule_expr_sides,
    law_text_has_at_most_one_criterion_language,
)


@dataclass
class ThresholdRepairSnapshot:
    cardinality_violation_count: int = 0
    cardinality_paths: list[str] = field(default_factory=list)
    numeric_provenance_count: int = 0
    has_correct_pairwise_positive: bool = False
    has_exclusion_negated_then: bool = False
    has_malformed_exclusion_simple_or: bool = False
    rules_fingerprint: str = ""
    primary_error_path: str | None = None


@dataclass(frozen=True)
class ThresholdProgressVerdict:
    progress_detected: bool
    progress_reason: str
    previous_error_path: str | None
    current_error_path: str | None
    threshold_cardinality_violation_count: int


def rules_fingerprint(rules: list | None) -> str:
    if not rules:
        return ""
    payload = json.dumps(rules, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _then_has_negated_derived(then_side: Any, pred_kinds: dict[str, str]) -> bool:
    for atom in _iter_then_atoms(then_side):
        pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
        if pred_kinds.get(pn) in _DERIVED_OUTPUT_KINDS and atom.get("negated"):
            return True
    return False


def _then_has_non_negated_derived(then_side: Any, pred_kinds: dict[str, str]) -> bool:
    for atom in _iter_then_atoms(then_side):
        pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
        if pred_kinds.get(pn) in _DERIVED_OUTPUT_KINDS and not atom.get("negated"):
            return True
    return False


def _iter_then_atoms(expr: Any):
    if isinstance(expr, list):
        for x in expr:
            yield from _iter_then_atoms(x)
    elif isinstance(expr, dict):
        if "pred" in expr or "symbol" in expr:
            yield expr
        if "not" in expr:
            inner = expr.get("not")
            if isinstance(inner, dict) and ("pred" in inner or "symbol" in inner):
                yield {**inner, "negated": True}
        for k in ("and", "or"):
            if k in expr:
                for x in expr.get(k) or []:
                    yield from _iter_then_atoms(x)


def _if_has_correct_pairwise_positive(if_side: Any) -> bool:
    """NOT (OR of pairwise AND exceeded) or pairwise within OR for qualification."""
    if isinstance(if_side, list):
        return any(_if_has_correct_pairwise_positive(x) for x in if_side)
    if not isinstance(if_side, dict):
        return False
    if "not" in if_side:
        inner = if_side.get("not")
        if isinstance(inner, dict) and _is_pairwise_or_of_thresholds(inner, kind="exceeded"):
            return True
    if _is_pairwise_or_of_thresholds(if_side, kind="within"):
        return True
    if "and" in if_side:
        return any(_if_has_correct_pairwise_positive(x) for x in (if_side.get("and") or []))
    if "or" in if_side:
        return any(_if_has_correct_pairwise_positive(x) for x in (if_side.get("or") or []))
    return False


def _if_has_simple_or_exceeded(if_side: Any) -> bool:
    if isinstance(if_side, list):
        return any(_if_has_simple_or_exceeded(x) for x in if_side)
    if not isinstance(if_side, dict):
        return False
    if _is_unsafe_simple_or_of_thresholds(if_side, kind="exceeded"):
        return True
    if _is_unsafe_simple_or_of_thresholds(if_side, kind="within"):
        return True
    for k in ("and", "or", "not"):
        if k in if_side:
            v = if_side.get(k)
            if isinstance(v, list):
                if any(_if_has_simple_or_exceeded(x) for x in v):
                    return True
            elif _if_has_simple_or_exceeded(v):
                return True
    return False


def build_threshold_repair_snapshot(
    ir: dict,
    pred_kinds: dict[str, str],
    *,
    cardinality_violations: list[str],
    numeric_provenance_count: int,
    primary_error_path: str | None = None,
) -> ThresholdRepairSnapshot:
    rules = ir.get("rules") or []
    has_pos = False
    has_excl = False
    has_bad_excl = False

    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            continue
        if_side, then_side = _rule_expr_sides(raw_rule)
        if _then_has_non_negated_derived(then_side, pred_kinds):
            if _if_has_correct_pairwise_positive(if_side):
                has_pos = True
        if _then_has_negated_derived(then_side, pred_kinds):
            has_excl = True
            if _if_has_simple_or_exceeded(if_side):
                has_bad_excl = True

    paths = [_extract_path(v) for v in cardinality_violations]
    paths = [p for p in paths if p]
    return ThresholdRepairSnapshot(
        cardinality_violation_count=len(cardinality_violations),
        cardinality_paths=paths,
        numeric_provenance_count=numeric_provenance_count,
        has_correct_pairwise_positive=has_pos,
        has_exclusion_negated_then=has_excl,
        has_malformed_exclusion_simple_or=has_bad_excl,
        rules_fingerprint=rules_fingerprint(rules if isinstance(rules, list) else None),
        primary_error_path=primary_error_path or (paths[0] if paths else None),
    )


def _extract_path(message: str) -> str | None:
    m = re.search(r"(rules\[\d+\](?:\.[a-zA-Z0-9_\[\]]+)*)", message or "")
    return m.group(1) if m else None


def detect_threshold_cardinality_progress(
    previous: ThresholdRepairSnapshot | None,
    current: ThresholdRepairSnapshot,
) -> ThresholdProgressVerdict:
    """True when repair is visibly improving despite same normalized error code."""
    prev_path = previous.primary_error_path if previous else None
    cur_path = current.primary_error_path
    reasons: list[str] = []

    if previous is None:
        return ThresholdProgressVerdict(
            progress_detected=False,
            progress_reason="first_attempt",
            previous_error_path=None,
            current_error_path=cur_path,
            threshold_cardinality_violation_count=current.cardinality_violation_count,
        )

    if previous.rules_fingerprint and current.rules_fingerprint == previous.rules_fingerprint:
        return ThresholdProgressVerdict(
            progress_detected=False,
            progress_reason="identical_rules_output",
            previous_error_path=prev_path,
            current_error_path=cur_path,
            threshold_cardinality_violation_count=current.cardinality_violation_count,
        )

    if current.cardinality_violation_count < previous.cardinality_violation_count:
        reasons.append("cardinality_violation_count_decreased")

    if set(current.cardinality_paths) != set(previous.cardinality_paths):
        reasons.append("failing_rule_path_changed")

    if current.has_correct_pairwise_positive and not previous.has_correct_pairwise_positive:
        reasons.append("correct_pairwise_positive_rule_appeared")

    if current.has_exclusion_negated_then and not previous.has_exclusion_negated_then:
        reasons.append("exclusion_negated_then_appeared")

    if current.numeric_provenance_count < previous.numeric_provenance_count:
        reasons.append("numeric_provenance_issues_decreased")

    if previous.has_malformed_exclusion_simple_or and not current.has_malformed_exclusion_simple_or:
        reasons.append("malformed_exclusion_simple_or_fixed")

    progress = bool(reasons)
    return ThresholdProgressVerdict(
        progress_detected=progress,
        progress_reason="; ".join(reasons) if reasons else "no_structural_progress",
        previous_error_path=prev_path,
        current_error_path=cur_path,
        threshold_cardinality_violation_count=current.cardinality_violation_count,
    )


def should_stall_threshold_cardinality_repeat(
    *,
    signature_repeat_count: int,
    repeated_error_limit: int,
    progress: ThresholdProgressVerdict,
    rules_attempt: int,
    max_rules_attempts: int,
) -> bool:
    """
    Stall on repeated threshold_cardinality signature only when no progress and budget logic says stop.
    """
    if signature_repeat_count < repeated_error_limit:
        return False
    if progress.progress_detected and rules_attempt < max_rules_attempts:
        return False
    return True
