"""Detect suspicious binary self-relations R(x,x) in JSON IR rules."""

from __future__ import annotations

import re

from pipeline.semantic.legal_question import is_reflexive_predicate_name

_NON_REFLEXIVE_RELATION_MARKERS: tuple[str, ...] = (
    "affiliated",
    "associated",
    "related",
    "connected",
    "belongs_to",
    "member_of",
    "forms_consortium",
    "consortium",
    "controls",
    "owns",
    "participates",
    "partner",
    "parent",
    "subsidiary",
    "daughter",
    "child_company",
    "linked_to",
    "group_with",
    "with_other",
    "with_another",
    "between",
    "spouse",
    "married",
    "successor",
    "predecessor",
)

_REFLEXIVE_METADATA_KEYS = (
    "reflexive",
    "reflexive_allowed",
    "allows_self_application",
    "non_reflexive",
)


def predicate_allows_self_application(
    name: str,
    description: str = "",
    *,
    reflexive_allowed: bool = False,
    non_reflexive: bool = False,
) -> bool:
    if non_reflexive:
        return False
    if reflexive_allowed:
        return True
    return is_reflexive_predicate_name(name, description)


def looks_like_between_entities_relation(name: str, description: str = "") -> bool:
    blob = re.sub(r"[^a-z0-9]+", " ", ((name or "") + " " + (description or "")).lower())
    if any(m in blob for m in _NON_REFLEXIVE_RELATION_MARKERS):
        return True
    if re.search(r"(?i)(?:_with$|_to$|_of$|related|affiliat|consortium|subsidiary|parent)", name or ""):
        return True
    return False


def is_suspicious_self_relation(
    pred_name: str,
    arg0: str,
    arg1: str,
    *,
    description: str = "",
    reflexive_allowed: bool = False,
    non_reflexive: bool = False,
) -> bool:
    """True when R(x,x) is likely invalid for a between-entities relation."""
    if not pred_name or not arg0 or arg0 != arg1:
        return False
    if predicate_allows_self_application(
        pred_name,
        description,
        reflexive_allowed=reflexive_allowed,
        non_reflexive=non_reflexive,
    ):
        return False
    return looks_like_between_entities_relation(pred_name, description)


def self_relation_repair_hint() -> str:
    return (
        " Do not use R(c,c) to express existence of another related entity. "
        "Introduce a distinct quantified variable if needed: "
        "exists other in EntityType: other != c and R(c, other). "
        "Or model existence as an observable Boolean on the main subject "
        "(e.g. has_affiliated_companies(c)). "
        "Only use R(x,x) when the predicate is explicitly reflexive by name, description, or metadata."
    )


def self_relation_error_message(*, rule_index: int, pred_name: str, var_name: str) -> str:
    return (
        f"rules[{rule_index}] suspicious self-relation: predicate '{pred_name}' is called with the same "
        f"variable twice ({var_name}, {var_name}) for a between-entities relation."
        f"{self_relation_repair_hint()}"
    )
