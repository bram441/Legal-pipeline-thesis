"""Composite threshold + temporal/consecutive helper repair hints and evidence."""

from __future__ import annotations

from pipeline.kb.composite_temporal_threshold_repair_hints import (
    build_composite_temporal_threshold_supplement,
    build_missing_temporal_support_symbol_supplement,
    diagnose_missing_temporal_support,
    qualifies_for_composite_temporal_threshold_card,
)
from pipeline.kb.json_ir_compile_loop import _build_repair_hints
from pipeline.kb.json_ir_repair import JsonIRErrorKind, classify_json_ir_validation_error
from pipeline.kb.repair_cards import format_repair_card
from pipeline.kb.validation_evidence import collect_missing_helper_evidence

_EFFECT_SCOPE = {
    "contains_effect_language": True,
    "question_asks_legal_effect": True,
}

_ERR = (
    "JSON_IR_RULE_DESIGN_ERROR: Helper predicate 'exceeds_more_than_one_criterion_two_consecutive_years' "
    "is used as a rule condition but has no defining rule (never appears in any rule THEN)."
)

_SYMBOLS_WITH_TEMPORAL = {
    "types": ["Company", "FinancialYear"],
    "predicates": [
        {"name": "exceeds_employee_threshold", "kind": "helper", "args": ["Company", "FinancialYear"], "returns": "Bool"},
        {"name": "exceeds_net_turnover_threshold", "kind": "helper", "args": ["Company", "FinancialYear"], "returns": "Bool"},
        {"name": "exceeds_balance_sheet_total_threshold", "kind": "helper", "args": ["Company", "FinancialYear"], "returns": "Bool"},
        {"name": "exceeds_more_than_one_criterion", "kind": "helper", "args": ["Company", "FinancialYear"], "returns": "Bool"},
        {
            "name": "exceeds_more_than_one_criterion_two_consecutive_years",
            "kind": "helper",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
        },
        {
            "name": "legal_consequences_apply_from_following_financial_year",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "legal_output": True,
            "output_category": "legal_effect",
        },
    ],
    "functions": [
        {"name": "prior_financial_year", "kind": "helper", "args": ["FinancialYear"], "returns": "FinancialYear"},
        {"name": "annual_net_turnover_excluding_vat", "kind": "observable", "args": ["Company", "FinancialYear"], "returns": "Real"},
    ],
}

_SYMBOLS_NO_TEMPORAL = {
    "types": _SYMBOLS_WITH_TEMPORAL["types"],
    "predicates": _SYMBOLS_WITH_TEMPORAL["predicates"],
    "functions": [
        {
            "name": "annual_net_turnover_excluding_vat",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Real",
        },
    ],
}

_MERGED_IR = {
    "types": _SYMBOLS_WITH_TEMPORAL["types"],
    "predicates": _SYMBOLS_WITH_TEMPORAL["predicates"],
    "functions": _SYMBOLS_WITH_TEMPORAL["functions"],
    "rules": [
        {
            "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
            "if": [{"pred": "exceeds_more_than_one_criterion_two_consecutive_years", "args": ["c", "fy"]}],
            "then": [{"pred": "legal_consequences_apply_from_following_financial_year", "args": ["c", "fy"]}],
            "operator": "implies",
        }
    ],
}


def test_composite_helper_evidence_with_temporal_candidates():
    pred_kinds = {p["name"]: p["kind"] for p in _SYMBOLS_WITH_TEMPORAL["predicates"]}
    evidence = collect_missing_helper_evidence(
        _MERGED_IR,
        pred_kinds,
        error_message=_ERR,
        symbol_table=_SYMBOLS_WITH_TEMPORAL,
        scope_metadata=_EFFECT_SCOPE,
    )
    assert evidence is not None
    assert evidence.helper_name == "exceeds_more_than_one_criterion_two_consecutive_years"
    assert "composite_temporal_threshold" in evidence.helper_kind_hints
    assert evidence.helper_kind_hint == "composite_temporal_threshold"
    assert evidence.used_in_legal_output_rule is True
    assert evidence.missing_temporal_support_symbol is False
    assert any(c["name"] == "prior_financial_year" for c in evidence.temporal_relation_candidates)
    assert any(
        c.get("role") == "threshold_helper"
        for c in evidence.threshold_helper_candidates
    )

    assert qualifies_for_composite_temporal_threshold_card(
        helper_name=evidence.helper_name,
        scope_metadata=_EFFECT_SCOPE,
        derives_legal_output=True,
    )

    card = format_repair_card("missing_helper_definition_for_composite_temporal_threshold")
    assert "pairwise" in card.lower()

    hints = _build_repair_hints(
        _ERR,
        "",
        error_code="missing_helper_definition",
        layer="rules",
        scope_metadata=_EFFECT_SCOPE,
        symbol_table=_SYMBOLS_WITH_TEMPORAL,
        missing_helper_evidence=evidence,
    )
    assert "COMPOSITE THRESHOLD/TEMPORAL HELPER" in hints
    assert "Missing composite threshold/temporal helper" in hints


def test_missing_temporal_support_escalates_to_symbols():
    pred_kinds = {p["name"]: p["kind"] for p in _SYMBOLS_NO_TEMPORAL["predicates"]}
    ir = {
        **_MERGED_IR,
        "functions": _SYMBOLS_NO_TEMPORAL["functions"],
    }
    evidence = collect_missing_helper_evidence(
        ir,
        pred_kinds,
        error_message=_ERR,
        symbol_table=_SYMBOLS_NO_TEMPORAL,
        scope_metadata=_EFFECT_SCOPE,
    )
    assert evidence is not None
    assert evidence.missing_temporal_support_symbol is True
    assert not evidence.temporal_relation_candidates
    assert diagnose_missing_temporal_support(
        evidence.helper_name,
        symbol_table=_SYMBOLS_NO_TEMPORAL,
        merged_ir=ir,
    )

    sym_hints = _build_repair_hints(
        _ERR,
        "",
        error_code="missing_helper_definition",
        layer="symbols",
        scope_metadata=_EFFECT_SCOPE,
        symbol_table=_SYMBOLS_NO_TEMPORAL,
        missing_helper_evidence=evidence,
    )
    assert "MISSING TEMPORAL SUPPORT" in sym_hints
    assert "Symbols repair" in sym_hints or "symbols repair" in sym_hints.lower()

    route = classify_json_ir_validation_error(_ERR)
    assert route == JsonIRErrorKind.RULES_REPAIR_ONLY
    supplement = build_missing_temporal_support_symbol_supplement(evidence=evidence)
    assert "prior" in supplement.lower() or "temporal" in supplement.lower()


def test_composite_supplement_includes_decomposition():
    pred_kinds = {p["name"]: p["kind"] for p in _SYMBOLS_WITH_TEMPORAL["predicates"]}
    evidence = collect_missing_helper_evidence(
        _MERGED_IR,
        pred_kinds,
        error_message=_ERR,
        symbol_table=_SYMBOLS_WITH_TEMPORAL,
        scope_metadata=_EFFECT_SCOPE,
    )
    supplement = build_composite_temporal_threshold_supplement(
        error_message=_ERR,
        symbol_table=_SYMBOLS_WITH_TEMPORAL,
        evidence=evidence,
    )
    assert "per-criterion exceeded" in supplement.lower()
    assert "pairwise" in supplement.lower()
    assert "two-consecutive" in supplement.lower() or "two consecutive" in supplement.lower()
    assert "legal-effect output" in supplement.lower() or "legal-effect" in supplement.lower()


def test_non_temporal_missing_helper_unchanged():
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
    ir = {
        "types": symbols["types"],
        "predicates": symbols["predicates"],
        "functions": [],
        "rules": [
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"pred": "aux_helper", "args": ["x"]}],
                "then": [{"pred": "some_derived", "args": ["x"]}],
                "operator": "implies",
            }
        ],
    }
    pred_kinds = {p["name"]: p["kind"] for p in symbols["predicates"]}
    evidence = collect_missing_helper_evidence(
        ir,
        pred_kinds,
        error_message=err,
        symbol_table=symbols,
        scope_metadata=scope,
    )
    assert evidence is not None
    assert "composite_temporal_threshold" not in evidence.helper_kind_hints
    assert not qualifies_for_composite_temporal_threshold_card(
        helper_name="aux_helper",
        scope_metadata=scope,
    )
    hints = _build_repair_hints(
        err,
        "",
        error_code="missing_helper_definition",
        layer="rules",
        scope_metadata=scope,
        symbol_table=symbols,
        missing_helper_evidence=evidence,
    )
    assert "COMPOSITE THRESHOLD/TEMPORAL HELPER" not in hints
    assert "MISSING HELPER FOR LEGAL-EFFECT RULE" not in hints
