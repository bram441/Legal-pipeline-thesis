"""Generic law-text scoping before KB compilation (citation-based or keyword retrieval)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from pipeline.kb.law_citation import CitationRef, citations_to_legacy_keys, extract_citations
from pipeline.kb.law_chunks import (
    chunk_law_text,
    chunks_to_scoped_text,
    select_chunks_for_citations,
)
from pipeline.kb.legal_effect import (
    law_text_has_strong_legal_effect_language,
    question_has_legal_effect_language,
)


def _scope_mode() -> str:
    from pipeline.config import json_ir_config

    mode = str(json_ir_config().scope_mode or "cited").strip().lower()
    return mode if mode else "cited"


def _select_by_keywords(law_text: str, question: str, case: str, top_k: int = 3) -> str:
    query_tokens = set(re.findall(r"[a-z0-9]{4,}", (question + " " + case).lower()))
    if not query_tokens:
        return law_text
    chunks = chunk_law_text(law_text)
    if len(chunks) <= 1:
        return law_text
    scored: list[tuple[int, str]] = []
    for ch in chunks:
        body_l = ch.text.lower()
        score = sum(1 for t in query_tokens if t in body_l)
        scored.append((score, ch.text))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))
    picked = [b for s, b in scored[:top_k] if s > 0]
    return "\n\n".join(picked) if picked else law_text


def _enrich_scope_metadata(
    meta: dict[str, Any],
    *,
    scoped_text: str,
    question: str,
    citations: list[CitationRef],
) -> None:
    meta["citations_structured"] = [
        {
            "article": c.article,
            "paragraph": c.effective_paragraph(),
            "point": c.point,
            "lid": c.lid,
            "raw": c.raw,
            "confidence": c.confidence,
        }
        for c in citations
    ]
    meta["citations"] = citations_to_legacy_keys(citations)
    meta["question_asks_legal_effect"] = question_has_legal_effect_language(question)
    meta["contains_effect_language"] = law_text_has_strong_legal_effect_language(scoped_text)
    if meta.get("scope_mode") is None:
        meta["scope_mode"] = "exact_citation" if citations else "fallback_full_law"


def select_law_text_for_compilation(
    law_text: str,
    *,
    question_text: str | None = None,
    case_text: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Return (scoped_law_text, metadata).
    Modes: full | cited | retrieve (env JSON_IR_SCOPE_MODE, default cited).
    """
    mode = _scope_mode()
    full = (law_text or "").strip()
    meta: dict[str, Any] = {
        "mode": mode,
        "original_length": len(full),
        "scope_mode": None,
        "cited_article": None,
        "cited_paragraph": None,
        "cited_point": None,
        "selected_chunk_ids": [],
        "selected_granularity": None,
        "included_dependency_chunks": [],
        "contains_effect_language": False,
        "question_asks_legal_effect": False,
    }
    if not full or mode == "full":
        meta["scope_mode"] = "fallback_full_law"
        meta["selected_length"] = len(full)
        meta["question_asks_legal_effect"] = question_has_legal_effect_language(
            question_text or ""
        )
        meta["contains_effect_language"] = law_text_has_strong_legal_effect_language(full)
        return full, meta

    question = (question_text or "").strip()
    case = (case_text or "").strip()
    citations = extract_citations(question)

    if mode == "cited" and citations:
        all_chunks = chunk_law_text(full)
        primary = max(citations, key=lambda c: (c.specificity(), c.confidence))
        selected, sel_meta = select_chunks_for_citations(all_chunks, [primary])
        if selected:
            scoped = chunks_to_scoped_text(selected)
            meta.update(sel_meta)
            _enrich_scope_metadata(meta, scoped_text=scoped, question=question, citations=citations)
            meta["selected_length"] = len(scoped)
            return scoped, meta

    if mode in {"cited", "retrieve"}:
        picked = _select_by_keywords(full, question, case)
        if picked != full:
            meta["scope_mode"] = "keyword_retrieval"
            meta["selected_granularity"] = "mixed"
            meta["selected_length"] = len(picked)
            _enrich_scope_metadata(meta, scoped_text=picked, question=question, citations=citations)
            return picked, meta

    meta["scope_mode"] = "fallback_full_law"
    meta["selected_length"] = len(full)
    _enrich_scope_metadata(meta, scoped_text=full, question=question, citations=citations)
    return full, meta


def write_scope_artifacts(directory: str, law_text: str, meta: dict[str, Any]) -> None:
    if not directory:
        return
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "selected_law_text.txt"), "w", encoding="utf-8") as f:
        f.write(law_text)
    with open(os.path.join(directory, "selected_law_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
