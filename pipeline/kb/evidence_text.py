"""Normalize and validate case evidence_text against case_text."""

from __future__ import annotations

import re


def normalize_text_for_evidence_match(text: str) -> str:
    """Lowercase; collapse whitespace, hyphenation, and punctuation for substring checks."""
    s = str(text or "").lower()
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"[\s\-_]+", " ", s)
    s = re.sub(r"[^\w\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def evidence_text_supported_in_case(case_text: str | None, evidence_text: str | None) -> bool:
    """True when evidence_text is a normalized substring of case_text."""
    if not evidence_text or not str(evidence_text).strip():
        return False
    if not case_text or not str(case_text).strip():
        return False
    needle = normalize_text_for_evidence_match(evidence_text)
    haystack = normalize_text_for_evidence_match(case_text)
    if not needle or not haystack:
        return False
    return needle in haystack
