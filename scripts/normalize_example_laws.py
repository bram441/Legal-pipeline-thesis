#!/usr/bin/env python
"""
Normalize typographic / Unicode noise in example_laws/*.txt for easier parsing and LLM handling.

- Unicode spaces -> ASCII space
- Typographic quotes/dashes -> ASCII
- § and §§ -> 'par.' (paragraph references; Belgian 'paragraaf')
- Ordinal list markers like 1° .. 34° -> (1) .. (34) (degree sign, not temperature)

Run from project root: python scripts/normalize_example_laws.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def normalize(text: str) -> str:
    for u in (
        "\u00a0",
        "\u1680",
        "\u2000",
        "\u2001",
        "\u2002",
        "\u2003",
        "\u2004",
        "\u2005",
        "\u2006",
        "\u2007",
        "\u2008",
        "\u2009",
        "\u200a",
        "\u202f",
        "\u205f",
        "\u3000",
    ):
        text = text.replace(u, " ")

    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")

    text = re.sub(r"§§\s*", "par. ", text)
    text = text.replace("§", "par.")
    text = re.sub(r"\.(par\.)", r". \1", text)

    # Ordinal degrees on list numbers (including before comma or semicolon)
    text = re.sub(r"(\d{1,2})°", r"(\1)", text)

    lines = []
    for line in text.splitlines():
        lines.append(re.sub(r"[ \t]+", " ", line).rstrip())
    return "\n".join(lines)


def main() -> int:
    d = _ROOT / "example_laws"
    for name in ("microvennootschappen.txt", "erfrecht.text", "vreemdelingenwet.txt"):
        p = d / name
        if not p.is_file():
            print("Skip (missing):", p, file=sys.stderr)
            continue
        raw = p.read_text(encoding="utf-8")
        out = normalize(raw)
        if not out.endswith("\n"):
            out += "\n"
        p.write_text(out, encoding="utf-8")
        print("Wrote", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
