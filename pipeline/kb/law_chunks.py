"""Deterministic law-text chunking and citation-based selection."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from pipeline.kb.law_citation import CitationRef, normalize_article_id


@dataclass
class LawChunk:
    chunk_id: str
    article: str
    paragraph: int | None
    point: int | None
    subpoint: int | None
    heading: str
    text: str
    start: int
    end: int
    parent_id: str | None = None

    def article_keys(self) -> set[str]:
        a = normalize_article_id(self.article)
        return {a, a.replace(":", "."), a.replace(".", ":")}


_ARTICLE_HEADING_RE = re.compile(
    r"(?im)^\s*(?:article|artikel|art\.?)\s*(\d+(?:[:.]\d+)*)\s*\.?",
)

_PARA_PATTERNS: list[re.Pattern[str]] = [
    # Structural paragraph markers only (not cross-refs like "article 3:1, par. 1").
    re.compile(r"(?im)(?:^|\n)\s*par\.\s*(\d+)\s*\."),
    re.compile(r"(?im)(?:^|\n)\s*§\s*(\d+)\s*[\.\):]?"),
    re.compile(r"(?im)(?:^|\n)\s*(?:paragraph|paragraaf)\s+(\d+)\s*[\.\):]?"),
    re.compile(
        r"(?im)(?:^|\n)\s*((?:eerste|tweede|derde|vierde|vijfde|zesde|zevende|achtste|negende|tiende|"
        r"first|second|third|fourth|fifth)\s+lid)\b"
    ),
]

_POINT_RE = re.compile(r"(?im)^\s*(\d+)\s*°")

_LID_WORD_TO_NUM: dict[str, int] = {
    "eerste": 1,
    "tweede": 2,
    "derde": 3,
    "vierde": 4,
    "vijfde": 5,
    "zesde": 6,
    "zevende": 7,
    "achtste": 8,
    "negende": 9,
    "tiende": 10,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
}


def _find_paragraph_markers(body: str) -> list[tuple[int, int, str]]:
    """Return sorted (start, paragraph_num, heading_text) markers in article body."""
    found: dict[int, tuple[int, str]] = {}
    m_lead = re.match(r"(?im)^\s*par\.\s*(\d+)\s*\.", body)
    if m_lead:
        found[m_lead.start()] = (int(m_lead.group(1)), m_lead.group(0).strip())
    for pat in _PARA_PATTERNS:
        for m in pat.finditer(body):
            start = m.start()
            if start in found:
                continue
            g1 = m.group(1)
            if str(g1).strip().isdigit():
                pnum = int(g1)
            else:
                pnum = _LID_WORD_TO_NUM.get(str(g1).split()[0].lower())
            if pnum is None:
                continue
            found[start] = (pnum, m.group(0).strip())
    return [(pos, pnum, heading) for pos, (pnum, heading) in sorted(found.items())]


def _split_article_body(
    article: str,
    article_heading: str,
    body: str,
    base_offset: int,
) -> list[LawChunk]:
    chunks: list[LawChunk] = []
    art_key = normalize_article_id(article)
    body_start = base_offset

    para_markers = _find_paragraph_markers(body)
    if not para_markers:
        point_matches = list(_POINT_RE.finditer(body))
        if not point_matches:
            chunks.append(
                LawChunk(
                    chunk_id=f"{art_key}/article",
                    article=art_key,
                    paragraph=None,
                    point=None,
                    subpoint=None,
                    heading=article_heading,
                    text=(article_heading + "\n" + body).strip(),
                    start=body_start,
                    end=body_start + len(body),
                )
            )
            return chunks

        intro_end = point_matches[0].start()
        if intro_end > 0:
            intro = body[:intro_end].strip()
            if intro:
                chunks.append(
                    LawChunk(
                        chunk_id=f"{art_key}/intro",
                        article=art_key,
                        paragraph=None,
                        point=None,
                        subpoint=None,
                        heading=article_heading,
                        text=(article_heading + "\n" + intro).strip(),
                        start=body_start,
                        end=body_start + intro_end,
                    )
                )
        for i, pm in enumerate(point_matches):
            pnum = int(pm.group(1))
            seg_start = pm.start()
            seg_end = point_matches[i + 1].start() if i + 1 < len(point_matches) else len(body)
            seg = body[seg_start:seg_end].strip()
            chunks.append(
                LawChunk(
                    chunk_id=f"{art_key}/p0/pt{pnum}",
                    article=art_key,
                    paragraph=None,
                    point=pnum,
                    subpoint=None,
                    heading=pm.group(0).strip(),
                    text=seg,
                    start=body_start + seg_start,
                    end=body_start + seg_end,
                    parent_id=f"{art_key}/article",
                )
            )
        return chunks

    article_intro = body[: para_markers[0][0]].strip()
    if article_intro:
        chunks.append(
            LawChunk(
                chunk_id=f"{art_key}/intro",
                article=art_key,
                paragraph=None,
                point=None,
                subpoint=None,
                heading=article_heading,
                text=(article_heading + "\n" + article_intro).strip(),
                start=body_start,
                end=body_start + para_markers[0][0],
            )
        )

    for i, (seg_start, para_num, pheading) in enumerate(para_markers):
        seg_end = para_markers[i + 1][0] if i + 1 < len(para_markers) else len(body)
        seg = body[seg_start:seg_end]
        para_id = f"{art_key}/p{para_num}"

        point_matches = list(_POINT_RE.finditer(seg))
        if not point_matches:
            chunks.append(
                LawChunk(
                    chunk_id=para_id,
                    article=art_key,
                    paragraph=para_num,
                    point=None,
                    subpoint=None,
                    heading=pheading or article_heading,
                    text=seg.strip(),
                    start=body_start + seg_start,
                    end=body_start + seg_end,
                    parent_id=f"{art_key}/article",
                )
            )
            continue

        para_intro = seg[: point_matches[0].start()].strip()
        if para_intro:
            chunks.append(
                LawChunk(
                    chunk_id=f"{para_id}/intro",
                    article=art_key,
                    paragraph=para_num,
                    point=None,
                    subpoint=None,
                    heading=pheading,
                    text=para_intro,
                    start=body_start + seg_start,
                    end=body_start + point_matches[0].start(),
                    parent_id=para_id,
                )
            )
        for j, ptm in enumerate(point_matches):
            ptnum = int(ptm.group(1))
            pt_start = ptm.start()
            pt_end = point_matches[j + 1].start() if j + 1 < len(point_matches) else len(seg)
            pt_text = seg[pt_start:pt_end].strip()
            chunks.append(
                LawChunk(
                    chunk_id=f"{para_id}/pt{ptnum}",
                    article=art_key,
                    paragraph=para_num,
                    point=ptnum,
                    subpoint=None,
                    heading=ptm.group(0).strip(),
                    text=pt_text,
                    start=body_start + seg_start + pt_start,
                    end=body_start + seg_start + pt_end,
                    parent_id=para_id,
                )
            )

    return chunks


def chunk_law_text(law_text: str) -> list[LawChunk]:
    text = (law_text or "").strip()
    if not text:
        return []

    matches = list(_ARTICLE_HEADING_RE.finditer(text))
    if not matches:
        return [
            LawChunk(
                chunk_id="full",
                article="",
                paragraph=None,
                point=None,
                subpoint=None,
                heading="",
                text=text,
                start=0,
                end=len(text),
            )
        ]

    all_chunks: list[LawChunk] = []
    for i, m in enumerate(matches):
        art = m.group(1)
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        heading_line = m.group(0).strip()
        body = block[len(m.group(0)) :].lstrip("\n")
        all_chunks.extend(_split_article_body(art, heading_line, body, start))
    return all_chunks


def _article_matches(chunk: LawChunk, citation: CitationRef) -> bool:
    cit_art = normalize_article_id(citation.article)
    for k in chunk.article_keys():
        ck = normalize_article_id(k)
        if ck == cit_art or ck.replace(":", ".") == cit_art.replace(":", "."):
            return True
        if cit_art.startswith(ck + ".") or cit_art.startswith(ck + ":"):
            return True
        if ck.startswith(cit_art + ".") or ck.startswith(cit_art + ":"):
            return True
    return False


def _dependency_paragraph_refs(text: str) -> set[int]:
    refs: set[int] = set()
    for m in re.finditer(r"(?:paragraph|paragraaf)\s+(\d+)", text, re.IGNORECASE):
        refs.add(int(m.group(1)))
    for m in re.finditer(r"§\s*(\d+)", text):
        refs.add(int(m.group(1)))
    if re.search(r"\b(?:eerste|first)\s+lid\b", text, re.IGNORECASE):
        refs.add(1)
    if re.search(r"\b(?:tweede|second)\s+lid\b", text, re.IGNORECASE):
        refs.add(2)
    if re.search(
        r"\b(?:criteria|criterion|voorwaarden?)\b.*?\b(?:in|van)\s+"
        r"(?:paragraph|paragraaf|§)\s*1\b",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        refs.add(1)
    if re.search(
        r"\b(?:consequences|gevolgen)\b.*?\b(?:paragraph|paragraaf|§)\s*(\d+)",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        m = re.search(
            r"\b(?:paragraph|paragraaf|§)\s*(\d+)",
            text,
            re.IGNORECASE,
        )
        if m:
            refs.add(int(m.group(1)))
    return {r for r in refs if r > 0}


def _expand_dependencies(
    selected: list[LawChunk],
    all_chunks: list[LawChunk],
) -> tuple[list[LawChunk], list[str]]:
    chosen: dict[str, LawChunk] = {c.chunk_id: c for c in selected}
    dep_ids: list[str] = []

    for chunk in list(selected):
        for pnum in _dependency_paragraph_refs(chunk.text):
            if chunk.paragraph == pnum:
                continue
            for c in all_chunks:
                if (
                    _article_matches(c, CitationRef(article=chunk.article, paragraph=pnum))
                    and c.paragraph == pnum
                    and c.point is None
                    and "/intro" not in c.chunk_id
                    and c.chunk_id not in chosen
                ):
                    chosen[c.chunk_id] = c
                    dep_ids.append(c.chunk_id)

    ordered = sorted(chosen.values(), key=lambda c: (c.start, c.end))
    return ordered, dep_ids


def select_chunks_for_citations(
    chunks: list[LawChunk],
    citations: list[CitationRef],
) -> tuple[list[LawChunk], dict[str, Any]]:
    meta: dict[str, Any] = {
        "cited_article": None,
        "cited_paragraph": None,
        "cited_point": None,
        "selected_chunk_ids": [],
        "included_dependency_chunks": [],
        "selected_granularity": None,
        "scope_mode": None,
    }
    if not chunks or not citations:
        return [], meta

    primary = max(citations, key=lambda c: (c.specificity(), c.confidence))
    meta["cited_article"] = normalize_article_id(primary.article)
    meta["cited_paragraph"] = primary.effective_paragraph()
    meta["cited_point"] = primary.point

    art_chunks = [c for c in chunks if _article_matches(c, primary)]
    if not art_chunks:
        return [], meta

    para = primary.effective_paragraph()
    selected: list[LawChunk] = []

    if primary.point is not None:
        meta["selected_granularity"] = "point"
        meta["scope_mode"] = "exact_citation"
        for c in art_chunks:
            if c.point == primary.point and (para is None or c.paragraph == para):
                selected.append(c)
        if para is not None:
            intro = [c for c in art_chunks if c.paragraph == para and c.point is None and "/intro" in c.chunk_id]
            for c in intro:
                if c.chunk_id not in {x.chunk_id for x in selected}:
                    selected.insert(0, c)
    elif para is not None:
        meta["selected_granularity"] = "paragraph"
        meta["scope_mode"] = "exact_citation"
        selected = [c for c in art_chunks if c.paragraph == para]
    else:
        meta["selected_granularity"] = "article"
        meta["scope_mode"] = "article_level"
        selected = list(art_chunks)

    if not selected:
        return [], meta

    selected, dep_ids = _expand_dependencies(selected, chunks)
    meta["included_dependency_chunks"] = dep_ids
    meta["selected_chunk_ids"] = [c.chunk_id for c in selected]
    if dep_ids:
        meta["selected_granularity"] = "mixed"

    return selected, meta


def chunks_to_scoped_text(chunks: list[LawChunk]) -> str:
    if not chunks:
        return ""
    return "\n\n".join(c.text.strip() for c in chunks if c.text.strip())
