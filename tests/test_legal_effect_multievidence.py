"""Multi-error validation evidence for legal-effect KBs."""

from __future__ import annotations

from pipeline.kb.json_ir_compile_loop import _build_repair_hints
from pipeline.kb.json_ir_repair import normalize_error_code
from pipeline.kb.legal_effect_helper_repair_hints import build_legal_effect_computed_helper_supplement
from pipeline.kb.repair_cards import format_repair_card
from pipeline.kb.validation_evidence import collect_validation_repair_evidence

_EFFECT_SCOPE = {
    "contains_effect_language": True,
    "question_asks_legal_effect": True,
}

_COMPUTED_ERR = (
    "JSON_IR_SCHEMA_DESIGN_ERROR: Predicate 'exceeds_employee_threshold' (kind=observable) "
    "looks computed/composite (threshold, count, exceeds/meets/satisfies-style condition)."
)

_SYMBOLS = {
    "types": ["Company", "FinancialYear"],
    "predicates": [
        {
            "name": "exceeds_employee_threshold",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
        },
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
        {
            "name": "annual_average_number_of_employees",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Int",
        },
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


def test_computed_observable_primary_with_secondary_missing_helper():
    pred_kinds = {p["name"]: p["kind"] for p in _SYMBOLS["predicates"]}
    evidence = collect_validation_repair_evidence(
        _MERGED_IR,
        pred_kinds,
        law_text_for_lints="threshold 50 employees",
        error_message=_COMPUTED_ERR,
        symbol_table=_SYMBOLS,
        scope_metadata=_EFFECT_SCOPE,
    )
    assert normalize_error_code(_COMPUTED_ERR) == "computed_observable_unsafe"
    assert evidence.computed_observable_predicate == "exceeds_employee_threshold"
    assert evidence.computed_observable_helper_kind_hint == "threshold"
    assert len(evidence.secondary_missing_helpers) >= 1
    sec = evidence.secondary_missing_helpers[0]
    assert sec.helper_name == "exceeds_more_than_one_criterion_two_consecutive_years"
    assert sec.is_secondary is True
    assert sec.derives_legal_output is True

    diag = evidence.format_secondary_diagnostics()
    assert "secondary missing_helper_definition" in diag
    assert "exceeds_more_than_one_criterion_two_consecutive_years" in diag

    hints = _build_repair_hints(
        _COMPUTED_ERR,
        "",
        error_code="computed_observable_unsafe",
        layer="symbols",
        scope_metadata=_EFFECT_SCOPE,
        symbol_table=_SYMBOLS,
        secondary_diagnostics=diag,
        validation_evidence=evidence,
    )
    assert "SECONDARY VALIDATION DIAGNOSTICS" in hints
    assert "LEGAL-EFFECT COMPUTED HELPER" in hints
    assert "legal_consequences_apply" in hints
    assert "computed_observable_unsafe_for_legal_effect" in hints or "legal effect" in hints.lower()


def test_computed_observable_outside_legal_effect_unchanged():
    symbols = {
        "types": ["Entity"],
        "predicates": [
            {"name": "exceeds_limit", "kind": "observable", "args": ["Entity"], "returns": "Bool"},
            {"name": "some_derived", "kind": "derived", "args": ["Entity"], "returns": "Bool"},
        ],
        "functions": [],
    }
    scope = {"contains_effect_language": False, "question_asks_legal_effect": False}
    err = _COMPUTED_ERR.replace("exceeds_employee_threshold", "exceeds_limit")
    evidence = collect_validation_repair_evidence(
        {"types": ["Entity"], "predicates": symbols["predicates"], "functions": [], "rules": []},
        {"exceeds_limit": "observable", "some_derived": "derived"},
        law_text_for_lints="",
        error_message=err,
        symbol_table=symbols,
        scope_metadata=scope,
    )
    assert evidence.secondary_missing_helpers == []
    hints = _build_repair_hints(
        err,
        "",
        error_code="computed_observable_unsafe",
        layer="symbols",
        scope_metadata=scope,
        symbol_table=symbols,
        validation_evidence=evidence,
    )
    assert "LEGAL-EFFECT COMPUTED HELPER" not in hints
    assert "computed_observable_unsafe_for_legal_effect" not in hints


def test_computed_observable_legal_effect_repair_card():
    card = format_repair_card("computed_observable_unsafe_for_legal_effect")
    assert "legal effect" in card.lower()
    assert "helper" in card.lower()
    assert "observable" in card.lower()


def test_computed_helper_supplement_preserves_legal_effect():
    supplement = build_legal_effect_computed_helper_supplement(
        error_message=_COMPUTED_ERR,
        symbol_table=_SYMBOLS,
        computed_predicate="exceeds_employee_threshold",
        computed_kind_hint="threshold",
    )
    assert "legal effect" in supplement.lower()
    assert "legal_consequences_apply" in supplement
    assert "Do not" in supplement
    assert "Delete the legal-effect" in supplement
