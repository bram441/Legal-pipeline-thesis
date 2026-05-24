"""Targeted repair prompt supplement for missing legal-effect output predicates."""

from __future__ import annotations

import json
import re

from pipeline.kb.legal_effect import (
    _STRONG_LAW_EFFECT_RE,
    predicate_looks_like_classification_output,
    predicate_represents_legal_effect_output,
)

_ENTITY_TYPE_HINTS = ("Company", "FinancialYear", "Entity", "Period", "Amount")


def extract_effect_snippet_from_law(law_text: str | None, *, max_len: int = 220) -> str:
    """Short quote from scoped law text around effect/timing language."""
    text = (law_text or "").strip()
    if not text:
        return ""
    m = _STRONG_LAW_EFFECT_RE.search(text)
    if not m:
        return text[:max_len].strip()
    start = text.rfind(".", 0, m.start())
    start = 0 if start < 0 else start + 1
    end = text.find(".", m.end())
    if end < 0:
        end = min(len(text), m.end() + max_len)
    snippet = " ".join(text[start:end].split())
    if len(snippet) > max_len:
        snippet = snippet[: max_len - 3].rstrip() + "..."
    return snippet


def _tokens_for_name_generation(text: str) -> list[str]:
    parts = re.split(r"[^a-z0-9]+", (text or "").lower())
    stop = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "from",
        "for",
        "in",
        "of",
        "to",
        "that",
        "which",
        "when",
        "year",
        "financial",
        "article",
        "paragraph",
        "company",
        "companies",
    }
    out: list[str] = []
    for p in parts:
        if len(p) < 3 or p in stop:
            continue
        if p not in out:
            out.append(p)
    return out


def suggest_legal_effect_predicate_names(
    law_text: str | None,
    question_text: str | None = None,
) -> list[str]:
    """
    Law-agnostic predicate name shapes derived from effect wording (not hardcoded statutes).
    """
    blob = ((law_text or "") + " " + (question_text or "")).lower()
    toks = _tokens_for_name_generation(blob)
    suggestions: list[str] = []

    def _add(name: str) -> None:
        if name and name not in suggestions:
            suggestions.append(name)

    has_consequence = any(t in toks for t in ("consequences", "consequence", "gevolgen"))
    has_effect = "effect" in toks or "effects" in toks or "rechtsgevolg" in toks
    has_following = any(t in toks for t in ("following", "next", "volgende", "daaropvolgende"))
    has_apply = any(t in toks for t in ("apply", "applies", "applied", "toepassing", "vanaf"))
    has_timing = any(t in toks for t in ("timing", "period", "year", "boekjaar", "financial"))
    has_account = any(t in toks for t in ("account", "aanmerking", "taken"))
    has_immediate = "immediately" in toks or "onmiddellijk" in toks

    if has_consequence and has_following:
        _add("consequences_apply_from_following_financial_year")
    if has_consequence and has_apply:
        _add("legal_consequences_apply_from_period")
        _add("provision_consequences_apply_from")
    if has_effect and (has_apply or has_timing):
        _add("legal_effect_takes_effect_from")
    if has_account and has_immediate:
        _add("amount_must_be_taken_into_account_immediately")
    if has_consequence:
        _add("legal_consequences_apply")
    if has_effect:
        _add("legal_effect_applies_from_trigger_period")

    if not suggestions:
        _add("legal_effect_applies_from_period")
        _add("provision_legal_consequence_applies")

    return suggestions[:6]


def _infer_entity_period_types(symbol_table: dict | None) -> tuple[str, str]:
    types: list[str] = []
    if symbol_table:
        for t in symbol_table.get("types") or []:
            if isinstance(t, str):
                types.append(t)
            elif isinstance(t, dict) and t.get("name"):
                types.append(str(t["name"]))
    entity = next((t for t in types if t in _ENTITY_TYPE_HINTS), types[0] if types else "Entity")
    period = next(
        (t for t in types if t in ("FinancialYear", "Period", "Year")),
        types[1] if len(types) > 1 else "Period",
    )
    return entity, period


def list_classification_predicate_names(symbol_table: dict | None) -> list[str]:
    names: list[str] = []
    if not symbol_table:
        return names
    for p in symbol_table.get("predicates") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "")
        if not name:
            continue
        if predicate_looks_like_classification_output(
            name,
            description=str(p.get("description") or ""),
            kind=str(p.get("kind") or ""),
            legal_output=p.get("legal_output") if isinstance(p.get("legal_output"), bool) else None,
            output_category=str(p.get("output_category") or ""),
        ):
            names.append(name)
    return names


def scope_has_classification_and_effect_paragraphs(scope_metadata: dict | None) -> bool:
    if not scope_metadata:
        return False
    if not scope_metadata.get("contains_effect_language"):
        return False
    deps = scope_metadata.get("included_dependency_chunks") or []
    if deps:
        return True
    cited_par = scope_metadata.get("cited_paragraph")
    return cited_par == 2 or scope_metadata.get("selected_granularity") == "paragraph"


def build_missing_legal_effect_repair_supplement(
    error_message: str,
    *,
    law_text: str | None = None,
    question_text: str | None = None,
    scope_metadata: dict | None = None,
    symbol_table: dict | None = None,
) -> str:
    effect_snippet = extract_effect_snippet_from_law(law_text)
    question = (question_text or "").strip()
    entity_t, period_t = _infer_entity_period_types(symbol_table)
    candidates = suggest_legal_effect_predicate_names(law_text, question_text)
    classification_only = list_classification_predicate_names(symbol_table)

    lines = [
        "MISSING LEGAL-EFFECT OUTPUT PREDICATE — SYMBOLS REPAIR (mandatory)",
        "",
        "The scoped law text asks about legal consequences, timing, applicability, or similar effect language.",
        "A symbol table with only classification predicates (e.g. is_small_company, is_micro_company) "
        "or threshold helpers is insufficient.",
        "",
        "Open-world warning: do NOT answer an effect/timing legal question using "
        "is_small_company / is_micro_company / classification predicates alone.",
        "Absence of proof for a favorable classification is not a legal-effect answer.",
    ]
    if effect_snippet:
        lines.extend(["", "Effect phrase from scoped law text:", "  \"%s\"" % effect_snippet])
    if question:
        lines.extend(["", "Legal question (must target a legal-effect output predicate):", "  \"%s\"" % question])
    if scope_has_classification_and_effect_paragraphs(scope_metadata):
        lines.extend(
            [
                "",
                "Scoped law includes BOTH a classification paragraph and an effect/timing paragraph:",
                "  - KEEP existing classification predicates (is_* company size) as intermediate support.",
                "  - ADD a separate derived legal-effect output predicate for paragraph 2 effect language.",
                "  - Rules repair (later) must define the legal-effect predicate from the effect antecedents.",
            ]
        )
    if classification_only:
        lines.extend(
            [
                "",
                "Current classification-only predicates (keep, do not use as sole query target): "
                + ", ".join(classification_only[:6]),
            ]
        )
    lines.extend(
        [
            "",
            "Add ONE new derived predicate (examples — pick a name that matches the law wording):",
        ]
    )
    for name in candidates:
        lines.append(
            "  - %s(%s, %s)  kind=derived  legal_output=true  output_category=\"legal_effect\" or \"timing\""
            % (name, entity_t.lower(), period_t.lower())
        )
    lines.extend(
        [
            "",
            "Required JSON IR metadata on the new predicate:",
            "  \"kind\": \"derived\"",
            "  \"legal_output\": true",
            "  \"output_category\": \"legal_effect\"  (or \"timing\" / \"consequence\" when appropriate)",
            "  \"description\": short phrase mirroring the effect language in the scoped law text",
            "",
            "Do not remove observables or classification predicates needed to support the effect rule later.",
        ]
    )
    return "\n".join(lines)


def parse_symbol_table_from_repair_context(previous_output: str) -> dict | None:
    """Best-effort parse of symbol JSON from repair context string."""
    text = (previous_output or "").strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and "predicates" in obj:
            return obj
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict) and "predicates" in obj:
                return obj
        except json.JSONDecodeError:
            return None
    return None
