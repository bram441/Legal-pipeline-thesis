"""
Error-specific repair cards for JSON IR KB compilation (law-agnostic).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepairCard:
    card_id: str
    title: str
    layer: str  # symbols | rules | either
    do_items: tuple[str, ...]
    do_not_items: tuple[str, ...]
    preferred_pattern: str = ""


_CARDS: dict[str, RepairCard] = {
    "missing_helper_definition": RepairCard(
        card_id="missing_helper_definition",
        title="Missing helper definition",
        layer="rules",
        do_items=(
            "Define the helper predicate with rules using lower-level observables/functions.",
            "Or replace the helper in the rule body with lower-level conditions.",
        ),
        do_not_items=(
            "Delete the helper condition.",
            "Mark it observable without a case-level justification.",
            "Rename it without defining it.",
        ),
        preferred_pattern="helper(X) :- observable_fact(X), compare(metric(X), op, threshold).",
    ),
    "computed_observable_unsafe": RepairCard(
        card_id="computed_observable_unsafe",
        title="Computed condition marked observable",
        layer="symbols",
        do_items=(
            "Change computed/composite predicates to helper or derived with defining rules.",
            "Keep raw factual observables as observable.",
            "Use directly_observable=true only if a case can state the composite fact verbatim.",
        ),
        do_not_items=(
            "Use observable kind merely to avoid defining rules.",
        ),
    ),
    "missing_threshold_classification_exclusion": RepairCard(
        card_id="missing_threshold_classification_exclusion",
        title="Missing threshold classification exclusion",
        layer="rules",
        do_items=(
            "Add a disqualification rule: at_least_two_exceeded => not classification (negated in THEN).",
            "Pair with qualification: not at_least_two_exceeded => classification.",
            "Define at_least_two_exceeded from threshold helpers before using it.",
        ),
        do_not_items=(
            "Rely on open-world absence of proof to answer false legal questions.",
            "Use only a positive sufficient rule with zero-threshold semantics.",
        ),
        preferred_pattern="at_least_two_exceeded(c,y) => not is_classification(c,y).",
    ),
    "numeric_threshold_not_in_law_text": RepairCard(
        card_id="numeric_threshold_not_in_law_text",
        title="Numeric threshold not in law text",
        layer="rules",
        do_items=(
            "Preserve numeric thresholds exactly from scoped law text.",
            "Replace invented thresholds with matching law-text numbers.",
        ),
        do_not_items=(
            "Infer new thresholds (e.g. change 900,000 into 1,900,000).",
            "Round or rescale legal constants during repair.",
            "Add 1,000,000 unless the law text contains it.",
        ),
    ),
    "threshold_cardinality_or_singleton": RepairCard(
        card_id="threshold_cardinality_or_singleton",
        title="Threshold cardinality / polarity",
        layer="rules",
        do_items=(
            "When the law says 'not more than one criterion is exceeded', define exceeded: "
            "A = criterion 1 exceeded, B = criterion 2 exceeded, C = criterion 3 exceeded.",
            "Correct positive qualification: NOT ((A AND B) OR (A AND C) OR (B AND C)) => classification.",
            "Correct negative/exclusion/disqualification: "
            "((A AND B) OR (A AND C) OR (B AND C)) => NOT classification (negated predicate in THEN).",
            "If the failing rule has negated THEN, repair its IF to pairwise exceeded AND combinations; "
            "do not remove the exclusion rule or the positive rule.",
            "Preserve exact numeric thresholds from scoped law text.",
            "If using within-threshold conditions for qualification, use pairwise within: "
            "(within_A AND within_B) OR (within_A AND within_C) OR (within_B AND within_C).",
            "Exclusion/disqualification must still use pairwise exceeded combinations, not within-OR.",
        ),
        do_not_items=(
            "A OR B OR C => classification.",
            "A OR B OR C => NOT classification.",
            "within_A OR within_B OR within_C => classification.",
            "Remove the exclusion rule when fixing cardinality.",
            "Remove the positive rule when fixing exclusion.",
            "Invent or alter legal threshold numbers during repair.",
        ),
        preferred_pattern=(
            "Positive: NOT ((A_exceeded AND B_exceeded) OR (A_exceeded AND C_exceeded) OR "
            "(B_exceeded AND C_exceeded)) => classification. "
            "Exclusion: ((A_exceeded AND B_exceeded) OR (A_exceeded AND C_exceeded) OR "
            "(B_exceeded AND C_exceeded)) => NOT classification."
        ),
    ),
    "status_as_type": RepairCard(
        card_id="status_as_type",
        title="Status modeled as primitive type",
        layer="symbols",
        do_items=(
            "Replace narrow legal-status types with broader entity types.",
            "Model the status/classification as a derived predicate over the broader type.",
        ),
        do_not_items=(
            "Keep type X and predicate is_x(X).",
            "Make ordinary case entities impossible to classify.",
        ),
    ),
    "missing_legal_effect_output": RepairCard(
        card_id="missing_legal_effect_output",
        title="Missing legal-effect output predicate",
        layer="symbols",
        do_items=(
            "Add a derived legal-output predicate for consequence/effect/timing/right/obligation.",
            "Set legal_output=true or output_category=legal_effect when helpful.",
            "Keep classification predicates only as intermediate support.",
        ),
        do_not_items=(
            "Answer legal-effect questions using broad classification predicates only.",
        ),
    ),
    "derived_predicate_not_defined": RepairCard(
        card_id="derived_predicate_not_defined",
        title="Derived predicate not defined in rules",
        layer="rules",
        do_items=(
            "Add at least one rule with the derived predicate in THEN.",
            "Define legal-output predicates from the law's antecedents.",
        ),
        do_not_items=(
            "Remove the derived predicate if it is legally necessary.",
        ),
    ),
    "ungrounded_variable": RepairCard(
        card_id="ungrounded_variable",
        title="Ungrounded consequent variable",
        layer="rules",
        do_items=(
            "Ensure every variable in THEN appears in IF or is safely quantified.",
            "Add missing relational antecedents.",
        ),
        do_not_items=(
            "Invent constants.",
            "Leave conclusion variables unconstrained.",
        ),
    ),
    "invalid_signature": RepairCard(
        card_id="invalid_signature",
        title="Invalid symbol signature",
        layer="symbols",
        do_items=(
            "Align predicate/function signatures with how the law and rules use them.",
            "Prefer broader entity types for legal statuses.",
        ),
        do_not_items=(
            "Patch rules by changing legal meaning when the symbol table is wrong.",
        ),
    ),
    "unknown_symbol": RepairCard(
        card_id="unknown_symbol",
        title="Unknown or undeclared symbol",
        layer="either",
        do_items=(
            "If the symbol expresses a legally required concept, add it to symbols and use it consistently.",
            "If it is a typo, replace it with the correct existing symbol.",
        ),
        do_not_items=(
            "Silently drop the condition.",
        ),
    ),
    "type_mismatch": RepairCard(
        card_id="type_mismatch",
        title="Type mismatch in rule",
        layer="either",
        do_items=(
            "Align quantifier types and argument types with vocabulary signatures.",
            "Prefer broader entity types for status predicates.",
        ),
        do_not_items=(
            "Force incompatible types without fixing signatures.",
        ),
    ),
    "idp_render_error": RepairCard(
        card_id="idp_render_error",
        title="FO render / IDP error",
        layer="either",
        do_items=(
            "Fix the JSON IR shape and symbol usage that caused the render failure.",
        ),
        do_not_items=(
            "Delete legal conditions to satisfy the renderer.",
        ),
    ),
    "json_parse_error": RepairCard(
        card_id="json_parse_error",
        title="Invalid JSON output",
        layer="either",
        do_items=(
            "Return valid JSON only.",
            "Preserve semantics from the previous valid attempt if available.",
        ),
        do_not_items=(
            "Include prose outside JSON.",
            "Use markdown fences.",
        ),
    ),
    "unknown_validation_error": RepairCard(
        card_id="unknown_validation_error",
        title="Validation error (generic)",
        layer="either",
        do_items=(
            "Fix the validation error without deleting legal conditions.",
            "Preserve valid symbols/rules unless implicated by the error.",
        ),
        do_not_items=(
            "Rename predicates without preserving semantics.",
            "Turn legal-output predicates into observables.",
        ),
    ),
}


def get_repair_card(error_code: str) -> RepairCard:
    return _CARDS.get(error_code) or _CARDS["unknown_validation_error"]


def format_repair_card(error_code: str) -> str:
    card = get_repair_card(error_code)
    lines = [
        "REPAIR CARD: %s" % card.title,
        "Intended layer: %s" % card.layer,
        "Do:",
    ]
    for item in card.do_items:
        lines.append("- " + item)
    lines.append("Do not:")
    for item in card.do_not_items:
        lines.append("- " + item)
    if card.preferred_pattern:
        lines.append("Preferred pattern: " + card.preferred_pattern)
    return "\n".join(lines)
