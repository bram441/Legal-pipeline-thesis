"""Symbols-repair supplements when temporal period relations are missing."""

from __future__ import annotations

import re
from typing import Any

from pipeline.kb.temporal_support import (
    TemporalEffectDetection,
    assess_temporal_support,
    find_period_like_types,
    find_temporal_support_symbols,
    collect_legal_output_predicate_names,
)


def _type_name_to_snake(type_name: str) -> str:
    """FinancialYear -> financial_year; Period -> period."""
    if not type_name:
        return "period"
    parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", str(type_name))
    if not parts:
        return str(type_name).lower()
    return "_".join(p.lower() for p in parts)


def _consecutive_relation_name(snake_stem: str) -> str:
    if snake_stem.endswith("y"):
        return "consecutive_%sies" % snake_stem[:-1]
    if snake_stem.endswith("s"):
        return "consecutive_%s" % snake_stem
    return "consecutive_%ss" % snake_stem


def suggest_temporal_symbol_candidates(period_types: list[str]) -> list[str]:
    """
    Concrete temporal support shapes for symbols repair, derived from period-like types.
    """
    if not period_types:
        return [
            "previous_period(Period, Period)",
            "next_period(Period, Period)",
            "consecutive_periods(Period, Period)",
            "immediately_precedes(Period, Period)",
            "immediately_follows(Period, Period)",
        ]
    primary = period_types[0]
    stem = _type_name_to_snake(primary)
    if stem in ("period", "year"):
        return [
            "previous_%s(%s, %s)" % (stem, primary, primary),
            "next_%s(%s, %s)" % (stem, primary, primary),
            "consecutive_%ss(%s, %s)" % (stem, primary, primary),
            "immediately_precedes(%s, %s)" % (primary, primary),
            "immediately_follows(%s, %s)" % (primary, primary),
        ]
    return [
        "previous_%s(%s, %s)" % (stem, primary, primary),
        "next_%s(%s, %s)" % (stem, primary, primary),
        _consecutive_relation_name(stem) + "(%s, %s)" % (primary, primary),
        "immediately_precedes(%s, %s)" % (primary, primary),
        "immediately_follows(%s, %s)" % (primary, primary),
    ]


def _suggest_temporal_symbol_shapes(period_types: list[str]) -> list[str]:
    return suggest_temporal_symbol_candidates(period_types)


def build_missing_temporal_support_symbol_supplement(
    *,
    law_text: str | None = None,
    question_text: str | None = None,
    scope_metadata: dict | None = None,
    symbol_table: dict | None = None,
    evidence: Any | None = None,
    helper_requiring_temporal_support: str | None = None,
) -> str:
    det: TemporalEffectDetection | None = None
    if evidence is not None and hasattr(evidence, "detected_temporal_terms"):
        det = evidence  # type: ignore[assignment]
    elif hasattr(evidence, "to_dict"):
        pass

    if det is None:
        det = assess_temporal_support(
            symbol_table,
            law_text=law_text,
            question_text=question_text,
            scope_metadata=scope_metadata,
            helper_name=helper_requiring_temporal_support
            or getattr(evidence, "helper_name", None),
            helper_description=getattr(evidence, "helper_description", "") or "",
        )

    helper = (
        helper_requiring_temporal_support
        or getattr(evidence, "helper_name", None)
        or getattr(evidence, "helper_requiring_temporal_support", None)
    )
    terms = getattr(det, "detected_terms", None) or getattr(evidence, "detected_temporal_terms", None) or []
    period_types = (
        getattr(det, "period_like_types", None)
        or getattr(evidence, "existing_period_types", None)
        or find_period_like_types(symbol_table)
    )
    legal_preds = (
        getattr(det, "legal_output_predicates", None)
        or getattr(evidence, "legal_output_predicates", None)
        or collect_legal_output_predicate_names(symbol_table)
    )
    temporal_existing = find_temporal_support_symbols(symbol_table)
    candidates = suggest_temporal_symbol_candidates(period_types)

    lines = [
        "MISSING TEMPORAL SUPPORT SYMBOL (MANDATORY):",
        "The symbol table is INVALID because the scoped law/question requires temporal reasoning "
        "(previous, following, or consecutive periods/years) but no temporal support "
        "relation/function exists.",
        "",
        "You MUST add at least one temporal support predicate/function using the existing "
        "period/year types below. Temporal support must be a SEPARATE relation/function between "
        "period arguments — not merely the words following/consecutive inside a legal-effect "
        "predicate name.",
        "",
    ]
    if terms:
        lines.append("Detected temporal phrases:")
        for t in terms[:8]:
            lines.append('  - "%s"' % t)
        lines.append("")
    if (question_text or "").strip():
        lines.append("Question (excerpt): %s" % (question_text or "").strip()[:200])
        lines.append("")
    if (law_text or "").strip():
        law_excerpt = (law_text or "").strip()[:300]
        lines.append("Scoped law (excerpt): %s" % law_excerpt)
        lines.append("")

    lines.append("Existing period-like types (use these in argument positions):")
    if period_types:
        for pt in period_types[:6]:
            lines.append("  - %s" % pt)
    else:
        lines.append("  - (none — add a period/year type if the law uses time periods)")
    lines.append("")

    lines.append("Required temporal support — add at least ONE of these concrete candidates:")
    for shape in candidates[:6]:
        lines.append("  - %s" % shape)
    lines.append(
        "Derive names from law text when possible; keep argument types aligned with the types above."
    )
    lines.append("")

    lines.append("Existing legal-output predicates (preserve; do NOT treat as temporal support):")
    if legal_preds:
        for lp in legal_preds[:6]:
            lines.append("  - %s" % lp)
    else:
        lines.append("  - (add legal_output derived predicate if required by scope)")
    lines.append("")

    if helper:
        lines.append(
            "Helper requiring temporal support (cannot be defined in rules until symbols exist): %s"
            % helper
        )
        lines.append("")

    if temporal_existing:
        lines.append("Existing temporal symbols (extend if insufficient):")
        for s in temporal_existing[:4]:
            lines.append("  - %s (%s)" % (s.get("name"), s.get("kind")))
        lines.append("")

    lines.extend(
        [
            "Symbols repair (now) — required:",
            "- Add a generic temporal relation/function between period/year arguments.",
            "- Model temporal support as structural case/background input, NOT as a derived legal-output helper.",
            "- Prefer kind=observable (or helper only when needed) with directly_observable=true and/or "
            "background=true / case_input=true on the temporal relation.",
            "- Do NOT mark temporal support as kind=derived or legal_output=true unless it can be "
            "deterministically defined from explicit date/year-number symbols in rules.",
            "- Legal-effect predicate names with following/previous/consecutive do NOT count as temporal support.",
            "- Keep legal-effect output predicates separate from classification predicates.",
            "- Preserve existing classification/support predicates unless directly wrong.",
            "",
            "Do not:",
            "- Add next_financial_year / previous_period only as a derived helper needing rule definitions.",
            "- Rename only the legal-effect predicate to include following/consecutive.",
            "- Hardcode case-specific constants or article numbers.",
            "- Encode temporal relations only in predicate names without period arguments.",
            "- Remove the legal-effect predicate.",
            "",
            "Rules repair (later): use these temporal relations in IF; define composite consecutive/threshold "
            "helpers in THEN when needed.",
        ]
    )
    return "\n".join(lines)
