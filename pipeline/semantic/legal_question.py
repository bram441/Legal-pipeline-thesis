"""Generic legal-question classification (no law-specific vocabulary)."""

from __future__ import annotations

import os
import re


_LEGAL_DEFINITION_MARKERS_EN = (
    r"\bwithin the meaning of\b",
    r"\bfor the purposes of\b",
    r"\bas defined in\b",
    r"\bdefinition of\b",
    r"\bin the sense of\b",
    r"\bwithin the scope of\b",
    r"\bfalls under\b",
    r"\bqualifies as\b",
    r"\bis considered\b",
    r"\bis deemed\b",
    r"\bwithin the meaning\b",
)

_LEGAL_DEFINITION_MARKERS_NL = (
    r"\bin de zin van\b",
    r"\bals bedoeld in\b",
    r"\bbedoeld in artikel\b",
    r"\bzoals gedefinieerd in\b",
    r"\bvalt onder\b",
    r"\bkwalificeert als\b",
    r"\bwordt beschouwd als\b",
    r"\bwordt geacht\b",
    r"\bis sprake van\b",
)

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
    r"\bconsequences\b",
    r"\bconsequence\b",
    r"\btake effect\b",
    r"\btakes effect\b",
    r"\bapply from\b",
    r"\bapplies from\b",
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
    r"\bgevolgen\b",
    r"\btreden in werking\b",
    r"\bgelden vanaf\b",
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


def _matches_patterns(question: str, patterns: tuple[str, ...]) -> bool:
    t = (question or "").strip()
    if not t:
        return False
    for pat in patterns:
        if re.search(pat, t, re.IGNORECASE):
            return True
    return False


def question_asks_legal_definition(question: str) -> bool:
    """True when the question targets a legal definition or classification under a cited provision."""
    return _matches_patterns(question, _LEGAL_DEFINITION_MARKERS_EN + _LEGAL_DEFINITION_MARKERS_NL)


def question_asks_legal_effect_timing(question: str) -> bool:
    """True when the question targets consequences, applicability timing, or similar legal effects."""
    from pipeline.kb.legal_effect import question_has_legal_effect_language

    return question_has_legal_effect_language(question)


def question_asks_legal_conclusion(question: str) -> bool:
    """True when the question targets a legal effect, not merely a recorded fact."""
    if question_asks_legal_definition(question):
        return True
    if question_asks_legal_effect_timing(question):
        return True
    if _matches_patterns(question, _LEGAL_CONCLUSION_MARKERS_EN + _LEGAL_CONCLUSION_MARKERS_NL):
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
