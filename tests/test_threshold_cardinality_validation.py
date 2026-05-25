"""Threshold-cardinality validation for at-most-one criterion exceeded logic."""

from __future__ import annotations

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir
from pipeline.kb.json_ir_repair import JsonIRErrorKind, classify_json_ir_validation_error

LAW_AT_MOST_ONE = (
    "Article 1:24. A company is a small company if not more than one of the following criteria is exceeded: "
    "employees, turnover, or balance sheet total."
)

LAW_ANY_ONE = (
    "Article 9. A permit is granted if any of the following conditions is sufficient: "
    "condition_A, condition_B, or condition_C."
)


def _cmp(func: str, op: str, right: int | float) -> dict:
    return {
        "compare": {
            "left": {"func": func, "args": ["c"]},
            "op": op,
            "right": right,
        }
    }


def _base_ir(*, if_expr, law_text: str | None = LAW_AT_MOST_ONE) -> dict:
    return {
        "types": ["Company"],
        "predicates": [
            {
                "name": "favorable_status",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
                "description": "Favorable legal classification",
            },
            {
                "name": "condition_A",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
            },
            {
                "name": "condition_B",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
            },
            {
                "name": "condition_C",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
            },
        ],
        "functions": [
            {"name": "metric_A", "args": ["Company"], "returns": "Int", "kind": "observable"},
            {"name": "metric_B", "args": ["Company"], "returns": "Int", "kind": "observable"},
            {"name": "metric_C", "args": ["Company"], "returns": "Int", "kind": "observable"},
        ],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": if_expr if isinstance(if_expr, list) else [if_expr],
                "then": [{"pred": "favorable_status", "args": ["c"]}],
                "operator": "implies",
            }
        ],
        "_law": law_text,
    }


def _validate_fixture(ir: dict) -> None:
    law = ir.pop("_law", None)
    compile_validate_json_ir(ir, law_text_for_lints=law)


def test_a_or_exceeded_favorable_fails() -> None:
    ir = _base_ir(
        if_expr={
            "or": [
                _cmp("metric_A", ">", 50),
                _cmp("metric_B", ">", 100),
                _cmp("metric_C", ">", 200),
            ]
        }
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        _validate_fixture(ir)
    msg = str(exc.value)
    assert "JSON_IR_RULE_DESIGN_ERROR" in msg
    assert "exceeded-threshold" in msg or "exceeded" in msg
    assert classify_json_ir_validation_error(msg) == JsonIRErrorKind.RULES_REPAIR_ONLY


def test_b_or_within_favorable_fails() -> None:
    ir = _base_ir(
        if_expr={
            "or": [
                _cmp("metric_A", "<=", 50),
                _cmp("metric_B", "<=", 100),
                _cmp("metric_C", "<=", 200),
            ]
        }
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        _validate_fixture(ir)
    msg = str(exc.value)
    assert "within-threshold" in msg or "within" in msg


def test_c_negated_pairwise_exceeded_passes() -> None:
    ir = _base_ir(
        if_expr={
            "not": {
                "or": [
                    {
                        "and": [
                            _cmp("metric_A", ">", 50),
                            _cmp("metric_B", ">", 100),
                        ]
                    },
                    {
                        "and": [
                            _cmp("metric_A", ">", 50),
                            _cmp("metric_C", ">", 200),
                        ]
                    },
                    {
                        "and": [
                            _cmp("metric_B", ">", 100),
                            _cmp("metric_C", ">", 200),
                        ]
                    },
                ]
            }
        }
    )
    _validate_fixture(ir)


def test_d_pairwise_within_or_passes() -> None:
    ir = _base_ir(
        if_expr={
            "or": [
                {"and": [_cmp("metric_A", "<=", 50), _cmp("metric_B", "<=", 100)]},
                {"and": [_cmp("metric_A", "<=", 50), _cmp("metric_C", "<=", 200)]},
                {"and": [_cmp("metric_B", "<=", 100), _cmp("metric_C", "<=", 200)]},
            ]
        }
    )
    ir["predicates"].append(
        {
            "name": "at_least_two_exceeded",
            "args": ["Company"],
            "returns": "Bool",
            "kind": "helper",
        }
    )
    ir["rules"].extend(
        [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": "at_least_two_exceeded", "args": ["c"]}],
                "then": [{"pred": "at_least_two_exceeded", "args": ["c"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": "at_least_two_exceeded", "args": ["c"]}],
                "then": [{"pred": "favorable_status", "args": ["c"], "negated": True}],
                "operator": "implies",
            },
        ]
    )
    _validate_fixture(ir)


def test_e_any_one_sufficient_or_passes() -> None:
    ir = _base_ir(
        law_text=LAW_ANY_ONE,
        if_expr={
            "or": [
                {"pred": "condition_A", "args": ["c"]},
                {"pred": "condition_B", "args": ["c"]},
                {"pred": "condition_C", "args": ["c"]},
            ]
        },
    )
    _validate_fixture(ir)


def test_smoke_run_009_style_rule_blocked() -> None:
    """OR exceeded => is_small_company pattern from smoke_iteration2."""
    ir = {
        "types": ["Company"],
        "predicates": [
            {
                "name": "is_small_company",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
            },
        ],
        "functions": [
            {"name": "average_number_of_employees", "args": ["Company"], "returns": "Int", "kind": "observable"},
            {"name": "net_revenue_excl_vat", "args": ["Company"], "returns": "Int", "kind": "observable"},
            {"name": "balance_sheet_total", "args": ["Company"], "returns": "Int", "kind": "observable"},
        ],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [
                    {
                        "or": [
                            _cmp("average_number_of_employees", ">", 50),
                            _cmp("net_revenue_excl_vat", ">", 11250000),
                            _cmp("balance_sheet_total", ">", 6000000),
                        ]
                    }
                ],
                "then": [{"pred": "is_small_company", "args": ["c"]}],
                "operator": "implies",
            }
        ],
        "_law": LAW_AT_MOST_ONE,
    }
    with pytest.raises(JSONIRCompilationError):
        _validate_fixture(ir)


def test_smoke_run_117_style_rule_blocked() -> None:
    """OR within-threshold => is_micro_company pattern from smoke_iteration2."""
    ir = {
        "types": ["Company"],
        "predicates": [
            {"name": "is_micro_company", "args": ["Company"], "returns": "Bool", "kind": "derived"},
            {"name": "is_subsidiary", "args": ["Company"], "returns": "Bool", "kind": "observable"},
            {"name": "is_parent_company", "args": ["Company"], "returns": "Bool", "kind": "observable"},
        ],
        "functions": [
            {"name": "annual_average_employees", "args": ["Company"], "returns": "Int", "kind": "observable"},
            {"name": "annual_net_turnover", "args": ["Company"], "returns": "Int", "kind": "observable"},
            {"name": "total_balance_sheet", "args": ["Company"], "returns": "Int", "kind": "observable"},
        ],
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [
                    {"pred": "is_subsidiary", "args": ["c"], "negated": True},
                    {"pred": "is_parent_company", "args": ["c"], "negated": True},
                    {
                        "or": [
                            _cmp("annual_average_employees", "<=", 10),
                            _cmp("annual_net_turnover", "<=", 900000),
                            _cmp("total_balance_sheet", "<=", 450000),
                        ]
                    },
                ],
                "then": [{"pred": "is_micro_company", "args": ["c"]}],
                "operator": "implies",
            }
        ],
        "_law": (
            "Article 1:25. A micro-company applies if not more than one of the following criteria is exceeded."
        ),
    }
    with pytest.raises(JSONIRCompilationError):
        _validate_fixture(ir)
