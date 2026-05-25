"""
Generic heuristics for computed/composite legal predicates (law-agnostic).

Used by JSON_IR validation to block unsafe negation over undefined helper/observable
predicates that case extraction is unlikely to populate.
"""

from __future__ import annotations

import re

# Word-boundary tokens in predicate names or descriptions (EN + common NL artifacts).
_COMPUTED_LEXICON: tuple[str, ...] = (
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
    "complies",
    "comply",
    "applies",
    "apply",
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
    "valid",
    "invalid",
    "voldoet",
    "overschrijdt",
    "voorwaarden",
    "criterium",
    "uitzondering",
    "drempel",
)

_TOKEN_RE = re.compile(
    r"(?i)(?<![a-z0-9_])(" + "|".join(re.escape(t) for t in _COMPUTED_LEXICON) + r")(?![a-z0-9_])"
)


def looks_computed_composite(name: str, description: str = "") -> bool:
    """True when name/description suggests threshold/count/composite legal condition."""
    text = ((name or "") + " " + (description or "")).strip().lower()
    if not text:
        return False
    if _TOKEN_RE.search(text):
        return True
    # Structural naming patterns common in LLM KBs.
    if re.search(r"(?i)(exceeds?|meets?|satisf|qualif|compli|eligible|threshold|criteri|exception)", name or ""):
        return True
    if re.search(r"(?i)_(more_than|less_than|at_least|no_more_than|threshold|criterion|criteria|condition)_", name or ""):
        return True
    if re.search(
        r"(?i)(consolidat|eliminat|carried_out|good_faith|exceptional|no_longer|mainly_not)",
        name or "",
    ):
        return True
    return False


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
    ):
        if raw.get(key) is True:
            return True
    meta = raw.get("metadata")
    if isinstance(meta, dict):
        for key in ("background", "case_input", "structural", "temporal_background"):
            if meta.get(key) is True:
                return True
    return False
