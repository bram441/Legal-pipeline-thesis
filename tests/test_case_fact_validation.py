"""Case extraction must assert observable base facts, not helpers/legal outputs."""

from __future__ import annotations

import pytest

from pipeline.extraction.case_fact_validation import (
    CaseFactAssertionRejected,
    build_case_fact_rejection_repair_hint,
    case_predicate_may_be_asserted,
)
from pipeline.extraction.extractor import _schema_feedback_message
from pipeline.extraction.json_ir import normalize_case_ir


_KB_SCHEMA = {
    "types": ["Company", "FinancialYear", "Criterion"],
    "predicates": [
        {
            "name": "filed_annual_accounts",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "description": "Company filed annual accounts for the financial year.",
        },
        {
            "name": "staff_size_reported",
            "kind": "observable",
            "args": ["Company", "FinancialYear", "Criterion"],
            "returns": "Bool",
            "description": "Company reported staff size for a listed dimension.",
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
            "name": "is_small_company",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "output_category": "classification",
            "description": "Company qualifies as small.",
        },
        {
            "name": "next_financial_year",
            "kind": "observable",
            "args": ["FinancialYear", "FinancialYear"],
            "returns": "Bool",
            "directly_observable": True,
            "background": True,
            "description": "The second financial year immediately follows the first.",
        },
    ],
    "functions": [
        {
            "name": "annual_net_turnover",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Int",
            "description": "Annual net turnover in euros.",
        },
        {
            "name": "criterion_count",
            "kind": "helper",
            "args": ["Company", "FinancialYear"],
            "returns": "Int",
            "description": "Derived count of criteria exceeded.",
        },
    ],
}


def test_rejects_helper_composite_predicate_as_case_fact():
    with pytest.raises(CaseFactAssertionRejected, match="helper/composite/derived|not a controlled factual"):
        normalize_case_ir(
            {
                "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
                "assertions": [
                    {"symbol": "exceeds_more_than_one_criterion", "args": ["acme", "fy2025"]},
                ],
            },
            _KB_SCHEMA,
        )


def test_repair_hint_directs_to_observable_base_facts():
    hint = build_case_fact_rejection_repair_hint(
        "exceeds_more_than_one_criterion",
        _KB_SCHEMA,
        rejection_code="derived_or_helper",
    )
    assert "decompose into observables" in hint.lower()
    assert "Suggested observable replacements" in hint
    assert "staff_size_reported" in hint
    assert "annual_net_turnover" in hint
    assert "fabricate" in hint.lower() or "omit" in hint.lower()


def test_schema_feedback_includes_case_fact_remediation():
    err = CaseFactAssertionRejected(
        "Case extraction cannot assert helper/composite/derived predicate "
        "exceeds_more_than_one_criterion. Use observable base facts only.",
        pred="exceeds_more_than_one_criterion",
        rejection_code="derived_or_helper",
    )
    msg = _schema_feedback_message(err, {}, _KB_SCHEMA)
    assert "REMEDIATION (case facts" in msg
    assert "staff_size_reported" in msg


def test_composite_case_statement_via_atomic_observables():
    case = normalize_case_ir(
        {
            "entities": {
                "Company": ["acme"],
                "FinancialYear": ["fy2025"],
                "Criterion": ["turnover", "balance_sheet"],
            },
            "assertions": [
                {"symbol": "staff_size_reported", "args": ["acme", "fy2025", "turnover"]},
                {"symbol": "staff_size_reported", "args": ["acme", "fy2025", "balance_sheet"]},
                {"symbol": "filed_annual_accounts", "args": ["acme", "fy2025"]},
            ],
            "value_assertions": [
                {"symbol": "annual_net_turnover", "args": ["acme", "fy2025"], "value": 9000000},
            ],
        },
        _KB_SCHEMA,
    )
    assert "staff_size_reported(acme,fy2025,turnover)." in case["facts"]
    assert "staff_size_reported(acme,fy2025,balance_sheet)." in case["facts"]
    assert "filed_annual_accounts(acme,fy2025)." in case["facts"]
    assert "annual_net_turnover(acme,fy2025) = 9000000." in case["facts"]
    assert not any("exceeds_more_than_one_criterion" in f for f in case["facts"])


def test_rejects_legal_output_predicate_as_case_fact():
    with pytest.raises(CaseFactAssertionRejected, match="legal-output"):
        normalize_case_ir(
            {
                "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
                "assertions": [
                    {
                        "symbol": "legal_consequences_apply_from_following_financial_year",
                        "args": ["acme", "fy2025"],
                    },
                ],
            },
            _KB_SCHEMA,
        )


def test_rejects_classification_output_as_case_fact():
    with pytest.raises(CaseFactAssertionRejected, match="classification"):
        normalize_case_ir(
            {
                "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
                "assertions": [{"symbol": "is_small_company", "args": ["acme", "fy2025"]}],
            },
            _KB_SCHEMA,
        )


def test_background_temporal_may_be_asserted_when_marked():
    case = normalize_case_ir(
        {
            "entities": {"FinancialYear": ["fy2025", "fy2026"]},
            "assertions": [
                {"symbol": "next_financial_year", "args": ["fy2025", "fy2026"]},
            ],
        },
        _KB_SCHEMA,
    )
    assert "next_financial_year(fy2025,fy2026)." in case["facts"]


def test_background_temporal_rejected_without_exemption_flags():
    schema = {
        "predicates": [
            {
                "name": "next_period",
                "kind": "observable",
                "args": ["FinancialYear", "FinancialYear"],
                "returns": "Bool",
                "description": "The next consecutive financial year follows the previous one.",
            }
        ],
        "functions": [],
    }
    allowed, code = case_predicate_may_be_asserted(schema["predicates"][0])
    assert allowed is False
    assert code == "computed_composite"

    with pytest.raises(CaseFactAssertionRejected, match="computed/composite"):
        normalize_case_ir(
            {
                "entities": {"FinancialYear": ["fy2025", "fy2026"]},
                "assertions": [{"symbol": "next_period", "args": ["fy2025", "fy2026"]}],
            },
            schema,
        )


def test_observable_with_legal_output_false_still_allowed():
    schema = {
        "predicates": [
            {
                "name": "has_legal_personality",
                "kind": "observable",
                "args": ["Company"],
                "returns": "Bool",
                "legal_output": False,
                "output_category": "classification",
                "description": "Company has legal personality.",
            }
        ],
        "functions": [],
    }
    case = normalize_case_ir(
        {
            "entities": {"Company": ["sigma"]},
            "assertions": [{"symbol": "has_legal_personality", "args": ["sigma"]}],
        },
        schema,
    )
    assert case["facts"] == ["has_legal_personality(sigma)."]


def test_normal_observable_case_fact_still_allowed():
    case = normalize_case_ir(
        {
            "entities": {
                "Company": ["acme"],
                "FinancialYear": ["fy2025"],
                "Criterion": ["turnover"],
            },
            "assertions": [
                {"symbol": "staff_size_reported", "args": ["acme", "fy2025", "turnover"]},
            ],
        },
        _KB_SCHEMA,
    )
    assert case["facts"] == ["staff_size_reported(acme,fy2025,turnover)."]
