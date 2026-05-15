"""Generic law-text scoping before KB compilation (citation-based or keyword retrieval)."""

from __future__ import annotations

import json
import os
import re
from typing import Any


def _scope_mode() -> str:
    return (os.getenv("JSON_IR_SCOPE_MODE") or "cited").strip().lower()


def _extract_citation_keys(question: str) -> list[str]:
    """Return normalized citation keys like '4.17' or '1:24' from question text."""
    q = question or ""
    keys: list[str] = []
    patterns = [
        r"(?:article|artikel|art\.?)\s*(\d+(?:[:.]\d+)*(?:\s*,\s*par(?:agraph|agraaf)?\.?\s*\d+)?)",
        r"(?:section|§)\s*(\d+(?:[:.]\d+)*)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, q, re.IGNORECASE):
            raw = m.group(1).strip()
            raw = re.sub(r"\s+", " ", raw)
            keys.append(raw.replace(",", " ").strip())
    out: list[str] = []
    seen: set[str] = set()
    for k in keys:
        norm = re.sub(r"\s*par(?:agraph|agraaf)?\.?\s*(\d+)", r"(\1)", k, flags=re.I)
        norm = norm.replace(" ", "")
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


def _split_law_into_chunks(law_text: str) -> list[tuple[str, str]]:
    """Split on article/section headings; returns (heading, body) chunks."""
    text = (law_text or "").strip()
    if not text:
        return []
    heading_re = re.compile(
        r"(?im)^(?:\s*(?:article|artikel|art\.?)\s*(\d+(?:[:.]\d+)*)\b[^\n]*)",
    )
    matches = list(heading_re.finditer(text))
    if not matches:
        return [("", text)]
    chunks: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = m.group(0).strip()
        body = text[start:end].strip()
        key = m.group(1).replace(":", ".")
        chunks.append((key, body if body else heading))
    return chunks


def _chunk_matches_citation(chunk_key: str, citation: str) -> bool:
    ck = chunk_key.replace(":", ".").strip()
    cit = citation.replace(":", ".").strip()
    if ck == cit:
        return True
    if cit.startswith(ck + ".") or ck.startswith(cit + "."):
        return True
    return False


def _select_by_citation(law_text: str, citations: list[str]) -> str | None:
    if not citations:
        return None
    chunks = _split_law_into_chunks(law_text)
    if len(chunks) <= 1 and chunks and not chunks[0][0]:
        return None
    selected: list[str] = []
    for cit in citations:
        for key, body in chunks:
            if key and _chunk_matches_citation(key, cit):
                selected.append(body)
    if selected:
        return "\n\n".join(selected)
    return None


def _select_by_keywords(law_text: str, question: str, case: str, top_k: int = 3) -> str:
    query_tokens = set(re.findall(r"[a-z0-9]{4,}", (question + " " + case).lower()))
    if not query_tokens:
        return law_text
    chunks = _split_law_into_chunks(law_text)
    if len(chunks) <= 1:
        return law_text
    scored: list[tuple[int, str]] = []
    for _key, body in chunks:
        body_l = body.lower()
        score = sum(1 for t in query_tokens if t in body_l)
        scored.append((score, body))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))
    picked = [b for s, b in scored[:top_k] if s > 0]
    return "\n\n".join(picked) if picked else law_text


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
    meta: dict[str, Any] = {"mode": mode, "original_length": len(full)}
    if not full or mode == "full":
        meta["selected_length"] = len(full)
        return full, meta

    question = (question_text or "").strip()
    case = (case_text or "").strip()
    citations = _extract_citation_keys(question)

    if mode == "cited" and citations:
        picked = _select_by_citation(full, citations)
        if picked:
            meta["citations"] = citations
            meta["selected_length"] = len(picked)
            return picked, meta

    if mode in {"cited", "retrieve"}:
        picked = _select_by_keywords(full, question, case)
        if picked != full:
            meta["selection"] = "keyword_retrieval"
            meta["selected_length"] = len(picked)
            return picked, meta

    meta["fallback"] = "full_law"
    meta["selected_length"] = len(full)
    return full, meta


def write_scope_artifacts(directory: str, law_text: str, meta: dict[str, Any]) -> None:
    if not directory:
        return
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "selected_law_text.txt"), "w", encoding="utf-8") as f:
        f.write(law_text)
    with open(os.path.join(directory, "selected_law_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
