import pytest

from pipeline.kb.schema_environment import build_schema_environment
from pipeline.validation.pre_solver_validation import (
    PreSolverDomainValidationError,
    prepare_case_for_symbolic,
)


def _schema():
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {
                "name": "legal_consequences_apply_from_following_financial_year",
                "kind": "derived",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "legal_output": True,
            },
            {
                "name": "company_marker",
                "kind": "observable",
                "args": ["Company"],
                "returns": "Bool",
                "directly_observable": True,
            },
            {
                "name": "year_marker",
                "kind": "observable",
                "args": ["FinancialYear"],
                "returns": "Bool",
                "directly_observable": True,
            },
        ],
        "functions": [
            {
                "name": "annual_average_number_of_employees",
                "kind": "observable",
                "args": ["Company", "FinancialYear"],
                "returns": "Int",
                "directly_observable": True,
            }
        ],
    }


def test_entity_type_inference_from_fact_and_query_args():
    env = build_schema_environment(_schema())
    case = {"facts": ["company_marker(bv_horizon)."], "entities": {}}
    query = {
        "type": "predicate",
        "predicate": "legal_consequences_apply_from_following_financial_year",
        "args": ["bv_horizon", "financial_year_2025"],
    }
    prepared, mapping, _ = prepare_case_for_symbolic(case, query, env)
    assert mapping["entities"]["bv_horizon"]["resolved_type"] == "Company"
    assert mapping["entities"]["financial_year_2025"]["resolved_type"] == "FinancialYear"
    assert "Company" in prepared["entities"] and "bv_horizon" in prepared["entities"]["Company"]


def test_conflicting_inferred_types_fail_before_solver():
    env = build_schema_environment(_schema())
    case = {"facts": ["company_marker(shared_entity).", "year_marker(shared_entity)."], "entities": {}}
    with pytest.raises(PreSolverDomainValidationError):
        prepare_case_for_symbolic(case, None, env)


def test_unknown_declared_type_fails_presolver():
    env = build_schema_environment(_schema())
    case = {"facts": [], "entities": {"UnknownType": ["x"]}}
    with pytest.raises(PreSolverDomainValidationError):
        prepare_case_for_symbolic(case, None, env)


def test_function_signature_validation_fails_on_swapped_args():
    env = build_schema_environment(_schema())
    case = {
        "facts": ["annual_average_number_of_employees(financial_year_2025,bv_horizon)=12."],
        "entities": {"Company": ["bv_horizon"], "FinancialYear": ["financial_year_2025"]},
    }
    with pytest.raises(PreSolverDomainValidationError):
        prepare_case_for_symbolic(case, None, env)
