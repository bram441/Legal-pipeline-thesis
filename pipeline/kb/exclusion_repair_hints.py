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
) -> str:
    """
    Extra rules-repair guidance when the KB lacks disqualification/exclusion rules.
    """
    preds = extract_classification_predicates(error_message)
    pred_label = preds[0] if preds else "classification"
    all_preds = ", ".join(preds) if preds else pred_label
    thresholds = format_law_thresholds_for_repair(law_text)

    lines = [
        "MISSING EXCLUSION RULE — REQUIRED REPAIR FOCUS",
        "",
        "The KB already has, or may have, positive qualification rules. That is not enough for false-case reasoning.",
        "Under open-world semantics, absence of proof for a favorable classification is NOT a false answer.",
        "",
        "Classification predicate to disqualify: %s" % all_preds,
        "Scoped law-text numeric thresholds (preserve exactly in compares): %s" % thresholds,
        "",
        "For laws saying \"not more than one criterion is exceeded,\" add a negative/exclusion rule.",
        "Let:",
        "  A = criterion 1 exceeded",
        "  B = criterion 2 exceeded",
        "  C = criterion 3 exceeded",
        "",
        "Correct exclusion (pairwise exceeded, negated classification in THEN):",
        "  %s" % _PAIRWISE_EXCLUSION_TEMPLATE.replace("classification", pred_label),
        "",
        "Concrete JSON_IR shape (example):",
        "  if: { or: [",
        "    { and: [ compare(metric_A, >, threshold_A), compare(metric_B, >, threshold_B) ] },",
        "    { and: [ compare(metric_A, >, threshold_A), compare(metric_C, >, threshold_C) ] },",
        "    { and: [ compare(metric_B, >, threshold_B), compare(metric_C, >, threshold_C) ] }",
        "  ] }",
        "  then: [ { pred: \"%s\", args: [...], negated: true } ]" % pred_label,
        "",
        "Do NOT use:",
        "  A OR B OR C => NOT %s" % pred_label,
        "  within_A OR within_B OR within_C => %s (simple OR within-threshold for qualification)" % pred_label,
        "  only positive pairwise within-threshold rules without this exclusion rule",
        "",
        "If positive qualification rules already exist, preserve them and ADD this missing exclusion rule.",
        "Do not remove or weaken existing positive rules while fixing this error.",
    ]
    if secondary_diagnostics.strip():
        lines.append("")
        lines.append("Also address any secondary issues below (numeric thresholds, cardinality, etc.):")
        lines.append(secondary_diagnostics.strip())
    return "\n".join(lines)
