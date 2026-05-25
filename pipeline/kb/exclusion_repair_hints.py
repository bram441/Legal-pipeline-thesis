"""Targeted repair prompt supplement for missing threshold classification exclusion."""

from __future__ import annotations

import re

from pipeline.kb.law_numeric_literals import (
    extract_numeric_values_from_law_text,
    format_law_numbers_for_message,
)

_RE_AFFECTED_PREDS = re.compile(
    r"Affected classification predicate\(s\):\s*([^\n.]+)",
    re.IGNORECASE,
)
_RE_SUGGESTED_PRED = re.compile(
    r"at_least_two_exceeded\s*=>\s*not\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

_PAIRWISE_EXCLUSION_TEMPLATE = (
    "((A_exceeded AND B_exceeded) OR (A_exceeded AND C_exceeded) OR (B_exceeded AND C_exceeded)) "
    "=> NOT classification (use negated: true on the classification predicate in THEN)"
)


def extract_classification_predicates(error_message: str) -> list[str]:
    """Parse affected classification predicate name(s) from the validation error."""
    msg = error_message or ""
    m = _RE_AFFECTED_PREDS.search(msg)
    if m:
        raw = m.group(1).strip()
        return [p.strip() for p in raw.split(",") if p.strip()]
    m2 = _RE_SUGGESTED_PRED.search(msg)
    if m2:
        return [m2.group(1)]
    return []


def format_law_thresholds_for_repair(law_text: str | None) -> str:
    values = extract_numeric_values_from_law_text(law_text)
    if not values:
        return "(none extracted from scoped law text)"
    return format_law_numbers_for_message(values)


def build_missing_exclusion_repair_supplement(
    error_message: str,
    *,
    law_text: str | None = None,
    secondary_diagnostics: str = "",
    symbol_table: dict | None = None,
    merged_ir: dict | None = None,
    query_predicate: str | None = None,
) -> str:
    """
    Extra rules-repair guidance when the KB lacks disqualification/exclusion rules.
    """
    from pipeline.kb.threshold_exclusion_scaffold import build_threshold_exclusion_repair_scaffold

    scaffold = build_threshold_exclusion_repair_scaffold(
        symbol_table,
        merged_ir,
        error_message=error_message,
        law_text=law_text,
        query_predicate=query_predicate,
    )
    preds = extract_classification_predicates(error_message)
    pred_label = preds[0] if preds else "classification"
    thresholds = format_law_thresholds_for_repair(law_text)

    lines = [
        "MISSING EXCLUSION RULE — REQUIRED REPAIR FOCUS",
        "",
        "Classification predicate to disqualify: %s" % (", ".join(preds) if preds else pred_label),
        "Scoped law-text numeric thresholds (preserve exactly in compares): %s" % thresholds,
        "",
        scaffold,
    ]
    if secondary_diagnostics.strip():
        lines.append("")
        lines.append("Also address secondary issues:")
        lines.append(secondary_diagnostics.strip())
    return "\n".join(lines)
