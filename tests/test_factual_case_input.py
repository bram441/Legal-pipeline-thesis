"""Controlled case-given factual threshold/criterion satisfaction inputs."""

from __future__ import annotations

import pytest

from pipeline.extraction.case_fact_validation import (
    CaseFactAssertionRejected,
    case_predicate_may_be_asserted,
    case_predicate_may_be_asserted_as_factual_input,
    validate_case_facts_not_query_target,
)
from pipeline.extraction.json_ir import ExtractionIRValidationError, normalize_case_ir
from pipeline.kb.evidence_text import evidence_text_supported_in_case
from pipeline.kb.case_given_bridge import (
    augment_kb_for_case_given,
    build_case_given_inputs_from_assertions,
    inject_case_given_bridges_into_fo,
)
from pipeline.kb.factual_case_input import is_factual_case_input_candidate
from pipeline.kb.schema_environment import build_schema_environment


def _schema_with_helpers(*, include_consecutive: bool = False):
    preds = [
        {
            "name": "exceeds_employee_threshold",
            "kind": "helper",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "description": "Company exceeds the employee threshold for the financial year.",
        },
        {
            "name": "exceeds_more_than_one_criterion",
            "kind": "helper",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "description": "Company exceeds more than one criterion threshold.",
        },
        {
            "name": "legal_consequences_apply_from_following_financial_year",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "legal_output": True,
            "output_category": "legal_effect",
            "description": "Legal consequences apply from the following financial year.",
        },
        {
            "name": "aux_condition",
            "kind": "helper",
            "args": ["Company"],
            "returns": "Bool",
            "description": "Generic auxiliary condition.",
        },
        {
            "name": "filed_annual_accounts",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
        },
    ]
    if include_consecutive:
        preds.append(
            {
                "name": "exceeded_more_than_one_criterion_two_consecutive_years",
                "kind": "helper",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "description": "More than one criterion exceeded for two consecutive years.",
            }
        )
    rules = [
        {
            "if": [{"pred": "exceeds_employee_threshold", "args": ["c", "fy"]}],
            "then": [{"pred": "exceeds_more_than_one_criterion", "args": ["c", "fy"]}],
        },
        {
            "if": [{"pred": "exceeds_more_than_one_criterion", "args": ["c", "fy"]}],
            "then": [
                {
                    "pred": "legal_consequences_apply_from_following_financial_year",
                    "args": ["c", "fy"],
                }
            ],
        },
    ]
    if include_consecutive:
        rules.append(
            {
                "if": [
                    {
                        "pred": "exceeded_more_than_one_criterion_two_consecutive_years",
                        "args": ["c", "fy"],
                    }
                ],
                "then": [
                    {
                        "pred": "legal_consequences_apply_from_following_financial_year",
                        "args": ["c", "fy"],
                    }
                ],
            }
        )
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": preds,
        "functions": [
            {
                "name": "annual_average_number_of_employees",
                "kind": "observable",
                "args": ["Company", "FinancialYear"],
                "returns": "Int",
            }
        ],
        "rules": rules,
    }


def test_numeric_values_are_not_invented():
    case_text = "The company exceeded the employee threshold during the financial year."
    with pytest.raises(ExtractionIRValidationError, match="cannot invent numeric"):
        normalize_case_ir(
            {
                "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
                "assertions": [],
                "value_assertions": [
                    {
                        "symbol": "annual_average_number_of_employees",
                        "args": ["acme", "fy2025"],
                        "value": 51,
                    }
                ],
            },
            _schema_with_helpers(),
            case_text=case_text,
        )


def test_legal_output_still_rejected():
    with pytest.raises(CaseFactAssertionRejected, match="legal-output|query predicate"):
        normalize_case_ir(
            {
                "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
                "assertions": [
                    {
                        "symbol": "legal_consequences_apply_from_following_financial_year",
                        "args": ["acme", "fy2025"],
                    }
                ],
            },
            _schema_with_helpers(),
            case_text="Legal consequences apply from the following financial year for acme.",
        )


def test_query_predicate_rejected_as_case_fact():
    schema = _schema_with_helpers()
    sig = next(p for p in schema["predicates"] if p["name"] == "legal_consequences_apply_from_following_financial_year")
    allowed, code = case_predicate_may_be_asserted(
        sig,
        query_predicate="legal_consequences_apply_from_following_financial_year",
    )
    assert allowed is False
    assert code == "query_predicate"

    case = {
        "facts": ["legal_consequences_apply_from_following_financial_year(acme,fy2025)."],
        "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
    }
    query = {
        "type": "predicate",
        "predicate": "legal_consequences_apply_from_following_financial_year",
        "mode": "boolean",
        "args": ["acme", "fy2025"],
    }
    with pytest.raises(CaseFactAssertionRejected, match="query predicate"):
        validate_case_facts_not_query_target(case, query, schema)


def test_explicit_threshold_satisfaction_allowed_with_evidence():
    schema = _schema_with_helpers()
    case_text = (
        "During FY2025, Acme Corp explicitly exceeded the employee threshold "
        "for the financial year."
    )
    case = normalize_case_ir(
        {
            "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
            "assertions": [
                {
                    "symbol": "exceeds_employee_threshold",
                    "args": ["acme", "fy2025"],
                    "negated": False,
                    "evidence_text": "Acme Corp explicitly exceeded the employee threshold",
                }
            ],
        },
        schema,
        case_text=case_text,
    )
    assert "case_given_exceeds_employee_threshold(acme,fy2025)." in case["facts"]
    assert case["case_given_factual_inputs"]
    assert case["case_given_factual_inputs"][0]["evidence_text"]


def test_explicit_composite_factual_condition_allowed():
    schema = _schema_with_helpers(include_consecutive=True)
    case_text = (
        "For Acme, more than one criterion was exceeded for two consecutive financial years."
    )
    case = normalize_case_ir(
        {
            "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
            "assertions": [
                {
                    "symbol": "exceeded_more_than_one_criterion_two_consecutive_years",
                    "args": ["acme", "fy2025"],
                    "negated": False,
                    "evidence_text": case_text,
                }
            ],
        },
        schema,
        case_text=case_text,
    )
    assert any("case_given_exceeded_more_than_one_criterion_two_consecutive_years" in f for f in case["facts"])
    assert case["case_given_factual_inputs"][0]["assertion_kind"] == "factual_threshold_satisfaction"


def test_unsupported_helper_still_rejected():
    with pytest.raises(CaseFactAssertionRejected, match="not a controlled factual"):
        normalize_case_ir(
            {
                "entities": {"Company": ["acme"]},
                "assertions": [{"symbol": "aux_condition", "args": ["acme"], "negated": False}],
            },
            _schema_with_helpers(),
            case_text="Some auxiliary condition holds for acme.",
        )


def test_case_given_bridge_predicates_and_fo_injection():
    schema = _schema_with_helpers()
    bridges = build_case_given_inputs_from_assertions(
        [
            {
                "target_predicate": "exceeds_more_than_one_criterion",
                "input_predicate": "case_given_exceeds_more_than_one_criterion",
                "args": ["acme", "fy2025"],
                "evidence_text": "more than one criterion exceeded",
            }
        ],
        schema,
    )
    assert bridges[0]["args_types"] == ["Company", "FinancialYear"]
    fo = (
        "vocabulary V {\n"
        "  type Company\n"
        "  type FinancialYear\n"
        "  exceeds_more_than_one_criterion: Company * FinancialYear -> Bool\n"
        "}\n"
        "theory T:V {\n"
        "  ! c in Company, fy in FinancialYear: true.\n"
        "}\n"
    )
    out = inject_case_given_bridges_into_fo(fo, bridges)
    assert "case_given_exceeds_more_than_one_criterion: Company * FinancialYear -> Bool" in out
    assert "case_given_exceeds_more_than_one_criterion(c, fy)) => (exceeds_more_than_one_criterion(c, fy))" in out


def test_schema_environment_lists_factual_case_inputs():
    schema = _schema_with_helpers()
    env = build_schema_environment(schema)
    assert "exceeds_more_than_one_criterion" in env["factual_case_input_predicates"]
    assert env["predicates"]["exceeds_more_than_one_criterion"]["factual_case_input"] is True
    assert (
        env["predicates"]["exceeds_more_than_one_criterion"]["case_given_input_predicate"]
        == "case_given_exceeds_more_than_one_criterion"
    )
    assert "aux_condition" not in env["factual_case_input_predicates"]


def test_is_factual_case_input_requires_rule_antecedent():
    schema = _schema_with_helpers()
    orphan = {
        "name": "exceeds_turnover_threshold",
        "kind": "helper",
        "args": ["Company", "FinancialYear"],
        "returns": "Bool",
        "description": "Company exceeds turnover threshold.",
    }
    assert is_factual_case_input_candidate(orphan, schema) is False
    assert is_factual_case_input_candidate(
        next(p for p in schema["predicates"] if p["name"] == "exceeds_employee_threshold"),
        schema,
    )
    assert is_factual_case_input_candidate(
        next(p for p in schema["predicates"] if p["name"] == "exceeds_more_than_one_criterion"),
        schema,
    )


def test_augment_kb_for_case_given_extends_schema():
    schema = _schema_with_helpers()
    case = {
        "case_given_factual_inputs": [
            {
                "target_predicate": "exceeds_more_than_one_criterion",
                "input_predicate": "case_given_exceeds_more_than_one_criterion",
                "args": ["acme", "fy2025"],
            }
        ]
    }
    fo = (
        "vocabulary V {\n"
        "  type Company\n"
        "  type FinancialYear\n"
        "  exceeds_more_than_one_criterion: Company * FinancialYear -> Bool\n"
        "}\n"
        "theory T:V {\n"
        "}\n"
    )
    new_fo, new_schema = augment_kb_for_case_given(fo, schema, case)
    names = {p["name"] for p in new_schema["predicates"]}
    assert "case_given_exceeds_more_than_one_criterion" in names
    assert "case_given_exceeds_more_than_one_criterion" in new_fo
    assert new_schema.get("case_given_bridge_rules")


def test_invented_evidence_text_rejected():
    schema = _schema_with_helpers()
    sig = next(p for p in schema["predicates"] if p["name"] == "exceeds_employee_threshold")
    allowed, code, _ = case_predicate_may_be_asserted_as_factual_input(
        sig,
        case_text="Acme exceeded the employee threshold during the financial year.",
        evidence_text="This phrase does not appear anywhere in the case.",
        kb_schema=schema,
    )
    assert allowed is False
    assert code == "unsupported_by_case_text"
    with pytest.raises(CaseFactAssertionRejected, match="does not explicitly support"):
        normalize_case_ir(
            {
                "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
                "assertions": [
                    {
                        "symbol": "exceeds_employee_threshold",
                        "args": ["acme", "fy2025"],
                        "evidence_text": "This phrase does not appear anywhere in the case.",
                    }
                ],
            },
            schema,
            case_text="Acme exceeded the employee threshold during the financial year.",
        )


def test_evidence_text_normalization_accepts_punctuation_and_whitespace():
    case_text = "During FY2025, Acme Corp exceeded the employee threshold."
    evidence = "Acme Corp  exceeded the employee-threshold"
    assert evidence_text_supported_in_case(case_text, evidence) is True


def test_valid_evidence_substring_passes():
    schema = _schema_with_helpers()
    case_text = "During FY2025, Acme explicitly exceeded the employee threshold."
    case = normalize_case_ir(
        {
            "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
            "assertions": [
                {
                    "symbol": "exceeds_employee_threshold",
                    "args": ["acme", "fy2025"],
                    "evidence_text": "explicitly exceeded the employee threshold",
                }
            ],
        },
        schema,
        case_text=case_text,
    )
    assert case["case_given_factual_inputs"]


def test_no_evidence_text_falls_back_to_conservative_lexical_support():
    schema = _schema_with_helpers(include_consecutive=True)
    case_text = (
        "For Acme, more than one criterion was exceeded for two consecutive financial years."
    )
    case = normalize_case_ir(
        {
            "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
            "assertions": [
                {
                    "symbol": "exceeded_more_than_one_criterion_two_consecutive_years",
                    "args": ["acme", "fy2025"],
                    "negated": False,
                }
            ],
        },
        schema,
        case_text=case_text,
    )
    assert any("case_given_exceeded_more_than_one_criterion_two_consecutive_years" in f for f in case["facts"])
