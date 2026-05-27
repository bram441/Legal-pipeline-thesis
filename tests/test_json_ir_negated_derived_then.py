"""Negated derived conclusions in rule THEN must render as explicit negation."""

from __future__ import annotations

from pipeline.kb.json_ir import compile_validate_json_ir


def test_negated_derived_classification_in_then_renders_not_predicate() -> None:
    ir = {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {
                "name": "exceeds_limit",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "helper",
            },
            {
                "name": "is_micro_company",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
                "legal_output": True,
                "output_category": "classification",
            },
        ],
        "functions": [],
        "rules": [
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [{"pred": "exceeds_limit", "args": ["c", "fy"]}],
                "then": [
                    {
                        "pred": "is_micro_company",
                        "args": ["c", "fy"],
                        "negated": True,
                    }
                ],
                "operator": "implies",
            },
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [
                    {
                        "compare": {
                            "left": {"func": "annual_average_employees", "args": ["c", "fy"]},
                            "op": ">",
                            "right": 10,
                        }
                    }
                ],
                "then": [{"pred": "exceeds_limit", "args": ["c", "fy"]}],
                "operator": "implies",
            },
        ],
    }
    ir["functions"] = [
        {
            "name": "annual_average_employees",
            "args": ["Company", "FinancialYear"],
            "returns": "Int",
            "kind": "observable",
        }
    ]
    norm = compile_validate_json_ir(ir, law_text_for_lints="micro company threshold")
    fo = "\n".join(norm.get("rules") or [])
    compact = fo.replace(" ", "")
    assert "~is_micro_company" in compact
    assert "is_micro_company=false" not in compact.lower()
    assert "=>" in fo
