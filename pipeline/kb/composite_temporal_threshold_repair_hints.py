"""Repair hints for composite threshold + temporal/consecutive helpers (legal-effect KBs)."""

from __future__ import annotations

import re
from typing import Any

from pipeline.kb.legal_effect import predicate_represents_legal_effect_output
from pipeline.kb.legal_effect_helper_repair_hints import (
    _THRESHOLD_MARKERS,
    legal_effect_rules_repair_context,
)

_COMPOSITE_SIGNALS_EN = (
    "consecutive",
    "two_consecutive",
    "following_year",
    "following_financial_year",
    "following_period",
    "previous_year",
    "prior_year",
    "prior_financial",
    "second_time",
    "repeated",
    "more_than_one_criterion",
    "more_than_one",
    "threshold",
    "exceeded",
    "exceeds",
    "criteria",
    "criterion",
)

_COMPOSITE_SIGNALS_NL = (
    "opeenvolgend",
    "twee_opeenvolgende",
    "volgend_boekjaar",
    "volgend_financieel",
    "vorig_boekjaar",
    "vorige_jaar",
    "herhaald",
    "tweede_keer",
    "meer_dan_een_criterium",
    "drempel",
    "overschreden",
    "criteria",
    "criterium",
)

_TEMPORAL_RELATION_MARKERS = (
    "prior_year",
    "previous_year",
    "prior_financial",
    "following_year",
    "following_financial",
    "next_year",
    "next_financial",
    "successor",
    "predecessor",
    "consecutive",
    "prior_period",
    "following_period",
)

_TEMPORAL_SUPPORT_NAME_MARKERS = _CONSECUTIVE_MARKERS = (
    "consecutive",
    "two_consecutive",
    "two_year",
    "following_year",
    "following_financial",
    "previous_year",
    "prior_year",
    "prior_financial",
    "second_time",
    "repeated",
    "opeenvolgend",
    "twee_opeenvolgende",
)


def _blob(name: str, description: str = "") -> str:
    return ((name or "") + " " + (description or "")).lower().replace("-", "_")


def matches_composite_temporal_threshold_pattern(name: str, description: str = "") -> bool:
    """True when helper name/description suggests threshold + temporal/consecutive composition."""
    b = _blob(name, description)
    signals = _COMPOSITE_SIGNALS_EN + _COMPOSITE_SIGNALS_NL
    hits = sum(1 for s in signals if s in b)
    has_temporal_or_consecutive = any(
        s in b
        for s in (
            "consecutive",
            "two_consecutive",
            "following",
            "previous",
            "prior_",
            "second_time",
            "repeated",
            "opeenvolg",
            "volgend",
            "vorig",
            "herhaald",
        )
    )
    has_threshold = any(s in b for s in ("threshold", "exceed", "criterion", "criteria", "drempel", "overschreden"))
    if has_temporal_or_consecutive and has_threshold:
        return True
    if has_temporal_or_consecutive and ("more_than_one" in b or "meer_dan_een" in b):
        return True
    return hits >= 2 and has_temporal_or_consecutive


def helper_requires_temporal_support(name: str, description: str = "") -> bool:
    b = _blob(name, description)
    return any(m in b for m in _TEMPORAL_SUPPORT_NAME_MARKERS) or (
        "more_than_one" in b and ("year" in b or "jaar" in b or "consecutive" in b or "opeenvolg" in b)
    )


def _sym_entries(symbol_table: dict | None) -> list[dict[str, Any]]:
    if not symbol_table:
        return []
    out: list[dict[str, Any]] = []
    for p in symbol_table.get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            out.append(p)
    for f in symbol_table.get("functions") or []:
        if isinstance(f, dict) and f.get("name"):
            out.append(f)
    return out


def collect_temporal_relation_candidates(symbol_table: dict | None) -> list[dict[str, str]]:
    from pipeline.kb.temporal_support import find_temporal_support_symbols

    return find_temporal_support_symbols(symbol_table)


def collect_threshold_helper_candidates(
    symbol_table: dict | None,
    *,
    defined_in_then: set[str] | None = None,
) -> list[dict[str, str]]:
    defined = defined_in_then or set()
    candidates: list[dict[str, str]] = []
    for sym in _sym_entries(symbol_table):
        name = str(sym["name"])
        name_l = name.lower().replace("-", "_")
        kind = str(sym.get("kind") or "")
        desc = str(sym.get("description") or "")
        if any(m in name_l for m in _THRESHOLD_MARKERS) or "criterion" in name_l:
            if kind in {"helper", "derived"} or name in defined:
                candidates.append(
                    {
                        "name": name,
                        "kind": kind,
                        "role": "threshold_helper",
                        "description": desc[:120],
                    }
                )
        elif kind in {"observable", "input"} and any(
            m in name_l for m in ("turnover", "employee", "balance_sheet", "amount", "count")
        ):
            candidates.append(
                {
                    "name": name,
                    "kind": kind,
                    "role": "numeric_observable",
                    "description": desc[:120],
                }
            )
    return candidates


def collect_legal_output_candidates(symbol_table: dict | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for sym in _sym_entries(symbol_table):
        if not isinstance(sym, dict):
            continue
        name = str(sym.get("name") or "")
        desc = str(sym.get("description") or "")
        kind = str(sym.get("kind") or "")
        lo = sym.get("legal_output")
        cat = str(sym.get("output_category") or "")
        if predicate_represents_legal_effect_output(
            name,
            description=desc,
            kind=kind,
            legal_output=lo if isinstance(lo, bool) else None,
            output_category=cat,
        ):
            out.append(
                {
                    "name": name,
                    "kind": kind,
                    "role": "legal_output",
                    "description": desc[:120],
                }
            )
    return out


def undeclared_temporal_funcs_in_rules(merged_ir: dict | None, symbol_table: dict | None) -> list[str]:
    from pipeline.kb.temporal_support import undeclared_temporal_funcs_in_rules as _undeclared

    return _undeclared(merged_ir, symbol_table)


def diagnose_missing_temporal_support(
    helper_name: str,
    *,
    symbol_table: dict | None,
    description: str = "",
    merged_ir: dict | None = None,
    law_text: str | None = None,
    question_text: str | None = None,
    scope_metadata: dict | None = None,
) -> bool:
    from pipeline.kb.temporal_support import diagnose_missing_temporal_support as _diag

    return _diag(
        helper_name,
        symbol_table=symbol_table,
        description=description,
        merged_ir=merged_ir,
        law_text=law_text,
        question_text=question_text,
        scope_metadata=scope_metadata,
    )


def classify_helper_kind_hints(name: str, description: str = "") -> list[str]:
    """Ordered tags from specific to general."""
    b = _blob(name, description)
    hints: list[str] = []
    if matches_composite_temporal_threshold_pattern(name, description):
        hints.append("composite_temporal_threshold")
    if any(m in b for m in ("consecutive", "two_consecutive", "opeenvolg", "twee_opeenvolg")):
        hints.append("consecutive")
    if any(
        m in b
        for m in (
            "following_year",
            "following_financial",
            "following_period",
            "volgend",
            "next_year",
            "apply_from",
        )
    ):
        hints.append("following_period")
    if any(m in b for m in ("previous_year", "prior_year", "prior_financial", "vorig")):
        hints.append("temporal")
    elif any(m in b for m in ("year", "period", "financial_year", "boekjaar", "jaar")) and (
        "consecutive" in b or "following" in b or "prior" in b
    ):
        hints.append("temporal")
    if "more_than_one" in b or "meer_dan_een" in b:
        hints.append("cardinality")
    if any(m in b for m in _THRESHOLD_MARKERS) or "criterion" in b:
        hints.append("threshold")
    if not hints:
        hints.append("unknown")
    return hints


def primary_helper_kind_hint(hints: list[str]) -> str:
    if "composite_temporal_threshold" in hints:
        return "composite_temporal_threshold"
    if "consecutive" in hints:
        return "consecutive"
    if "following_period" in hints:
        return "following_period"
    if "temporal" in hints:
        return "temporal"
    if "cardinality" in hints:
        return "cardinality"
    if "threshold" in hints:
        return "threshold"
    return hints[0] if hints else "unknown"


def qualifies_for_composite_temporal_threshold_card(
    *,
    helper_name: str,
    description: str = "",
    scope_metadata: dict | None = None,
    symbol_table: dict | None = None,
    merged_ir: dict | None = None,
    derives_legal_output: bool = False,
) -> bool:
    if not matches_composite_temporal_threshold_pattern(helper_name, description):
        return False
    if derives_legal_output:
        return True
    if scope_metadata and scope_metadata.get("question_asks_legal_effect") is True:
        return True
    return legal_effect_rules_repair_context(
        scope_metadata=scope_metadata,
        symbol_table=symbol_table,
        merged_ir=merged_ir,
        missing_helper_name=helper_name,
    )


def build_composite_temporal_threshold_supplement(
    *,
    error_message: str,
    symbol_table: dict | None,
    evidence: Any | None = None,
    law_text: str | None = None,
) -> str:
    helper = getattr(evidence, "helper_name", None) or "?"
    kind_hints = getattr(evidence, "helper_kind_hints", None) or classify_helper_kind_hints(helper)
    legal_preds = getattr(evidence, "legal_output_predicates_in_then", None) or []
    used_rules = getattr(evidence, "used_in_rules", None) or []
    threshold_cands = getattr(evidence, "threshold_helper_candidates", None) or []
    temporal_cands = getattr(evidence, "temporal_relation_candidates", None) or []
    legal_cands = getattr(evidence, "legal_output_candidates", None) or []
    missing_temporal = getattr(evidence, "missing_temporal_support_symbol", False)

    lines = [
        "You are repairing rules only.",
        "Do not create new symbols.",
        "Do not delete the legal-effect rule.",
        "Define the missing helper using existing lower-level predicates/functions.",
        "",
        "Missing helper: %s (kind hints: %s)" % (helper, ", ".join(kind_hints)),
    ]
    if legal_preds:
        lines.append(
            "Legal-effect predicate(s) in THEN (preserve): " + ", ".join(legal_preds[:4])
        )
    if used_rules:
        lines.append("Helper used in rules:")
        for u in used_rules[:6]:
            idx = u.get("rule_index", "?")
            then_lo = u.get("then_legal_output_predicates") or []
            tail = (" -> THEN legal output: " + ", ".join(then_lo)) if then_lo else ""
            lines.append("  - rules[%s].if%s" % (idx, tail))

    lines.extend(
        [
            "",
            "Recommended decomposition:",
            "A. Define per-criterion exceeded helpers from numeric comparisons on observable functions.",
            "B. Define more_than_one_criterion_exceeded as pairwise combinations:",
            "   (A_exceeded AND B_exceeded) OR (A_exceeded AND C_exceeded) OR (B_exceeded AND C_exceeded).",
            "C. Define the two-consecutive-years helper from:",
            "   condition holds in year Y AND condition holds in the immediately previous/consecutive year,",
            "   using an existing predecessor-year relation/function from the symbol table if available.",
            "D. Define following-year / following-period linkage only if the symbol table already has such a predicate/function.",
            "E. Keep the legal-effect output predicate in THEN, derived from the triggering helper and timing relation.",
        ]
    )

    if missing_temporal:
        lines.extend(
            [
                "",
                "WARNING: Symbol table lacks temporal year/period relations needed for step C/D.",
                "Do not invent unsupported temporal functions in rules repair.",
                "Use only declared symbols; inline the best available per-year conditions,",
                "or stop — symbols repair must add prior/following financial-year relations first.",
            ]
        )

    if threshold_cands:
        lines.append("")
        lines.append("Threshold / numeric candidates:")
        for c in threshold_cands[:10]:
            lines.append("  - %s (%s) [%s]" % (c.get("name"), c.get("kind"), c.get("role", "")))

    if temporal_cands:
        lines.append("")
        lines.append("Temporal relation candidates:")
        for c in temporal_cands[:8]:
            lines.append("  - %s (%s)" % (c.get("name"), c.get("kind")))

    if legal_cands and not legal_preds:
        lines.append("")
        lines.append("Legal-output symbols:")
        for c in legal_cands[:4]:
            lines.append("  - %s (%s)" % (c.get("name"), c.get("kind")))

    gen_cands = getattr(evidence, "candidate_lower_level_symbols", None) or []
    if gen_cands:
        lines.append("")
        lines.append("Other lower-level symbols:")
        for c in gen_cands[:8]:
            lines.append("  - %s (%s)" % (c.get("name"), c.get("kind")))

    lines.extend(
        [
            "",
            "Do not:",
            "- Create new symbols during rules repair.",
            "- Delete the legal-effect rule or its THEN conclusion.",
            "- Invent prior/following year functions not declared in the symbol table.",
        ]
    )
    if (law_text or "").strip():
        lines.append("- Preserve exact legal thresholds and timing from scoped law text.")
    return "\n".join(lines)


def build_missing_temporal_support_symbol_supplement(*, evidence: Any | None = None, **kwargs: Any) -> str:
    from pipeline.kb.temporal_support_repair_hints import (
        build_missing_temporal_support_symbol_supplement as _build,
    )

    return _build(evidence=evidence, **kwargs)
