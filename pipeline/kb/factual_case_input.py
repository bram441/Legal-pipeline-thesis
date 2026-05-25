"""Classify controlled case-given factual threshold/criterion inputs (law-agnostic)."""

from __future__ import annotations

import re
from typing import Any

from pipeline.kb.composite_predicate_heuristics import looks_computed_composite
from pipeline.kb.json_ir import _iter_pred_atoms_with_args, _rule_expr_sides
from pipeline.kb.legal_effect import (
    predicate_looks_like_classification_output,
    predicate_represents_legal_effect_output,
)

CASE_GIVEN_PREFIX = "case_given_"

_LEGAL_CONSEQUENCE_NAME = re.compile(
    r"(?i)(consequences?_apply|legal_effect|apply_from|entitled|has_right|"
    r"obligation_applies|permission_exists|prohibition_applies|is_entitled)"
)

_FACTUAL_THRESHOLD_TOKENS = frozenset(
    {
        "exceed",
        "exceeds",
        "exceeded",
        "threshold",
        "criterion",
        "criteria",
        "consecutive",
        "satisfies",
        "satisfied",
        "meets",
        "within_limit",
        "above_limit",
        "below_limit",
        "more_than",
        "no_more_than",
        "at_least",
        "no_longer",
        "overschrijdt",
        "drempel",
        "criterium",
    }
)

_CLASSIFICATION_STATUS_TOKENS = frozenset(
    {
        "is_micro",
        "is_small",
        "is_large",
        "qualifies",
        "eligible",
        "micro_company",
        "small_company",
        "classification",
    }
)


def case_given_predicate_name(base_name: str) -> str:
    base = str(base_name or "").strip()
    if not base:
        return ""
    if base.startswith(CASE_GIVEN_PREFIX):
        return base
    return CASE_GIVEN_PREFIX + base


def _name_tokens(name: str) -> set[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(name or ""))
    s = s.replace("_", " ").replace("-", " ")
    return {t.lower() for t in s.split() if len(t) >= 3}


def _has_factual_threshold_lexicon(name: str, description: str = "") -> bool:
    toks = _name_tokens(name) | _name_tokens(description)
    return bool(toks & _FACTUAL_THRESHOLD_TOKENS)


def _looks_legal_consequence_name(name: str) -> bool:
    return bool(_LEGAL_CONSEQUENCE_NAME.search(str(name or "")))


def _predicate_in_rule_antecedents(name: str, kb_schema: dict | None) -> bool:
    target = str(name or "").strip()
    if not target or not isinstance(kb_schema, dict):
        return False
    for rule in kb_schema.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        if_side, _ = _rule_expr_sides(rule)
        for atom in _iter_pred_atoms_with_args(if_side):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if pn == target:
                return True
    return False


def is_factual_case_input_candidate(sig: dict[str, Any] | None, kb_schema: dict | None = None) -> bool:
    """
    True when a helper/composite predicate may be asserted from explicit case text
    as externally provided threshold/criterion satisfaction (not a legal conclusion).
    """
    if not isinstance(sig, dict) or not sig.get("name"):
        return False
    name = str(sig["name"])
    description = str(sig.get("description") or "")
    kind = str(sig.get("kind") or "").strip().lower()

    if sig.get("legal_output") is True:
        return False

    lo = sig.get("legal_output") if isinstance(sig.get("legal_output"), bool) else None
    if predicate_represents_legal_effect_output(
        name,
        description=description,
        kind=kind,
        legal_output=lo,
        output_category=str(sig.get("output_category") or ""),
    ):
        return False

    if _looks_legal_consequence_name(name):
        return False

    if predicate_looks_like_classification_output(
        name,
        description=description,
        kind=kind,
        legal_output=lo,
        output_category=str(sig.get("output_category") or ""),
    ):
        if not _has_factual_threshold_lexicon(name, description):
            return False
        if any(t in _name_tokens(name) for t in _CLASSIFICATION_STATUS_TOKENS):
            return False

    if not _has_factual_threshold_lexicon(name, description):
        return False

    if not looks_computed_composite(name, description) and kind not in {"helper", "derived"}:
        return False

    if kind in {"observable", "input"}:
        return False

    if kind in {"helper", "derived", "conclusion"}:
        if kb_schema and not _predicate_in_rule_antecedents(name, kb_schema):
            return False
        return True

    return False


def _case_text_supports_predicate(
    case_text: str | None,
    pred: str,
    sig: dict[str, Any],
    *,
    evidence_text: str | None = None,
) -> tuple[bool, str]:
    from pipeline.extraction.ir_utils import question_tokens, symbol_tokens
    from pipeline.kb.evidence_text import (
        evidence_text_supported_in_case,
        normalize_text_for_evidence_match,
    )

    if evidence_text and str(evidence_text).strip():
        snippet = str(evidence_text).strip()
        if not evidence_text_supported_in_case(case_text, snippet):
            return False, ""
        # Return original snippet when possible; else normalized match is enough.
        low_case = str(case_text or "").lower()
        if snippet.lower() in low_case:
            return True, snippet
        norm_snip = normalize_text_for_evidence_match(snippet)
        for sent in re.split(r"(?<=[.!?])\s+", str(case_text or "").strip()):
            if norm_snip and norm_snip in normalize_text_for_evidence_match(sent):
                return True, sent.strip()
        return True, snippet

    if not case_text:
        return False, ""

    case_tokens = question_tokens(case_text) | set(symbol_tokens(case_text))
    pred_tokens = set(symbol_tokens(pred)) | set(symbol_tokens(str(sig.get("description") or "")))
    overlap = len(case_tokens & pred_tokens)
    if overlap < 2:
        return False, ""

    for sent in re.split(r"(?<=[.!?])\s+", case_text.strip()):
        low = sent.lower()
        hits = sum(1 for t in pred_tokens if t in low)
        if hits >= 2:
            return True, sent.strip()
    return False, ""


def case_text_explicitly_supports_factual_input(
    case_text: str | None,
    pred: str,
    sig: dict[str, Any],
    *,
    evidence_text: str | None = None,
) -> tuple[bool, str]:
    """Return (supported, evidence_snippet). Does not allow numeric invention."""
    if not is_factual_case_input_candidate(sig):
        return False, ""
    return _case_text_supports_predicate(case_text, pred, sig, evidence_text=evidence_text)


def is_query_or_legal_output_predicate(
    sig: dict[str, Any] | None,
    *,
    query_predicate: str | None = None,
) -> bool:
    if not isinstance(sig, dict):
        return False
    name = str(sig.get("name") or "")
    if query_predicate and name == str(query_predicate).strip():
        return True
    if sig.get("legal_output") is True:
        return True
    lo = sig.get("legal_output") if isinstance(sig.get("legal_output"), bool) else None
    return predicate_represents_legal_effect_output(
        name,
        description=str(sig.get("description") or ""),
        kind=str(sig.get("kind") or ""),
        legal_output=lo,
        output_category=str(sig.get("output_category") or ""),
    )
