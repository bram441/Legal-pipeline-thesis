"""Belgian company-law helpers (threshold names shared with JSON-IR synthesis)."""

from __future__ import annotations

import re

from pipeline.utils.prompt_loader import load_prompt

COMPANY_THRESHOLD_FUNCTION_NAMES: tuple[str, ...] = (
    "threshold_employees_micro",
    "threshold_employees_small",
    "threshold_net_turnover_micro",
    "threshold_net_turnover_small",
    "threshold_total_assets_micro",
    "threshold_total_assets_small",
)


def law_text_mentions_company_thresholds(law_text: str) -> bool:
    t = (law_text or "").lower()
    markers = (
        "small enterprise",
        "micro enterprise",
        "kleine onderneming",
        "micro-onderneming",
        "micro-onderneming",
        "annual average number of employees",
        "annual average employees",
        "net turnover",
        "balance sheet total",
        "balance-sheet total",
        "threshold_employees",
        "threshold_net_turnover",
        "threshold_total_assets",
        "onderneming van kleine omvang",
        "micro-onderneming",
    )
    return any(m in t for m in markers)


def company_law_thresholds_prompt_addon(law_text: str) -> str:
    if not law_text_mentions_company_thresholds(law_text):
        return ""
    return "\n" + load_prompt("kb/kb_company_law_thresholds_addon.txt").strip() + "\n"


def patch_kb_missing_company_threshold_declarations(kb_text: str) -> tuple[str, bool]:
    """Insert nullary Int threshold declarations into vocabulary when theory calls them (LE/FO path)."""
    from pipeline.kb.kb_lint import _collect_declared_names, _theory_body, _vocab_body

    vb = _vocab_body(kb_text)
    th = _theory_body(kb_text)
    if vb is None or th is None:
        return kb_text, False
    declared = _collect_declared_names(vb)
    lines_to_add: list[str] = []
    for name in COMPANY_THRESHOLD_FUNCTION_NAMES:
        if name in declared:
            continue
        if re.search(r"\b" + re.escape(name) + r"\s*\(", th):
            lines_to_add.append("  " + name + ": () -> Int")
    if not lines_to_add:
        return kb_text, False
    insert = "\n".join(lines_to_add) + "\n"
    # Insert before closing brace of vocabulary block
    m = re.search(r"\bvocabulary\s+V\s*\{", kb_text, re.IGNORECASE)
    if not m:
        return kb_text, False
    start = kb_text.find("{", m.start())
    if start < 0:
        return kb_text, False
    depth = 0
    close = -1
    for i in range(start, len(kb_text)):
        if kb_text[i] == "{":
            depth += 1
        elif kb_text[i] == "}":
            depth -= 1
            if depth == 0:
                close = i
                break
    if close < 0:
        return kb_text, False
    patched = kb_text[:close] + insert + kb_text[close:]
    return patched, True
