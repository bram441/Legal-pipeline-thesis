"""Generic query argument repair using schema types and question overlap (law-agnostic)."""

from __future__ import annotations

import re
from typing import Any

from pipeline.extraction.json_ir import _entities_by_type, _question_tokens, _safe_entity, _symbol_sig


def _explicit_name_in_question(question: str | None) -> str | None:
    if not question:
        return None
    patterns = [
        r"\b(?:Is|Are|Does|Did|Was|Were)\s+([A-Z][a-zA-Z]+)\b",
        r"\b(?:for|about)\s+([A-Z][a-zA-Z]+)\b",
        r"^\s*(?:Heeft|Verkrijgt|Krijgt|Is|Kan|Moet)\s+([A-Z][a-zA-Z]+)\b",
    ]
    for pat in patterns:
        m = re.search(pat, question.strip())
        if m:
            name = m.group(1).strip().lower()
            if len(name) >= 2:
                return name
    return None


def apply_generic_query_arg_fill(
    user_question: str | None,
    query_obj: dict,
    case: dict,
    kb_schema: dict | None,
) -> bool:
    """
    Fill unary/boolean query args when exactly one entity matches the required schema type.
    Returns True if query_obj was modified.
    """
    if _explicit_name_in_question(user_question):
        return False
    if str(query_obj.get("type") or "").lower() != "predicate":
        return False
    if str(query_obj.get("mode") or "").lower() != "boolean":
        return False
    pred = str(query_obj.get("predicate") or "").strip()
    if not pred or not kb_schema:
        return False
    sig = _symbol_sig(kb_schema, pred)
    if not sig:
        return False
    arg_types = [str(t) for t in (sig.get("args") or [])]
    if not arg_types:
        return False
    args = list(query_obj.get("args") or [])
    while len(args) < len(arg_types):
        args.append("")
    changed = False
    for i, typ in enumerate(arg_types):
        cur = _safe_entity(args[i] if i < len(args) else "")
        if cur:
            continue
        cands = _entities_by_type(case, typ)
        if len(cands) == 1:
            args[i] = cands[0]
            changed = True
    if changed:
        query_obj["args"] = args
    return changed
