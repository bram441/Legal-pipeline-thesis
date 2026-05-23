"""Extract and normalize numeric literals from scoped law text (law-agnostic)."""

from __future__ import annotations

import re

_LOGICAL_SMALL_CONSTANTS = frozenset({0, 1, 2, 3, 4, 5, 10})


def parse_numeric_token(token: str) -> float | None:
    """
    Parse a numeric token from law text or rules.
    Supports 900,000 / 900.000 / 11250000 / 11,250,000 / 11.250.000 / 50 / 50.0.
    """
    raw = (token or "").strip()
    if not raw:
        return None
    if raw.lower() in {"true", "false"}:
        return None
    t = re.sub(r"\s+", "", raw)
    if re.fullmatch(r"\d+", t):
        return float(int(t))

    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        parts = t.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and parts[1].isdigit():
            t = parts[0] + parts[1]
        elif all(p.isdigit() and len(p) == 3 for p in parts[1:]) and parts[0].isdigit():
            t = "".join(parts)
        else:
            t = t.replace(",", ".")
    elif "." in t:
        parts = t.split(".")
        if len(parts) >= 2 and all(p.isdigit() for p in parts):
            if all(len(p) == 3 for p in parts[1:]) and len(parts[0]) <= 3:
                t = "".join(parts)
            elif len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3:
                t = parts[0] + parts[1]
            else:
                t = t.replace(".", "")
        else:
            t = t.replace(".", "")

    if re.fullmatch(r"\d+", t):
        return float(int(t))
    if re.fullmatch(r"\d+\.\d+", t):
        return float(t)
    return None


def extract_numeric_values_from_law_text(law_text: str | None) -> set[float]:
    """All numeric values appearing in law text, normalized for comparison."""
    text = law_text or ""
    if not text.strip():
        return set()
    text = re.sub(r"\b\d+(?:[:/]\d+)+\b", " ", text)
    values: set[float] = set()
    def _add_token(token: str) -> None:
        v = parse_numeric_token(token)
        if v is None:
            return
        values.add(v)
        if v == int(v):
            values.add(float(int(v)))

    masked = list(text)
    for pat in (
        r"\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?",  # 900,000 / 11.250.000
        r"\d[\d.,]{2,}\d",
        r"\d{4,}",
    ):
        for m in re.finditer(pat, text):
            _add_token(m.group(0))
            for i in range(m.start(), m.end()):
                masked[i] = " "

    remainder = "".join(masked)
    for m in re.finditer(r"\b\d{2,3}\b", remainder):
        _add_token(m.group(0))
    return values


def format_law_numbers_for_message(values: set[float], *, limit: int = 12) -> str:
    """Compact sorted list for error messages."""
    ints = sorted({int(v) for v in values if v == int(v)})
    out = [str(n) for n in ints[:limit]]
    if len(ints) > limit:
        out.append("...")
    return ", ".join(out) if out else "(none found)"


def is_logical_small_constant(value: float) -> bool:
    """Cardinality / helper constants that need not appear verbatim in law text."""
    if value != int(value):
        return False
    return int(value) in _LOGICAL_SMALL_CONSTANTS


def numeric_value_matches_law(value: float, law_values: set[float]) -> bool:
    if is_logical_small_constant(value):
        return True
    if not law_values:
        return False
    candidates = {value}
    if value == int(value):
        candidates.add(float(int(value)))
    for lv in law_values:
        if value == lv:
            return True
        if lv == int(lv) and value == float(int(lv)):
            return True
    return False
