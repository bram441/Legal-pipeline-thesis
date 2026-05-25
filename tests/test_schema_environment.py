from pipeline.kb.schema_environment import build_schema_environment


def _kb_schema():
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {
                "name": "legal_consequences_apply_from_following_financial_year",
                "kind": "derived",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "legal_output": True,
                "output_category": "legal_effect",
            },
            {
                "name": "next_financial_year",
                "kind": "observable",
                "args": ["FinancialYear", "FinancialYear"],
                "returns": "Bool",
                "directly_observable": True,
                "background": True,
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


def test_environment_contains_types_signatures_and_lists():
    env = build_schema_environment(_kb_schema())
    assert "Company" in env["types"]
    assert "FinancialYear" in env["types"]
    assert env["predicates"]["legal_consequences_apply_from_following_financial_year"]["args"] == [
        "Company",
        "FinancialYear",
    ]
    assert env["functions"]["annual_average_number_of_employees"]["returns"] == "Int"
    assert "legal_consequences_apply_from_following_financial_year" in env["legal_output_query_targets"]
    assert "next_financial_year" in env["temporal_support_symbols"]


def test_assertability_policy_respected():
    env = build_schema_environment(_kb_schema())
    assert (
        env["predicates"]["legal_consequences_apply_from_following_financial_year"][
            "assertable_in_case"
        ]
        is False
    )
    assert env["predicates"]["next_financial_year"]["assertable_in_case"] is True
    assert env["functions"]["annual_average_number_of_employees"]["assertable_in_case"] is True
