"""Generic legal-question classification (no law-specific vocabulary)."""

from __future__ import annotations

import os
import re


_LEGAL_CONCLUSION_MARKERS_EN = (
    r"\bright\b",
    r"\bentitled\b",
    r"\bentitlement\b",
    r"\bobligation\b",
    r"\bobliged\b",
    r"\bliable\b",
    r"\bliability\b",
    r"\bvalid\b",
    r"\binvalid\b",
    r"\bmay\b",
    r"\bmust\b",
    r"\bshall\b",
    r"\bprohibited\b",
    r"\bpermitted\b",
    r"\ballowed\b",
    r"\bexcluded\b",
    r"\bforfeited\b",
    r"\blegal consequence\b",
    r"\bclassification\b",
    r"\bstatus\b",
    r"\baccording to\b",
    r"\bpursuant to\b",
    r"\bunder article\b",
    r"\bunder art\.?\b",
    r"\bapplies\b",
    r"\bapplicable\b",
    r"\bqualifies\b",
    r"\bacquires\b",
    r"\bobtains\b",
    r"\breceives\b",
    r"\bhas the right\b",
    r"\bis entitled\b",
)

_LEGAL_CONCLUSION_MARKERS_NL = (
    r"\brecht op\b",
    r"\bheeft recht\b",
    r"\bverkrijgt\b",
    r"\bkrijgt\b",
    r"\bmag\b",
    r"\bmoet\b",
    r"\bverplicht\b",
    r"\baansprakelijk\b",
    r"\bgeldig\b",
    r"\bongeldig\b",
    r"\bverboden\b",
    r"\btoegelaten\b",
    r"\buitgesloten\b",
    r"\bvervallen\b",
    r"\bvolgens artikel\b",
    r"\bovereenkomstig\b",
    r"\bkrachtens\b",
    r"\bvan toepassing\b",
    r"\bkwalificeert\b",
    r"\bis er sprake van\b",
    r"\bheeft .* recht\b",
)

_FACTUAL_MARKERS = (
    r"\bdid\b.+\boccur\b",
    r"\bdoes\b.+\bhave\b",
    r"\bis\b.+\btrue\b",
    r"\bwas\b.+\brecorded\b",
    r"\bgedocumenteerd\b",
    r"\bheeft\b.+\bingediend\b",
    r"\bsubmit\b",
    r"\bfiled\b",
    r"\bregistered\b",
    r"\boccurred\b",
    r"\bgebeurd\b",
)

_REFLEXIVE_MARKERS = (
    "same",
    "identical",
    "equal",
    "equals",
    "self",
    "itself",
    "is_same",
    "identity",
    "reflexive",
    "symmetric_identity",
)


def domain_heuristics_enabled() -> bool:
    """Domain-specific succession/role hacks (disabled by default)."""
    return (os.getenv("LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _matches_legal_conclusion_markers(question: str) -> bool:
    t = (question or "").strip().lower()
    if not t:
        return False
    for pat in _LEGAL_CONCLUSION_MARKERS_EN + _LEGAL_CONCLUSION_MARKERS_NL:
        if re.search(pat, t, re.IGNORECASE):
            return True
    return False


def question_asks_legal_conclusion(question: str) -> bool:
    """True when the question targets a legal effect, not merely a recorded fact."""
    if _matches_legal_conclusion_markers(question):
        return True
    if question_asks_factual_only(question):
        return False
    return False


def question_asks_factual_only(question: str) -> bool:
    """True when the question clearly asks about a fact/event, not a legal effect."""
    t = (question or "").strip().lower()
    if not t:
        return False
    for pat in _FACTUAL_MARKERS:
        if re.search(pat, t, re.IGNORECASE):
            return True
    return False


def is_reflexive_predicate_name(name: str, description: str = "") -> bool:
    blob = ((name or "") + " " + (description or "")).lower()
    blob = re.sub(r"[^a-z0-9]+", " ", blob)
    return any(m in blob for m in _REFLEXIVE_MARKERS)


def witness_modeling_hint() -> str:
    return (
        " If the legal condition only requires that some qualifying actor, object, event, document, "
        "relationship, or condition exists, and the identity of that witness is not needed by the "
        "legal consequence, model it as an observable Boolean condition on the main legal subject "
        "instead of a relation requiring invented witness entities."
    )
