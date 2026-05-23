"""Parse article / paragraph / point citations from questions (EN + NL)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CitationRef:
    """Structured legal citation extracted from question text."""

    article: str
    paragraph: int | None = None
    point: int | None = None
    lid: int | None = None
    raw: str = ""
    confidence: float = 1.0

    def specificity(self) -> int:
        """Higher = more specific (point > paragraph/lid > article)."""
        if self.point is not None:
            return 3
        if self.paragraph is not None or self.lid is not None:
            return 2
        return 1

    def effective_paragraph(self) -> int | None:
        return self.paragraph if self.paragraph is not None else self.lid


_LID_WORDS: dict[str, int] = {
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


def normalize_article_id(raw: str) -> str:
    s = (raw or "").strip().replace(" ", "")
    s = s.replace(",", ".")
    if ":" in s:
        return s.replace(".", ":")
    return s.replace(":", ".")


def _lid_from_text(blob: str) -> int | None:
    m = re.search(
        r"\b(" + "|".join(_LID_WORDS.keys()) + r")\s+lid\b",
        blob,
        re.IGNORECASE,
    )
    if m:
        return _LID_WORDS.get(m.group(1).lower())
    return None


def _parse_groups(
    article: str | None,
    paragraph: str | None = None,
    point: str | None = None,
    lid_word: str | None = None,
    *,
    raw: str,
    confidence: float,
) -> CitationRef | None:
    if not article and not paragraph and not point and not lid_word:
        return None
    art = normalize_article_id(article) if article else ""
    if not art and paragraph is None and point is None:
        return None
    para: int | None = int(paragraph) if paragraph and paragraph.isdigit() else None
    pt: int | None = int(point) if point and point.isdigit() else None
    lid: int | None = _LID_WORDS.get(lid_word.lower()) if lid_word else None
    if para is None and lid is not None:
        para = lid
    return CitationRef(
        article=art or "",
        paragraph=para,
        point=pt,
        lid=lid,
        raw=raw.strip(),
        confidence=confidence,
    )


# Ordered patterns: more specific first.
_CITATION_REGEXES: list[tuple[re.Pattern[str], float]] = [
    # artikel 1, § 1, 4°  /  article 1, § 1, 4°
    (
        re.compile(
            r"(?:article|artikel|art\.?)\s*"
            r"(\d+(?:[:.]\d+)*)\s*[,;]?\s*"
            r"§\s*(\d+)\s*[,;]?\s*(\d+)\s*°",
            re.IGNORECASE,
        ),
        0.95,
    ),
    # artikel 1, eerste lid, 4°
    (
        re.compile(
            r"(?:article|artikel|art\.?)\s*"
            r"(\d+(?:[:.]\d+)*)\s*[,;]?\s*"
            r"((?:eerste|tweede|derde|vierde|vijfde|first|second|third|fourth|fifth)\s+lid)\s*[,;]?\s*"
            r"(\d+)\s*°",
            re.IGNORECASE,
        ),
        0.95,
    ),
    # Article 1, paragraph 1, point 4
    (
        re.compile(
            r"(?:article|artikel|art\.?)\s*"
            r"(\d+(?:[:.]\d+)*)\s*[,;]?\s*"
            r"(?:paragraph|paragraaf|par\.?)\s*(\d+)\s*[,;]?\s*"
            r"(?:point|punt)\s*(\d+)",
            re.IGNORECASE,
        ),
        0.95,
    ),
    # article 1:24 paragraph 1 / artikel 1:24, paragraaf 1
    (
        re.compile(
            r"(?:article|artikel|art\.?)\s*"
            r"(\d+(?:[:.]\d+)*)\s*[,;]?\s*"
            r"(?:paragraph|paragraaf|par\.?|§)\s*(\d+)",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # art. 1:24, §2 / artikel 1:24 § 2
    (
        re.compile(
            r"(?:article|artikel|art\.?)\s*"
            r"(\d+(?:[:.]\d+)*)\s*[,;]?\s*"
            r"§\s*(\d+)",
            re.IGNORECASE,
        ),
        0.9,
    ),
    # artikel 1:25, eerste lid / tweede lid
    (
        re.compile(
            r"(?:article|artikel|art\.?)\s*"
            r"(\d+(?:[:.]\d+)*)\s*[,;]?\s*"
            r"((?:eerste|tweede|derde|vierde|vijfde|first|second|third|fourth|fifth)\s+lid)\b",
            re.IGNORECASE,
        ),
        0.88,
    ),
    # article 1:24 (article only)
    (
        re.compile(
            r"(?:article|artikel|art\.?)\s*(\d+(?:[:.]\d+)*)",
            re.IGNORECASE,
        ),
        0.75,
    ),
]


def extract_citations(question: str) -> list[CitationRef]:
    """Return structured citations from question text, most specific first."""
    q = question or ""
    if not q.strip():
        return []
    found: list[CitationRef] = []
    seen: set[tuple] = set()

    for pat, conf in _CITATION_REGEXES:
        for m in pat.finditer(q):
            raw = m.group(0)
            groups = m.groups()
            ref: CitationRef | None = None
            if len(groups) == 3 and groups[1] and re.search(r"lid", groups[1], re.I):
                lid_word = groups[1].split()[0]
                ref = _parse_groups(
                    groups[0], point=groups[2], lid_word=lid_word, raw=raw, confidence=conf
                )
            elif len(groups) == 3 and groups[2] and "°" in raw:
                ref = _parse_groups(
                    groups[0], paragraph=groups[1], point=groups[2], raw=raw, confidence=conf
                )
            elif len(groups) == 3:
                ref = _parse_groups(
                    groups[0], paragraph=groups[1], point=groups[2], raw=raw, confidence=conf
                )
            elif len(groups) == 2:
                if groups[1] and re.search(r"lid", groups[1], re.I):
                    ref = _parse_groups(
                        groups[0], lid_word=groups[1].split()[0], raw=raw, confidence=conf
                    )
                else:
                    ref = _parse_groups(
                        groups[0], paragraph=groups[1], raw=raw, confidence=conf
                    )
            elif len(groups) == 1:
                ref = _parse_groups(groups[0], raw=raw, confidence=conf)

            if ref is None or not ref.article:
                continue
            key = (
                ref.article,
                ref.effective_paragraph(),
                ref.point,
                ref.lid,
            )
            if key in seen:
                continue
            seen.add(key)
            found.append(ref)

    # Standalone § after article context: "according to § 2 of article 1:24"
    for m in re.finditer(
        r"(?:article|artikel|art\.?)\s*(\d+(?:[:.]\d+)*).*?§\s*(\d+)",
        q,
        re.IGNORECASE | re.DOTALL,
    ):
        ref = _parse_groups(m.group(1), paragraph=m.group(2), raw=m.group(0), confidence=0.85)
        if ref and ref.article:
            key = (ref.article, ref.effective_paragraph(), ref.point, ref.lid)
            if key not in seen:
                seen.add(key)
                found.append(ref)

    found.sort(key=lambda r: (-r.specificity(), -r.confidence))
    return found


def citations_to_legacy_keys(citations: list[CitationRef]) -> list[str]:
    """Backward-compatible citation keys for logs (e.g. '1:24(1)')."""
    keys: list[str] = []
    for c in citations:
        k = normalize_article_id(c.article).replace(".", ":")
        p = c.effective_paragraph()
        if p is not None and c.point is not None:
            keys.append(f"{k}({p}).{c.point}")
        elif p is not None:
            keys.append(f"{k}({p})")
        else:
            keys.append(k)
    return keys
