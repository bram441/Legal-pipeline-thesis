"""Shared token/entity helpers for extraction IR (no IDP or heavy imports)."""

from __future__ import annotations

import re
from typing import Any

_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def symbol_tokens(name: Any) -> list[str]:
    s = str(name or "").strip()
    if not s:
        return []
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    s = s.replace("_", " ").replace("-", " ")
    return [t.lower() for t in s.split() if t.strip()]


def question_tokens(text: Any) -> set[str]:
    s = str(text or "").strip().lower()
    if not s:
        return set()
    s = re.sub(r"[^a-z0-9_ ]+", " ", s)
    toks = [t for t in s.split() if len(t) >= 3]
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "have", "has", "had",
        "does", "did", "what", "which", "when", "where", "why", "who", "according",
        "article", "under", "into", "onto", "about", "your", "their", "will", "shall",
        "can", "may", "must", "een", "het", "dat", "die", "wat", "welke", "volgens",
    }
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in toks if t not in stop}


def safe_entity(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    if not s:
        return ""
    if s[0].isdigit():
        s = "e_" + s
    return s


def safe_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value or "").strip()
    if not s:
        return ""
    if _NUMBER_RE.match(s) or s.lower() in {"true", "false"}:
        return s.lower()
    return safe_entity(s)
