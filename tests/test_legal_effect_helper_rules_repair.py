"""Rules repair for missing helpers in legal-effect contexts."""

from __future__ import annotations

from pipeline.kb.json_ir_compile_loop import _build_repair_hints
from pipeline.kb.json_ir_repair import normalize_error_code
from pipeline.kb.legal_effect_helper_repair_hints import (
    build_missing_legal_effect_helper_supplement,
    classify_helper_kind_hint,
    legal_effect_rules_repair_context,
)
from pipeline.kb.validation_evidence import collect_missing_helper_evidence

_EFFECT_SCOPE = {
    "contains_effect_language": True,
    "question_asks_legal_effect": True,
}

_ERR = (
    "JSON_IR_RULE_DESIGN_ERROR: Helper predicate 'exceeds_more_than_one_criterion_two_consecutive_years' "
    "is used as a rule condition but has no defining rule (never appears in any rule THEN)."
)

_SYMBOLS = {
    "types": ["Company", "FinancialYear"],
    "predicates": [
        {"name": "exceeds_more_than_one_criterion", "kind": "helper", "args": ["Company", "FinancialYear"], "returns": "Bool"},
        {
            "name": "exceeds_more_than_one_criterion_two_consecutive_years",
            "kind": "helper",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
        },
        {
            "name": "legal_consequences_apply",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "legal_output": True,
            "output_category": "legal_effect",
        },
    ],
    "functions": [
        {"name": "annual_net_turnover", "kind": "observable", "args": ["Company", "FinancialYear"], "returns": "Real"},
    ],
}

_MERGED_IR = {
    "types": _SYMBOLS["types"],
    "predicates": _SYMBOLS["predicates"],
    "functions": _SYMBOLS["functions"],
    "rules": [
        {
            "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
            "if": [{"pred": "exceeds_more_than_one_criterion_two_consecutive_years", "args": ["c", "fy"]}],
            "then": [{"pred": "legal_consequences_apply", "args": ["c", "fy"]}],
            "operator": "implies",
        }
    ],
}


def test_missing_helper_legal_effect_evidence_and_supplement():
    pred_kinds = {p["name"]: p["kind"] for p in _SYMBOLS["predicates"]}
    evidence = collect_missing_helper_evidence(
        _MERGED_IR,
        pred_kinds,
        error_message=_ERR,
        symbol_table=_SYMBOLS,
        scope_metadata=_EFFECT_SCOPE,
    )
    assert evidence is not None
    assert evidence.helper_name == "exceeds_more_than_one_criterion_two_consecutive_years"
    assert evidence.legal_effect_context is True
    assert evidence.derives_legal_output is True
    assert "legal_consequences_apply" in evidence.legal_output_predicates_in_then
    assert evidence.helper_kind_hint == "composite_temporal_threshold"
    assert "consecutive" in evidence.helper_kind_hints

    supplement = build_missing_legal_effect_helper_supplement(
        error_message=_ERR,
        symbol_table=_SYMBOLS,
        evidence=evidence,
    )
    assert "You are repairing rules only" in supplement
    assert "legal-effect output predicate already exists" in supplement
    assert "legal_consequences_apply" in supplement
    assert "rules[0]" in supplement

    hints = _build_repair_hints(
        _ERR,
        "",
        error_code="missing_helper_definition",
        layer="rules",
        scope_metadata=_EFFECT_SCOPE,
        symbol_table=_SYMBOLS,
        missing_helper_evidence=evidence,
    )
    assert (
        "MISSING HELPER FOR LEGAL-EFFECT RULE" in hints
        or "COMPOSITE THRESHOLD/TEMPORAL HELPER" in hints
        or "MISSING TEMPORAL SUPPORT SYMBOL" in hints
    )
    assert evidence.missing_temporal_support_symbol is True
    assert "legal-effect" in hints.lower() or "legal effect" in hints.lower()
    assert normalize_error_code(_ERR) == "missing_helper_definition"


def test_threshold_helper_hint_in_supplement():
    supplement = build_missing_legal_effect_helper_supplement(
        error_message="Helper predicate 'exceeds_balance_sheet_threshold'",
        symbol_table=_SYMBOLS,
        evidence=None,
    )
    assert classify_helper_kind_hint("exceeds_balance_sheet_threshold") == "threshold"
    assert "numeric compare" in supplement.lower() or "threshold" in supplement.lower()


def test_temporal_helper_hint_in_supplement():
    supplement = build_missing_legal_effect_helper_supplement(
        error_message="Helper predicate 'applies_from_following_financial_year'",
        symbol_table=_SYMBOLS,
        evidence=None,
    )
    assert classify_helper_kind_hint("applies_from_following_financial_year") in {
        "temporal",
        "following_period",
    }
    assert "period" in supplement.lower() or "year" in supplement.lower()


def test_non_legal_effect_missing_helper_unchanged():
    symbols = {
        "types": ["Entity"],
        "predicates": [
            {"name": "aux_helper", "kind": "helper", "args": ["Entity"], "returns": "Bool"},
            {"name": "some_derived", "kind": "derived", "args": ["Entity"], "returns": "Bool"},
        ],
        "functions": [],
    }
    scope = {"contains_effect_language": False, "question_asks_legal_effect": False}
    err = "Helper predicate 'aux_helper' is used as a rule condition but has no defining rule"
    assert not legal_effect_rules_repair_context(
        scope_metadata=scope,
        symbol_table=symbols,
        error_message=err,
    )
    hints = _build_repair_hints(
        err,
        "",
        error_code="missing_helper_definition",
        layer="rules",
        scope_metadata=scope,
        symbol_table=symbols,
    )
    assert "MISSING HELPER FOR LEGAL-EFFECT RULE" not in hints
    assert "missing_helper_definition_for_legal_effect" not in hints
