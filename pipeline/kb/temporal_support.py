"""
Law-agnostic detection of period/year temporal vocabulary for legal-effect provisions.

Requires temporal relation symbols only when scoped text uses following/previous/consecutive
period language and the KB has legal-effect context — not merely because a period-like type exists.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pipeline.kb.legal_effect import (
    predicate_represents_legal_effect_output,
    schema_has_legal_effect_output_predicate,
    should_require_legal_effect_output,
)

# Phrase cues in law/question text (generic; not domain-specific).
_TEMPORAL_PHRASE_PATTERNS_EN: tuple[str, ...] = (
    r"\bfollowing\s+period\b",
    r"\bnext\s+period\b",
    r"\bfollowing\s+year\b",
    r"\bnext\s+year\b",
    r"\bfollowing\s+financial\s+year\b",
    r"\bnext\s+financial\s+year\b",
    r"\bprevious\s+period\b",
    r"\bpreceding\s+period\b",
    r"\bprevious\s+year\b",
    r"\bpreceding\s+year\b",
    r"\bprior\s+year\b",
    r"\bconsecutive\s+periods?\b",
    r"\bconsecutive\s+years?\b",
    r"\btwo\s+consecutive\s+periods?\b",
    r"\btwo\s+consecutive\s+years?\b",
    r"\bsecond\s+consecutive\b",
    r"\bsecond\s+time\b",
    r"\bimmediately\s+following\b",
    r"\bimmediately\s+preceding\b",
    r"\bfrom\s+the\s+following\b",
    r"\bfrom\s+the\s+next\b",
    r"\bafter\s+the\s+second\b",
    r"\bduring\s+the\s+previous\b",
    r"\bduring\s+the\s+preceding\b",
)

_TEMPORAL_PHRASE_PATTERNS_NL: tuple[str, ...] = (
    r"\bvolgend\s+tijdvak\b",
    r"\bvolgende\s+periode\b",
    r"\bvolgend\s+jaar\b",
    r"\bvolgende\s+boekjaar\b",
    r"\bdaaropvolgend\s+boekjaar\b",
    r"\bdaaropvolgende\s+boekjaar\b",
    r"\bvoorafgaand\s+tijdvak\b",
    r"\bvoorafgaande\s+periode\b",
    r"\bvorig\s+jaar\b",
    r"\bvoorgaand\s+jaar\b",
    r"\bvoorafgaand\s+jaar\b",
    r"\bopeenvolgende\s+tijdvakken\b",
    r"\bopeenvolgende\s+jaren\b",
    r"\bopeenvolgende\s+boekjaren\b",
    r"\btwee\s+opeenvolgende\b",
    r"\btweede\s+opeenvolgende\b",
    r"\btweede\s+achtereenvolgende\b",
    r"\bachtereenvolgende\b",
    r"\bonmiddellijk\s+volgend\b",
    r"\bonmiddellijk\s+voorafgaand\b",
    r"\bvanaf\s+het\s+volgende\b",
    r"\bvanaf\s+het\s+daaropvolgende\b",
    r"\bna\s+de\s+tweede\b",
    r"\bgedurende\s+het\s+voorafgaande\b",
)

_TEMPORAL_PHRASE_RES = tuple(
    re.compile(p, re.IGNORECASE) for p in _TEMPORAL_PHRASE_PATTERNS_EN + _TEMPORAL_PHRASE_PATTERNS_NL
)

_PERIOD_TYPE_MARKERS: tuple[str, ...] = (
    "year",
    "period",
    "financialyear",
    "bookyear",
    "accountingperiod",
    "taxyear",
    "tijdvak",
    "periode",
    "jaar",
    "boekjaar",
    "fiscalperiod",
    "reportingperiod",
)

_TEMPORAL_RELATION_NAME_MARKERS: tuple[str, ...] = (
    "prior_",
    "previous_",
    "preceding_",
    "following_",
    "next_",
    "successor",
    "predecessor",
    "consecutive",
    "immediately_precedes",
    "immediately_follows",
    "immediately_preceding",
    "immediately_following",
    "opeenvolg",
    "achtereenvolg",
    "volgend_",
    "daaropvolg",
    "voorafgaand",
    "voorgaand",
)

_HELPER_TEMPORAL_MARKERS: tuple[str, ...] = (
    "consecutive",
    "two_consecutive",
    "second_consecutive",
    "following",
    "following_year",
    "following_period",
    "next_year",
    "next_period",
    "previous",
    "previous_year",
    "previous_period",
    "prior",
    "preceding",
    "immediately_precedes",
    "immediately_follows",
    "achtereenvolg",
    "opeenvolg",
    "volgend",
    "daaropvolg",
    "voorafgaand",
    "vorig",
)


@dataclass
class TemporalEffectDetection:
    """Structured result of temporal phrase / context scanning."""

    detected_terms: list[str] = field(default_factory=list)
    requires_temporal_support: bool = False
    legal_effect_context: bool = False
    has_period_like_types: bool = False
    has_temporal_support_symbols: bool = False
    period_like_types: list[str] = field(default_factory=list)
    temporal_support_symbols: list[dict[str, str]] = field(default_factory=list)
    legal_output_predicates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected_temporal_terms": self.detected_terms,
            "requires_temporal_support": self.requires_temporal_support,
            "legal_effect_context": self.legal_effect_context,
            "has_period_like_types": self.has_period_like_types,
            "has_temporal_support_symbols": self.has_temporal_support_symbols,
            "existing_period_types": self.period_like_types,
            "existing_temporal_symbols": self.temporal_support_symbols,
            "legal_output_predicates": self.legal_output_predicates,
            "missing_temporal_support_symbol": (
                self.requires_temporal_support and not self.has_temporal_support_symbols
            ),
            "repair_route": (
                "symbols_repair_required"
                if self.requires_temporal_support and not self.has_temporal_support_symbols
                else None
            ),
        }


def _normalize_blob(name: str, description: str = "") -> str:
    return ((name or "") + " " + (description or "")).lower().replace("-", "_")


def extract_temporal_phrases_from_text(*texts: str | None) -> list[str]:
    """Return matched temporal phrase snippets (deduplicated, order preserved)."""
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not (text or "").strip():
            continue
        for pat in _TEMPORAL_PHRASE_RES:
            for m in pat.finditer(text):
                snippet = m.group(0).strip()
                key = snippet.lower()
                if key not in seen:
                    seen.add(key)
                    found.append(snippet)
    return found


def detect_temporal_effect_terms(
    law_text: str | None,
    question_text: str | None = None,
    *,
    scope_metadata: dict | None = None,
) -> TemporalEffectDetection:
    """Scan law/question/scope for temporal-effect language (phrase-based, law-agnostic)."""
    law = (law_text or "").strip()
    question = (question_text or "").strip()
    terms = extract_temporal_phrases_from_text(law, question)
    legal_ctx = _legal_effect_context_from_metadata(scope_metadata, law_text=law, question_text=question)
    has_phrases = bool(terms)
    requires = has_phrases and legal_ctx
    return TemporalEffectDetection(
        detected_terms=terms,
        requires_temporal_support=requires,
        legal_effect_context=legal_ctx,
    )


def _legal_effect_context_from_metadata(
    scope_metadata: dict | None,
    *,
    law_text: str | None = None,
    question_text: str | None = None,
) -> bool:
    if scope_metadata:
        if scope_metadata.get("question_asks_legal_effect") is True:
            return True
        if scope_metadata.get("contains_effect_language") is True:
            return True
    return should_require_legal_effect_output(law_text, scope_metadata=scope_metadata)


def _iter_symbol_dicts(symbols: dict | list | None) -> list[dict[str, Any]]:
    if symbols is None:
        return []
    if isinstance(symbols, dict):
        out: list[dict[str, Any]] = []
        for p in symbols.get("predicates") or []:
            if isinstance(p, dict):
                out.append(p)
        for f in symbols.get("functions") or []:
            if isinstance(f, dict):
                out.append(f)
        for t in symbols.get("types") or []:
            if isinstance(t, dict):
                out.append({"name": t.get("name"), "kind": "type", "description": t.get("description") or ""})
        return out
    out = []
    for sym in symbols:
        if hasattr(sym, "name"):
            out.append(
                {
                    "name": sym.name,
                    "kind": getattr(sym, "kind", ""),
                    "description": getattr(sym, "description", "") or "",
                    "args": getattr(sym, "args", None),
                    "returns": getattr(sym, "returns", None),
                    "legal_output": getattr(sym, "legal_output", None),
                    "output_category": getattr(sym, "output_category", "") or "",
                }
            )
        elif isinstance(sym, dict):
            out.append(sym)
    return out


def has_period_or_year_type(symbols: dict | list | None) -> bool:
    return bool(find_period_like_types(symbols))


def find_period_like_types(symbols: dict | list | None) -> list[str]:
    """Type names suggesting a period/year dimension (generic markers only)."""
    types: list[str] = []
    if isinstance(symbols, dict):
        raw = symbols.get("types") or []
    elif isinstance(symbols, list):
        raw = symbols
    else:
        return types
    for t in raw:
        if isinstance(t, dict):
            name = str(t.get("name") or "")
        else:
            name = str(t)
        nl = _normalize_blob(name)
        if any(m in nl for m in _PERIOD_TYPE_MARKERS):
            types.append(name)
    return types


def _is_temporal_relation_symbol(sym: dict[str, Any]) -> bool:
    name = str(sym.get("name") or "")
    name_l = _normalize_blob(name)
    desc_l = _normalize_blob(str(sym.get("description") or ""))
    kind = str(sym.get("kind") or "")
    lo = sym.get("legal_output")
    cat = str(sym.get("output_category") or "")
    if predicate_represents_legal_effect_output(
        name,
        description=str(sym.get("description") or ""),
        kind=kind,
        legal_output=lo if isinstance(lo, bool) else None,
        output_category=cat,
    ):
        return False
    if any(x in name_l for x in ("exceed", "criterion", "classification", "consequence", "effect", "apply")):
        if not any(m in name_l for m in _TEMPORAL_RELATION_NAME_MARKERS):
            return False
    relation_prefixes = (
        "prior_",
        "previous_",
        "preceding_",
        "following_",
        "next_",
        "successor_",
        "predecessor_",
        "consecutive_",
        "immediately_precedes",
        "immediately_follows",
    )
    if name_l in {
        "prior_financial_year",
        "previous_financial_year",
        "following_financial_year",
        "next_financial_year",
        "previous_period",
        "next_period",
        "prior_period",
        "following_period",
    }:
        return True
    if any(name_l.startswith(p) for p in relation_prefixes):
        return True
    args = sym.get("args") or []
    if len(args) >= 2 and kind in {"helper", "function"}:
        if sym.get("returns") in args and any(
            name_l.startswith(p) for p in ("prior_", "previous_", "preceding_", "following_", "next_")
        ):
            return True
    return False


def _symbol_decl_to_dict(sym: Any) -> dict[str, Any]:
    if isinstance(sym, dict):
        return sym
    return {
        "name": getattr(sym, "name", ""),
        "kind": getattr(sym, "kind", ""),
        "args": list(getattr(sym, "args", []) or []),
        "returns": getattr(sym, "returns", ""),
        "description": getattr(sym, "description", "") or "",
        "legal_output": getattr(sym, "legal_output", None),
        "output_category": getattr(sym, "output_category", "") or "",
        "directly_observable": getattr(sym, "directly_observable", False),
        "background": getattr(sym, "background", False),
        "case_input": getattr(sym, "case_input", False),
    }


def temporal_support_exempt_from_helper_definition(sym: dict[str, Any] | Any) -> bool:
    """
    Temporal period/year relations used in rule IF are structural case background,
    not legal-effect helpers that must be defined in rule THEN — unless explicitly derived.
    """
    d = _symbol_decl_to_dict(sym)
    if not _is_temporal_relation_symbol(d):
        return False
    kind = str(d.get("kind") or "")
    if kind in ("derived", "conclusion"):
        return False
    if d.get("legal_output") is True:
        return False
    if predicate_represents_legal_effect_output(
        str(d.get("name") or ""),
        description=str(d.get("description") or ""),
        kind=kind,
        legal_output=d.get("legal_output") if isinstance(d.get("legal_output"), bool) else None,
        output_category=str(d.get("output_category") or ""),
    ):
        return False
    return True


def find_temporal_support_symbols(symbols: dict | list | None) -> list[dict[str, str]]:
    """Predicates/functions that express previous/next/consecutive period relations."""
    out: list[dict[str, str]] = []
    for sym in _iter_symbol_dicts(symbols):
        if not sym.get("name"):
            continue
        if str(sym.get("kind")) == "type":
            continue
        if _is_temporal_relation_symbol(sym):
            out.append(
                {
                    "name": str(sym["name"]),
                    "kind": str(sym.get("kind") or ""),
                    "role": "temporal_relation",
                    "description": str(sym.get("description") or "")[:120],
                }
            )
    return out


def collect_legal_output_predicate_names(symbols: dict | list | None) -> list[str]:
    names: list[str] = []
    for sym in _iter_symbol_dicts(symbols):
        if not sym.get("name") or str(sym.get("kind")) == "type":
            continue
        name = str(sym["name"])
        if predicate_represents_legal_effect_output(
            name,
            description=str(sym.get("description") or ""),
            kind=str(sym.get("kind") or ""),
            legal_output=sym.get("legal_output") if isinstance(sym.get("legal_output"), bool) else None,
            output_category=str(sym.get("output_category") or ""),
        ):
            names.append(name)
    return names


def helper_name_requires_temporal_support(helper_name: str, description: str = "") -> bool:
    b = _normalize_blob(helper_name, description)
    if any(m in b for m in _HELPER_TEMPORAL_MARKERS):
        return True
    if "more_than_one" in b and any(x in b for x in ("year", "jaar", "period", "periode", "consecutive", "opeenvolg")):
        return True
    return False


def undeclared_temporal_funcs_in_rules(
    merged_ir: dict | None,
    symbol_table: dict | None,
) -> list[str]:
    if not merged_ir:
        return []
    declared = {
        str(f.get("name"))
        for f in (symbol_table or {}).get("functions") or []
        if isinstance(f, dict) and f.get("name")
    }
    declared |= {
        str(p.get("name"))
        for p in (symbol_table or {}).get("predicates") or []
        if isinstance(p, dict) and p.get("name")
    }
    found: set[str] = set()
    for rule in merged_ir.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        for block in (rule.get("if") or [], rule.get("then") or []):
            if not isinstance(block, list):
                continue
            for cond in block:
                if not isinstance(cond, dict):
                    continue
                cmp_node = cond.get("compare")
                if not isinstance(cmp_node, dict):
                    continue
                right = cmp_node.get("right")
                if isinstance(right, dict) and right.get("func"):
                    found.add(str(right["func"]))
    missing = []
    for fn in sorted(found):
        fn_l = _normalize_blob(fn)
        if fn not in declared and any(m in fn_l for m in _TEMPORAL_RELATION_NAME_MARKERS):
            missing.append(fn)
    return missing


def assess_temporal_support(
    symbols: dict | list | None,
    *,
    law_text: str | None = None,
    question_text: str | None = None,
    scope_metadata: dict | None = None,
    merged_ir: dict | None = None,
    helper_name: str | None = None,
    helper_description: str = "",
) -> TemporalEffectDetection:
    """Full assessment: phrases, types, legal-effect context, existing temporal symbols."""
    det = detect_temporal_effect_terms(
        law_text, question_text, scope_metadata=scope_metadata
    )
    period_types = find_period_like_types(symbols)
    det.period_like_types = period_types
    det.has_period_like_types = bool(period_types)
    temporal_syms = find_temporal_support_symbols(symbols)
    det.temporal_support_symbols = temporal_syms
    det.has_temporal_support_symbols = bool(temporal_syms)
    det.legal_output_predicates = collect_legal_output_predicate_names(symbols)

    if schema_has_legal_effect_output_predicate(_predicates_list(symbols)):
        det.legal_effect_context = True

    phrase_required = bool(det.detected_terms) and det.legal_effect_context
    helper_requires = (
        helper_name
        and helper_name_requires_temporal_support(helper_name, helper_description)
        and det.legal_effect_context
    )
    undeclared = undeclared_temporal_funcs_in_rules(merged_ir, symbols if isinstance(symbols, dict) else None)

    needs_support = (phrase_required or helper_requires or bool(undeclared)) and det.legal_effect_context
    det.requires_temporal_support = needs_support and not det.has_temporal_support_symbols
    return det


def _predicates_list(symbols: dict | list | None) -> list:
    if isinstance(symbols, dict):
        return list(symbols.get("predicates") or [])
    if isinstance(symbols, list):
        return [s for s in symbols if hasattr(s, "name") or (isinstance(s, dict) and s.get("kind") != "type")]
    return []


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
    """True when helper/temporal language needs period relations absent from symbols."""
    if not helper_name_requires_temporal_support(helper_name, description):
        if not undeclared_temporal_funcs_in_rules(merged_ir, symbol_table):
            return False
    det = assess_temporal_support(
        symbol_table,
        law_text=law_text,
        question_text=question_text,
        scope_metadata=scope_metadata,
        merged_ir=merged_ir,
        helper_name=helper_name,
        helper_description=description,
    )
    if det.has_temporal_support_symbols:
        return False
    if helper_name_requires_temporal_support(helper_name, description) and det.legal_effect_context:
        return True
    if undeclared_temporal_funcs_in_rules(merged_ir, symbol_table):
        return True
    return det.requires_temporal_support and helper_name_requires_temporal_support(helper_name, description)


_LEGAL_EFFECT_TEMPORAL_NAME_MARKERS: tuple[str, ...] = (
    "following",
    "previous",
    "preceding",
    "prior",
    "consecutive",
    "next_",
    "successor",
    "predecessor",
    "immediately_following",
    "immediately_preceding",
    "opeenvolg",
    "achtereenvolg",
    "volgend",
    "daaropvolg",
    "voorafgaand",
)


def legal_effect_predicates_masquerading_as_temporal(
    symbols: dict | list | None,
) -> list[str]:
    """
    Legal-output predicate names that embed temporal words but are not period relations.
    """
    names: list[str] = []
    for sym in _iter_symbol_dicts(symbols):
        if not sym.get("name") or str(sym.get("kind")) == "type":
            continue
        name = str(sym["name"])
        if _is_temporal_relation_symbol(sym):
            continue
        if not predicate_represents_legal_effect_output(
            name,
            description=str(sym.get("description") or ""),
            kind=str(sym.get("kind") or ""),
            legal_output=sym.get("legal_output") if isinstance(sym.get("legal_output"), bool) else None,
            output_category=str(sym.get("output_category") or ""),
        ):
            continue
        name_l = _normalize_blob(name)
        if any(m in name_l for m in _LEGAL_EFFECT_TEMPORAL_NAME_MARKERS):
            names.append(name)
    return names


def _raise_missing_temporal_support_symbol(
    *,
    detection: TemporalEffectDetection,
    law_text_for_lints: str | None,
    masquerading_legal_effect_names: list[str] | None = None,
) -> None:
    from pipeline.kb.json_ir import JSONIRCompilationError, SCHEMA_DESIGN_TAG

    if masquerading_legal_effect_names:
        sample = ", ".join(masquerading_legal_effect_names[:3])
        raise JSONIRCompilationError(
            SCHEMA_DESIGN_TAG
            + ": Legal-effect predicate names do not count as temporal support. "
            "Add a separate relation/function between periods "
            "(e.g. next_financial_year(FinancialYear, FinancialYear), previous_period(Period, Period)). "
            f"Misclassified names: {sample}. "
            "Repair layer: symbols."
        )

    terms = ", ".join(detection.detected_terms[:4]) if detection.detected_terms else "following/previous/consecutive periods"
    period_types = ", ".join(detection.period_like_types[:3]) if detection.period_like_types else "(none declared)"
    snippet = (law_text_for_lints or "").strip()
    if len(snippet) > 100:
        snippet = snippet[:97] + "..."
    raise JSONIRCompilationError(
        SCHEMA_DESIGN_TAG
        + ": The scoped law/question requires reasoning over previous, following, or consecutive "
        "periods"
        + (f' ("{snippet}")' if snippet else "")
        + ", but the symbol table has no temporal support relation/function "
        f"(e.g. previous_period, next_period, consecutive_periods between period types). "
        f"Detected temporal phrases: {terms}. Period-like types: {period_types}. "
        "Add a generic temporal relation using existing period/year types. "
        "Rules repair cannot define consecutive/following-period helpers without this vocabulary. "
        "Repair layer: symbols."
    )


def validate_temporal_support_symbols_stage(
    predicates: list,
    functions: list,
    types: list | None,
    *,
    law_text_for_lints: str | None,
    scope_metadata: dict | None = None,
    question_text: str | None = None,
    following_missing_temporal_support_repair: bool = False,
) -> None:
    """
    Symbol-table stage: fail when temporal-effect language requires period relations
    but no temporal support symbols exist.
    """
    sym_dict = {
        "types": [{"name": t} if isinstance(t, str) else t for t in (types or [])],
        "predicates": [_sym_to_dict(p) for p in predicates],
        "functions": [_sym_to_dict(f) for f in functions],
    }
    det = assess_temporal_support(
        sym_dict,
        law_text=law_text_for_lints,
        question_text=question_text,
        scope_metadata=scope_metadata,
    )
    if not det.detected_terms:
        return
    if not det.legal_effect_context:
        return
    if det.has_temporal_support_symbols:
        return
    if not det.has_period_like_types:
        return
    masquerade: list[str] = []
    if following_missing_temporal_support_repair:
        masquerade = legal_effect_predicates_masquerading_as_temporal(sym_dict)
    _raise_missing_temporal_support_symbol(
        detection=det,
        law_text_for_lints=law_text_for_lints,
        masquerading_legal_effect_names=masquerade if masquerade else None,
    )


def _sym_to_dict(sym: Any) -> dict:
    if isinstance(sym, dict):
        return sym
    return {
        "name": sym.name,
        "kind": sym.kind,
        "args": list(sym.args),
        "returns": sym.returns,
        "description": getattr(sym, "description", "") or "",
        "legal_output": getattr(sym, "legal_output", None),
        "output_category": getattr(sym, "output_category", "") or "",
    }
