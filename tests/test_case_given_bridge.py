"""case_given bridge FO injection and structure safety."""

from __future__ import annotations

import pytest

from pipeline.extraction.json_ir import normalize_case_ir
from pipeline.kb.case_given_bridge import (
    CaseGivenBridgeArityError,
    _bridge_rule_line,
    build_case_given_inputs_from_assertions,
    extend_kb_schema_with_case_given,
    inject_case_given_bridges_into_fo,
    structure_asserts_only_case_given,
)


def _fo_base():
    return (
        "vocabulary V {\n"
        "  type Company\n"
        "  type FinancialYear\n"
        "  type Person\n"
        "  type Document\n"
        "  type Location\n"
        "  type Event\n"
        "  type Money\n"
        "  type Date\n"
        "  target_pred: Company * FinancialYear * Person -> Bool\n"
        "}\n"
        "theory T:V {\n"
        "}\n"
    )


def test_bridge_predicate_declared_in_vocabulary():
    bridges = [
        {
            "input_predicate": "case_given_target_pred",
            "target_predicate": "target_pred",
            "args_types": ["Company", "FinancialYear"],
        }
    ]
    out = inject_case_given_bridges_into_fo(_fo_base(), bridges)
    assert "case_given_target_pred: Company * FinancialYear -> Bool" in out


def test_bridge_rule_inserted_into_theory():
    bridges = [
        {
            "input_predicate": "case_given_target_pred",
            "target_predicate": "target_pred",
            "args_types": ["Company", "FinancialYear"],
        }
    ]
    out = inject_case_given_bridges_into_fo(_fo_base(), bridges)
    assert "case_given_target_pred(c, fy)) => (target_pred(c, fy))" in out


def test_bridge_rule_uses_exact_argument_types_for_arities_1_2_3():
    fo = _fo_base()
    for arity, types in enumerate(
        [["Company"], ["Company", "FinancialYear"], ["Company", "FinancialYear", "Person"]],
        start=1,
    ):
        inp = f"case_given_p{arity}"
        tgt = f"p{arity}"
        line = _bridge_rule_line(inp, tgt, types)
        for typ in types:
            assert f"in {typ}" in line
        assert f"{inp}(" in line and f"{tgt}(" in line
        bridges = [{"input_predicate": inp, "target_predicate": tgt, "args_types": types}]
        fo = inject_case_given_bridges_into_fo(fo, bridges)


def test_structure_asserts_only_case_given_not_target():
    bridges = [
        {
            "input_predicate": "case_given_exceeds_more_than_one_criterion",
            "target_predicate": "exceeds_more_than_one_criterion",
            "args_types": ["Company", "FinancialYear"],
        }
    ]
    ok, violations = structure_asserts_only_case_given(
        [
            "case_given_exceeds_more_than_one_criterion(acme,fy2025).",
            "next_financial_year(fy2024,fy2025).",
        ],
        bridges,
    )
    assert ok is True
    assert violations == []

    ok2, violations2 = structure_asserts_only_case_given(
        ["exceeds_more_than_one_criterion(acme,fy2025)."],
        bridges,
    )
    assert ok2 is False
    assert violations2


def test_normalize_case_ir_structure_uses_case_given_only():
    schema = {
        "types": ["Company", "FinancialYear"],
        "predicates": [
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
        ],
        "functions": [],
        "rules": [
            {
                "if": [{"pred": "exceeds_employee_threshold", "args": ["c", "fy"]}],
                "then": [{"pred": "exceeds_more_than_one_criterion", "args": ["c", "fy"]}],
            }
        ],
    }
    case_text = "During FY2025, Acme explicitly exceeded the employee threshold for the financial year."
    case = normalize_case_ir(
        {
            "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
            "assertions": [
                {
                    "symbol": "exceeds_employee_threshold",
                    "args": ["acme", "fy2025"],
                    "evidence_text": "Acme explicitly exceeded the employee threshold",
                }
            ],
        },
        schema,
        case_text=case_text,
    )
    assert any("case_given_exceeds_employee_threshold" in f for f in case["facts"])
    assert not any(f.startswith("exceeds_employee_threshold(") for f in case["facts"])


def test_bridge_arity_above_limit_raises_structured_error():
    types = [f"T{i}" for i in range(9)]
    with pytest.raises(CaseGivenBridgeArityError, match="maximum supported arity"):
        _bridge_rule_line("case_given_big", "big", types)


def test_duplicate_case_given_bridges_are_deduplicated_by_signature():
    base = _fo_base()
    bridges = [
        {
            "input_predicate": "case_given_more_than_one_criterion_exceeded",
            "target_predicate": "more_than_one_criterion_exceeded",
            "args_types": ["Company", "FinancialYear"],
        },
        {
            "input_predicate": "case_given_more_than_one_criterion_exceeded",
            "target_predicate": "more_than_one_criterion_exceeded",
            "args_types": ["Company", "FinancialYear"],
        },
    ]
    out = inject_case_given_bridges_into_fo(base, bridges)
    assert out.count("case_given_more_than_one_criterion_exceeded: Company * FinancialYear -> Bool") == 1
    assert out.count(
        "case_given_more_than_one_criterion_exceeded(c, fy)) => (more_than_one_criterion_exceeded(c, fy))"
    ) == 1


def test_extend_schema_deduplicates_case_given_bridge_rules_by_signature():
    schema = {
        "predicates": [
            {"name": "more_than_one_criterion_exceeded", "args": ["Company", "FinancialYear"], "returns": "Bool"}
        ]
    }
    case_given_inputs = [
        {
            "input_predicate": "case_given_more_than_one_criterion_exceeded",
            "target_predicate": "more_than_one_criterion_exceeded",
            "target_signature": {"args": ["Company", "FinancialYear"]},
        },
        {
            "input_predicate": "case_given_more_than_one_criterion_exceeded",
            "target_predicate": "more_than_one_criterion_exceeded",
            "target_signature": {"args": ["Company", "FinancialYear"]},
        },
    ]
    out = extend_kb_schema_with_case_given(schema, case_given_inputs)
    bridge_rules = out.get("case_given_bridge_rules") or []
    assert len(bridge_rules) == 1
