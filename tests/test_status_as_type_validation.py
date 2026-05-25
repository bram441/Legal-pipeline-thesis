"""Status-as-type / legal-classification-as-type validation (iteration 4)."""

from __future__ import annotations

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir
from pipeline.kb.json_ir_repair import JsonIRErrorKind, classify_json_ir_validation_error


def _observable(name: str, args: list[str]) -> dict:
    return {
        "name": name,
        "args": args,
        "returns": "Bool",
        "kind": "observable",
        "description": "Case input",
    }


def _derived(name: str, args: list[str], *, desc: str = "") -> dict:
    return {
        "name": name,
        "args": args,
        "returns": "Bool",
        "kind": "derived",
        "description": desc or "Legal classification",
    }


def _rule(quant_type: str, *, then_pred: str, then_var: str = "x") -> dict:
    return {
        "forall": [{"var": then_var, "type": quant_type}],
        "if": [{"pred": "case_fact", "args": [then_var]}],
        "then": [{"pred": then_pred, "args": [then_var]}],
        "operator": "implies",
    }


def _base_passing_rules(quant_type: str, derived_name: str) -> list[dict]:
    return [_rule(quant_type, then_pred=derived_name)]


def _validate(ir: dict) -> None:
    compile_validate_json_ir(ir)


def _expect_schema_symbols(ir: dict) -> None:
    with pytest.raises(JSONIRCompilationError) as exc:
        _validate(ir)
    msg = str(exc.value)
    assert "JSON_IR_SCHEMA_DESIGN_ERROR" in msg
    assert classify_json_ir_validation_error(msg) == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED


def _expect_rule_symbols(ir: dict) -> None:
    with pytest.raises(JSONIRCompilationError) as exc:
        _validate(ir)
    msg = str(exc.value)
    assert "JSON_IR_RULE_DESIGN_ERROR" in msg or "JSON_IR_SCHEMA_DESIGN_ERROR" in msg
    assert classify_json_ir_validation_error(msg) == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED


def test_a_third_country_national_status_as_type() -> None:
    """Type ThirdCountryNational + is_third_country_national(ThirdCountryNational) -> symbols repair."""
    ir = {
        "types": ["ThirdCountryNational"],
        "predicates": [
            _observable("case_fact", ["ThirdCountryNational"]),
            _derived("is_third_country_national", ["ThirdCountryNational"]),
        ],
        "functions": [],
        "rules": _base_passing_rules("ThirdCountryNational", "is_third_country_national"),
    }
    _expect_schema_symbols(ir)


def test_b_micro_company_derived_on_narrow_type() -> None:
    """Derived is_micro_company(MicroCompany, FinancialYear) with matching narrow type."""
    ir = {
        "types": ["MicroCompany", "FinancialYear"],
        "predicates": [
            _observable("case_fact", ["MicroCompany"]),
            _derived("is_micro_company", ["MicroCompany", "FinancialYear"]),
        ],
        "functions": [],
        "rules": [
            {
                "forall": [
                    {"var": "c", "type": "MicroCompany"},
                    {"var": "y", "type": "FinancialYear"},
                ],
                "if": [{"pred": "case_fact", "args": ["c"]}],
                "then": [{"pred": "is_micro_company", "args": ["c", "y"]}],
                "operator": "implies",
            }
        ],
    }
    _expect_schema_symbols(ir)


def test_c_person_broad_type_status_predicate_passes() -> None:
    """is_third_country_national(Person) over Person is acceptable."""
    ir = {
        "types": ["Person"],
        "predicates": [
            _observable("case_fact", ["Person"]),
            _derived("is_third_country_national", ["Person"]),
        ],
        "functions": [],
        "rules": _base_passing_rules("Person", "is_third_country_national"),
    }
    _validate(ir)


def test_d_company_broad_type_micro_predicate_passes() -> None:
    """is_micro_company(Company, FinancialYear) over Company is acceptable."""
    ir = {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            _observable("reports_for_year", ["Company", "FinancialYear"]),
            _derived("is_micro_company", ["Company", "FinancialYear"]),
        ],
        "functions": [],
        "rules": [
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "y", "type": "FinancialYear"},
                ],
                "if": [{"pred": "reports_for_year", "args": ["c", "y"]}],
                "then": [{"pred": "is_micro_company", "args": ["c", "y"]}],
                "operator": "implies",
            }
        ],
    }
    _validate(ir)


def test_e_observable_has_legal_personality_on_company_passes() -> None:
    """Observable has_* on broad Company type is not a status-as-type trap."""
    ir = {
        "types": ["Company"],
        "predicates": [
            _observable("has_legal_personality", ["Company"]),
            _derived("is_registered", ["Company"]),
        ],
        "functions": [],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": "has_legal_personality", "args": ["c"]}],
                "then": [{"pred": "is_registered", "args": ["c"]}],
                "operator": "implies",
            }
        ],
    }
    _validate(ir)


def test_f_status_record_binary_predicate_passes() -> None:
    """Record-like type with non-is_* binary predicate should not be over-blocked."""
    ir = {
        "types": ["StatusRecord", "Person"],
        "predicates": [
            _observable("records_status", ["StatusRecord", "Person"]),
            _derived("status_applies", ["Person"]),
        ],
        "functions": [],
        "rules": [
            {
                "forall": [
                    {"var": "r", "type": "StatusRecord"},
                    {"var": "p", "type": "Person"},
                ],
                "if": [{"pred": "records_status", "args": ["r", "p"]}],
                "then": [{"pred": "status_applies", "args": ["p"]}],
                "operator": "implies",
            }
        ],
    }
    _validate(ir)


def test_redundant_is_company_on_broad_company_type_passes() -> None:
    """is_company(Company) on broad Company is redundant but not a status-as-type trap."""
    ir = {
        "types": ["Company"],
        "predicates": [
            _observable("has_registration", ["Company"]),
            _derived("is_company", ["Company"]),
        ],
        "functions": [],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": "has_registration", "args": ["c"]}],
                "then": [{"pred": "is_company", "args": ["c"]}],
                "operator": "implies",
            }
        ],
    }
    _validate(ir)


def test_g_rule_concludes_status_on_quantified_status_type() -> None:
    """Rule derives is_eligible_applicant(x) where x is quantified as EligibleApplicant."""
    ir = {
        "types": ["Person", "EligibleApplicant"],
        "predicates": [
            _observable("case_fact", ["EligibleApplicant"]),
            _derived("is_eligible_applicant", ["Person"]),
        ],
        "functions": [],
        "rules": [_rule("EligibleApplicant", then_pred="is_eligible_applicant")],
    }
    _expect_rule_symbols(ir)
