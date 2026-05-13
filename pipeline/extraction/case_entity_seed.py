"""Deterministic helpers to enrich case.entities from raw case text (law-agnostic)."""

from __future__ import annotations

import re
from typing import Any

from pipeline.extraction.json_ir import _merge_typed_entity, _safe_entity


# Capitalized tokens that are usually not person names in translated legal snippets.
_NAME_STOP = frozenset(
    {
        "the", "and", "but", "for", "art", "when", "then", "are", "was", "were", "not", "may", "can",
        "she", "her", "his", "him", "they", "them", "this", "that", "with", "from", "into", "upon",
        "each", "all", "any", "own", "one", "two", "both", "either", "nor", "yet", "per", "via",
        "chapter", "section", "paragraph", "article", "estate", "property", "goods", "children",
        "descendants", "relatives", "heirs", "spouse", "partner", "donor", "surviving", "deceased",
        "married", "cohabiting", "legally", "without", "according", "does", "is", "has", "have",
        "had", "been", "being", "also", "only", "such", "some", "same", "other", "under", "over",
        "their", "there", "these", "those", "which", "while", "where", "whether", "will", "would",
        "could", "should", "must", "shall", "here", "however", "therefore", "although", "because",
    }
)


def _kb_schema_uses_person(kb_schema: dict | None) -> bool:
    if not kb_schema or not isinstance(kb_schema, dict):
        return False
    types = kb_schema.get("types") or []
    if isinstance(types, list) and any(str(t).strip() == "Person" for t in types):
        return True
    for p in kb_schema.get("predicates") or []:
        if not isinstance(p, dict):
            continue
        for a in p.get("args") or []:
            if str(a).strip() == "Person":
                return True
    for f in kb_schema.get("functions") or []:
        if not isinstance(f, dict):
            continue
        for a in f.get("args") or []:
            if str(a).strip() == "Person":
                return True
    return False


def seed_person_entities_from_case_text(case_text: str, case: dict[str, Any], kb_schema: dict | None) -> int:
    """Add Person-like tokens from ``case_text`` into ``case['entities']['Person']``.

    Runs after JSON-IR normalization, before FO validation. Returns number of new names added.
    """
    if not case_text or not isinstance(case, dict) or not _kb_schema_uses_person(kb_schema):
        return 0
    raw = str(case_text)
    # English / translated prose: capitalized tokens (Els, Filip, Anna, …).
    found = re.findall(r"\b([A-Z][a-z]{2,})\b", raw)
    added = 0
    existing = {str(x).strip().lower() for x in (case.get("entities") or {}).get("Person", []) if x}
    for tok in found:
        low = tok.strip().lower()
        if not low or low in _NAME_STOP:
            continue
        ent = _safe_entity(tok)
        if not ent or ent in existing:
            continue
        _merge_typed_entity(case.setdefault("entities", {}), "Person", ent)
        existing.add(ent)
        added += 1
    return added
