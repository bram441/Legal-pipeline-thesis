"""Deterministic Int/Real compare literal normalization."""

from __future__ import annotations

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir


def _ir_with_compare(right) -> dict:
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {
                "name": "is_classification",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
            }
        ],
        "functions": [
            {
                "name": "annual_net_turnover",
                "args": ["Company", "FinancialYear"],
                "returns": "Real",
                "kind": "observable",
            }
        ],
        "rules": [
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "y", "type": "FinancialYear"},
                ],
                "if": [
                    {
                        "compare": {
                            "left": {"func": "annual_net_turnover", "args": ["c", "y"]},
                            "op": "=<",
                            "right": right,
                        }
                    }
                ],
                "then": [{"pred": "is_classification", "args": ["c", "y"]}],
                "operator": "implies",
            }
        ],
    }


def test_real_function_int_literal_normalizes_to_float():
    ir = _ir_with_compare(900000)
    norm = compile_validate_json_ir(ir, law_text_for_lints="turnover 900,000")
    fo = "\n".join(norm["rules"])
    assert "900000.0" in fo or "900000.0" in fo.replace(" ", "")


def test_int_function_float_integral_normalizes_to_int():
    ir = {
        "types": ["Company"],
        "predicates": [
            {
                "name": "is_classification",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
            }
        ],
        "functions": [
            {
                "name": "employee_count",
                "args": ["Company"],
                "returns": "Int",
                "kind": "observable",
            }
        ],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [
                    {
                        "compare": {
                            "left": {"func": "employee_count", "args": ["c"]},
                            "op": "=<",
                            "right": 50.0,
                        }
                    }
                ],
                "then": [{"pred": "is_classification", "args": ["c"]}],
                "operator": "implies",
            }
        ],
    }
    norm = compile_validate_json_ir(ir, law_text_for_lints="employees 50")
    fo = "\n".join(norm["rules"])
    assert "50)" in fo or " 50 " in fo
    assert "50.0" not in fo


def test_int_function_non_integral_float_still_errors():
    ir = {
        "types": ["Company"],
        "predicates": [
            {
                "name": "is_classification",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
            }
        ],
        "functions": [
            {
                "name": "employee_count",
                "args": ["Company"],
                "returns": "Int",
                "kind": "observable",
            }
        ],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [
                    {
                        "compare": {
                            "left": {"func": "employee_count", "args": ["c"]},
                            "op": "=<",
                            "right": 50.5,
                        }
                    }
                ],
                "then": [{"pred": "is_classification", "args": ["c"]}],
                "operator": "implies",
            }
        ],
    }
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir, law_text_for_lints=None)
    assert "Int" in str(exc.value) and "Real" in str(exc.value)


def test_negated_then_renders_tilde():
    ir = {
        "types": ["Company"],
        "predicates": [
            {
                "name": "case_fact",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
            },
            {
                "name": "at_least_two_exceeded",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "helper",
            },
            {
                "name": "is_classification",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
            },
        ],
        "functions": [],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": "at_least_two_exceeded", "args": ["c"]}],
                "then": [{"pred": "at_least_two_exceeded", "args": ["c"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [
                    {"pred": "case_fact", "args": ["c"]},
                    {"pred": "at_least_two_exceeded", "args": ["c"], "negated": True},
                ],
                "then": [{"pred": "is_classification", "args": ["c"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": "at_least_two_exceeded", "args": ["c"]}],
                "then": [
                    {
                        "pred": "is_classification",
                        "args": ["c"],
                        "negated": True,
                    }
                ],
                "operator": "implies",
            },
        ],
        "_law": "not more than one criterion exceeded",
    }
    law = ir.pop("_law")
    norm = compile_validate_json_ir(ir, law_text_for_lints=law)
    fo = "\n".join(norm["rules"])
    assert "~is_classification" in fo.replace(" ", "")
