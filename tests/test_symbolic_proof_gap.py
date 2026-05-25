"""Tests for symbolic proof-gap diagnostics."""

from pipeline.diagnostics.symbolic_proof_gap import build_symbolic_proof_gap_report


def _kb_schema():
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {
                "name": "next_financial_year",
                "kind": "observable",
                "args": ["FinancialYear", "FinancialYear"],
                "returns": "Bool",
                "directly_observable": True,
            },
            {
                "name": "exceeded_more_than_one_criterion_two_consecutive_years",
                "kind": "helper",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
            },
            {
                "name": "consequences_apply_from_financial_year",
                "kind": "derived",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
            },
            {
                "name": "exceeds_more_than_one_criterion",
                "kind": "helper",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
            },
        ],
        "functions": [
            {
                "name": "annual_average_number_of_employees",
                "kind": "observable",
                "args": ["Company", "FinancialYear"],
                "returns": "Int",
            }
        ],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}, {"var": "fy1", "type": "FinancialYear"}, {"var": "fy2", "type": "FinancialYear"}],
                "if": [
                    {
                        "and": [
                            {"pred": "exceeds_more_than_one_criterion", "args": ["c", "fy1"], "negated": False},
                            {"pred": "exceeds_more_than_one_criterion", "args": ["c", "fy2"], "negated": False},
                            {"pred": "next_financial_year", "args": ["fy1", "fy2"], "negated": False},
                        ]
                    }
                ],
                "then": [
                    {
                        "pred": "exceeded_more_than_one_criterion_two_consecutive_years",
                        "args": ["c", "fy2"],
                        "negated": False,
                    }
                ],
            },
            {
                "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
                "if": [
                    {
                        "pred": "exceeded_more_than_one_criterion_two_consecutive_years",
                        "args": ["c", "fy"],
                        "negated": False,
                    }
                ],
                "then": [
                    {"pred": "consequences_apply_from_financial_year", "args": ["c", "fy"], "negated": False}
                ],
            },
        ],
    }


def test_proof_gap_flags_missing_numeric_and_query_temporal_issue():
    case = {
        "facts": ["next_financial_year(fy_2024,fy_2025)."],
        "entities": {"Company": ["acme"], "FinancialYear": ["fy_2024", "fy_2025"]},
    }
    query = {
        "type": "predicate",
        "predicate": "consequences_apply_from_financial_year",
        "mode": "boolean",
        "args": ["acme", "fy_2024"],
    }
    report = build_symbolic_proof_gap_report(
        case=case,
        query=query,
        kb_schema=_kb_schema(),
        symbolic_result={"status": "ok", "label": "unknown", "certain": False},
        case_text=(
            "Acme exceeded more than one threshold during two consecutive financial years. "
            "The second year of exceeding is financial year 2025."
        ),
        user_question="Do consequences apply from the financial year following financial year 2025?",
    )
    assert report["query"]["predicate"] == "consequences_apply_from_financial_year"
    assert any(a["gap_status"] == "blocked_by_missing_numeric" for a in report["antecedents"])
    assert report["temporal_query_issues"]
    assert report["classification"]["primary"] == "extraction_gap"
    assert "query_argument_issue" in report["classification"]["secondary"]
