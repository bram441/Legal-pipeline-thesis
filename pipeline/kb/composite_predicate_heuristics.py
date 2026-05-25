"""
Generic heuristics for computed/composite legal predicates (law-agnostic).

Used by JSON_IR validation to block unsafe negation over undefined helper/observable
predicates that case extraction is unlikely to populate.

Categories:
  A. legal/computed conclusion-like — block as observable unless derived/defined
  B. directly observable documentary/status/behavior facts — not computed
  C. threshold/counting/composite helpers — block unless case_input/background/directly_observable
"""

from __future__ import annotations

import re

# Threshold / counting / composite legal-condition tokens (not bare "valid" or "comply").
_THRESHOLD_COUNTING_LEXICON: tuple[str, ...] = (
    "carried_out",
    "consolidation",
    "consolidated",
    "elimination",
    "eliminated",
    "eliminations",
    "exceptional",
    "duration",
    "good_faith",
    "mainly_not",
    "no_longer",
    "exceeds",
    "exceed",
    "meets",
    "meet",
    "satisfies",
    "satisfy",
    "qualifies",
    "qualify",
    "eligible",
    "threshold",
    "criterion",
    "criteria",
    "condition",
    "requirement",
    "exception",
    "exempt",
    "consecutive",
    "majority",
    "at_least",
    "more_than",
    "less_than",
    "no_more_than",
    "count",
    "aggregate",
    "calculated",
    "derived",
    "computed",
    "fulfilled",
    "not_fulfilled",
    "voldoet",
    "overschrijdt",
    "voorwaarden",
    "criterium",
    "uitzondering",
    "drempel",
)

_THRESHOLD_TOKEN_RE = re.compile(
    r"(?i)(?<![a-z0-9_])("
    + "|".join(re.escape(t) for t in _THRESHOLD_COUNTING_LEXICON)
    + r")(?![a-z0-9_])"
)

# Document possession, identity, travel papers, explicit compliance behavior from case text.
_DIRECTLY_OBSERVABLE_FACTUAL_RE = re.compile(
    r"(?i)(?:"
    r"possess(?:es|ed)?_valid_(?:passport|travel_document|document|identity(?:_document)?)|"
    r"has_valid_(?:passport|travel_document|document|identity(?:_document)?)|"
    r"(?:passport|travel_document|identity_document)_(?:is_)?valid|"
    r"possess(?:es|ed)?_(?:a_)?valid_(?:passport|travel_document)|"
    r"failed_to_comply_with(?:_measure|_order|_requirement)?|"
    r"stated_unwillingness_to_comply(?:_with(?:_measure|_order))?|"
    r"refused_to_comply_with(?:_measure|_order)?|"
    r"unwillingness_to_comply(?:_with(?:_measure|_order))?|"
    r"did_not_comply_with(?:_measure|_order)?|"
    r"non_compliance_with(?:_measure|_order)?"
    r")"
)

# Legal conclusions / effects / entitlements — must not be raw observables.
_LEGAL_CONCLUSION_RE = re.compile(
    r"(?i)(?:"
    r"legal_consequence|legal_effect|legal_outcome|"
    r"qualifies_for(?:_status|_classification)?|"
    r"classification_applies|status_applies|consequence_applies|"
    r"entitled_to|has_right_to|must_be_removed|shall_be_removed|"
    r"prohibited_from|forbidden_to|"
    r"applies_from|applicable_under|takes_effect|comes_into_force|"
    r"liable_for|obligation_applies|sanction_applies|penalty_applies"
    r")"
)

_COMPUTED_CATEGORY_FACTUAL = "directly_observable_factual"
_COMPUTED_CATEGORY_LEGAL = "legal_conclusion_computed"
_COMPUTED_CATEGORY_THRESHOLD = "threshold_counting_composite"
_COMPUTED_CATEGORY_NONE = "none"


def looks_directly_observable_factual(name: str, description: str = "") -> bool:
    """Document/status/behavior facts a case text may assert directly (category B)."""
    blob = ((name or "") + " " + (description or "")).strip()
    if not blob:
        return False
    return bool(_DIRECTLY_OBSERVABLE_FACTUAL_RE.search(blob))


def looks_legal_conclusion_computed(name: str, description: str = "") -> bool:
    """Legal-effect/conclusion predicates that must not be case observables (category A)."""
    blob = ((name or "") + " " + (description or "")).strip()
    if not blob:
        return False
    return bool(_LEGAL_CONCLUSION_RE.search(blob))


def looks_threshold_counting_composite(name: str, description: str = "") -> bool:
    """Threshold/count/consolidation-style composite conditions (category C)."""
    text = ((name or "") + " " + (description or "")).strip().lower()
    if not text:
        return False
    if _THRESHOLD_TOKEN_RE.search(text):
        return True
    if re.search(
        r"(?i)(exceeds?|meets?|satisf|qualif|eligible|threshold|criteri|exception)",
        name or "",
    ):
        return True
    if re.search(
        r"(?i)_(more_than|less_than|at_least|no_more_than|threshold|criterion|criteria|condition)_",
        name or "",
    ):
        return True
    if re.search(
        r"(?i)(consolidat|eliminat|carried_out|good_faith|exceptional|no_longer|mainly_not)",
        name or "",
    ):
        return True
    return False


def classify_computed_observable_subject(name: str, description: str = "") -> str:
    """Return category label for repair hints and diagnostics."""
    if looks_directly_observable_factual(name, description):
        return _COMPUTED_CATEGORY_FACTUAL
    if looks_legal_conclusion_computed(name, description):
        return _COMPUTED_CATEGORY_LEGAL
    if looks_threshold_counting_composite(name, description):
        return _COMPUTED_CATEGORY_THRESHOLD
    return _COMPUTED_CATEGORY_NONE


def suggest_computed_observable_repair(name: str, description: str = "") -> str:
    """One-line repair guidance keyed to predicate category."""
    cat = classify_computed_observable_subject(name, description)
    if cat == _COMPUTED_CATEGORY_FACTUAL:
        return (
            "Predicate '%s' is a documentary/status/behavior fact: keep kind=observable and set "
            "directly_observable=true and/or case_input=true (not helper/derived)."
            % name
        )
    if cat == _COMPUTED_CATEGORY_LEGAL:
        return (
            "Predicate '%s' is a legal conclusion/effect: use kind=derived (or helper with rules), "
            "not observable."
            % name
        )
    if cat == _COMPUTED_CATEGORY_THRESHOLD:
        return (
            "Predicate '%s' is threshold/counting/composite: use kind=helper or derived with "
            "defining rules from numeric compares, or case_input/background only when explicitly "
            "case-given."
            % name
        )
    return (
        "Predicate '%s': reclassify as helper/derived with defining rules, or set "
        "directly_observable=true only if cases may state the fact verbatim."
        % name
    )


def looks_computed_composite(name: str, description: str = "") -> bool:
    """True when name/description suggests unsafe observable (A or C, not B)."""
    if looks_directly_observable_factual(name, description):
        return False
    if looks_legal_conclusion_computed(name, description):
        return True
    return looks_threshold_counting_composite(name, description)


def symbol_directly_observable(raw: dict | None) -> bool:
    """Explicit escape hatch: case text may state this composite fact directly."""
    if not isinstance(raw, dict):
        return False
    for key in ("directly_observable", "case_observable", "direct_case_observable"):
        if raw.get(key) is True:
            return True
    meta = raw.get("metadata")
    if isinstance(meta, dict):
        for key in ("directly_observable", "case_observable", "direct_case_observable"):
            if meta.get(key) is True:
                return True
    return False


def symbol_background_or_case_input(raw: dict | None) -> bool:
    """Structural/background facts supplied with case input (not rule-derived)."""
    if not isinstance(raw, dict):
        return False
    for key in (
        "background",
        "case_input",
        "structural",
        "temporal_background",
        "background_relation",
        "factual_case_input",
    ):
        if raw.get(key) is True:
            return True
    meta = raw.get("metadata")
    if isinstance(meta, dict):
        for key in ("background", "case_input", "structural", "temporal_background"):
            if meta.get(key) is True:
                return True
    return False
