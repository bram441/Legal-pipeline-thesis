"""Legal-effect output predicate validation (iteration 5)."""

from __future__ import annotations

import pytest

from pipeline.extraction.json_ir import (
    ExtractionIRValidationError,
    _pick_most_specific_derived_predicate,
    _validate_query_target_for_legal_question,
)
from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir
from pipeline.kb.json_ir_repair import JsonIRErrorKind, classify_json_ir_validation_error

LAW_CONSEQUENCES_TIMING = (
    "The consequences apply from the financial year following the year in which the "
    "criteria were exceeded for the second consecutive time."
)

LAW_IMMEDIATE_ACCOUNT = "The amount must be taken into account immediately."

LAW_CLASSIFICATION_ONLY = (
    "A micro-company is a company that does not exceed more than one criterion."
)

QUESTION_CONSEQUENCES = (
    "Do the consequences according to article X apply from the financial year following 2025?"
)


def _observable(name: str, args: list[str]) -> dict:
    return {
        "name": name,
        "args": args,
        "returns": "Bool",
        "kind": "observable",
        "description": "Case input",
    }


def _derived(name: str, args: list[str], *, desc: str = "", **meta) -> dict:
    out = {
        "name": name,
        "args": args,
        "returns": "Bool",
        "kind": "derived",
        "description": desc or "Legal output",
    }
    out.update(meta)
    return out


def _helper(name: str, args: list[str]) -> dict:
    return {
        "name": name,
        "args": args,
        "returns": "Bool",
        "kind": "helper",
        "description": "Threshold check",
    }


def _rule_company_year(*, then_pred: str, if_pred: str = "reports_for_year") -> dict:
    return {
        "forall": [
            {"var": "c", "type": "Company"},
            {"var": "y", "type": "FinancialYear"},
        ],
        "if": [{"pred": if_pred, "args": ["c", "y"]}],
        "then": [{"pred": then_pred, "args": ["c", "y"]}],
        "operator": "implies",
    }


def _validate(ir: dict, *, law: str | None = None) -> None:
    law_text = ir.pop("_law", law)
    compile_validate_json_ir(ir, law_text_for_lints=law_text)


def _expect_symbols_repair(ir: dict) -> None:
    with pytest.raises(JSONIRCompilationError) as exc:
        _validate(ir)
    msg = str(exc.value)
    assert "JSON_IR_SCHEMA_DESIGN_ERROR" in msg
    assert "legal-output" in msg.lower() or "legal-effect" in msg.lower()
    assert classify_json_ir_validation_error(msg) == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED


def test_a_missing_legal_effect_on_consequences_law() -> None:
    ir = {
        "_law": LAW_CONSEQUENCES_TIMING,
        "types": ["Company", "FinancialYear"],
        "predicates": [
            _observable("reports_for_year", ["Company", "FinancialYear"]),
            _derived("is_small_company", ["Company", "FinancialYear"], desc="Small company classification"),
            _derived("is_micro_company", ["Company", "FinancialYear"], desc="Micro company classification"),
        ],
        "functions": [],
        "rules": [
            _rule_company_year(then_pred="is_small_company"),
            _rule_company_year(then_pred="is_micro_company"),
        ],
    }
    _expect_symbols_repair(ir)


def test_b_legal_effect_predicate_with_rule_passes() -> None:
    ir = {
        "_law": LAW_CONSEQUENCES_TIMING,
        "types": ["Company", "FinancialYear"],
        "predicates": [
            _observable("reports_for_year", ["Company", "FinancialYear"]),
            _derived(
                "consequences_apply_from_following_financial_year",
                ["Company", "FinancialYear"],
                desc="Legal consequences apply from the following financial year",
                legal_output=True,
                output_category="legal_effect",
            ),
            _derived("is_small_company", ["Company", "FinancialYear"], output_category="classification"),
        ],
        "functions": [],
        "rules": [
            _rule_company_year(then_pred="consequences_apply_from_following_financial_year"),
            _rule_company_year(then_pred="is_small_company"),
        ],
    }
    _validate(ir)


def test_c_immediate_account_law_missing_effect_predicate() -> None:
    ir = {
        "_law": LAW_IMMEDIATE_ACCOUNT,
        "types": ["Amount"],
        "predicates": [
            _observable("amount_reported", ["Amount"]),
            _helper("amount_exceeds_threshold", ["Amount"]),
            _derived("threshold_met", ["Amount"], desc="Threshold condition met"),
        ],
        "functions": [],
        "rules": [
            {
                "forall": [{"var": "a", "type": "Amount"}],
                "if": [{"pred": "amount_reported", "args": ["a"]}],
                "then": [{"pred": "threshold_met", "args": ["a"]}],
                "operator": "implies",
            }
        ],
    }
    _expect_symbols_repair(ir)


def test_d_classification_only_law_passes() -> None:
    ir = {
        "_law": LAW_CLASSIFICATION_ONLY,
        "types": ["Company", "FinancialYear"],
        "predicates": [
            _observable("reports_for_year", ["Company", "FinancialYear"]),
            _derived("is_micro_company", ["Company", "FinancialYear"], desc="Micro-company classification"),
        ],
        "functions": [],
        "rules": [_rule_company_year(then_pred="is_micro_company")],
    }
    _validate(ir)


def test_e_query_prefers_legal_effect_predicate() -> None:
    kb = {
        "predicates": [
            _derived("is_micro_company", ["Company", "FinancialYear"], output_category="classification"),
            _derived(
                "consequences_apply_from_following_financial_year",
                ["Company", "FinancialYear"],
                desc="Consequences apply from the following financial year",
                legal_output=True,
            ),
        ]
    }
    picked = _pick_most_specific_derived_predicate(QUESTION_CONSEQUENCES, kb, "is_micro_company")
    assert picked == "consequences_apply_from_following_financial_year"


def test_f_query_rejects_classification_when_effect_question() -> None:
    kb = {
        "predicates": [
            _derived("is_micro_company", ["Company", "FinancialYear"], desc="Micro company status"),
            _derived("is_small_company", ["Company", "FinancialYear"], desc="Small company status"),
        ]
    }
    with pytest.raises(ExtractionIRValidationError) as exc:
        _validate_query_target_for_legal_question("is_micro_company", QUESTION_CONSEQUENCES, kb)
    assert "classification" in str(exc.value).lower() or "legal-output" in str(exc.value).lower()


def test_run_006_style_dutch_question_detected() -> None:
    from pipeline.kb.legal_effect import question_has_legal_effect_language

    q = (
        "Gaan de gevolgen volgens artikel 1:24, paragraaf 2 in vanaf het boekjaar "
        "dat volgt op boekjaar 2025?"
    )
    assert question_has_legal_effect_language(q)


def test_metadata_legal_output_marks_effect_predicate() -> None:
    from pipeline.kb.legal_effect import predicate_represents_legal_effect_output

    assert predicate_represents_legal_effect_output(
        "is_micro_company",
        kind="derived",
        legal_output=False,
        output_category="classification",
    ) is False
    assert predicate_represents_legal_effect_output(
        "consequences_apply_from_period",
        kind="derived",
        legal_output=True,
    ) is True
