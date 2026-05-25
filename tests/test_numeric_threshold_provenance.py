"""Numeric threshold literal provenance (iteration: threshold integrity)."""

from __future__ import annotations

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir
from pipeline.kb.json_ir_repair import JsonIRErrorKind, classify_json_ir_validation_error
from pipeline.kb.law_numeric_literals import (
    extract_numeric_values_from_law_text,
    numeric_value_matches_law,
    parse_numeric_token,
)


def _cmp(func: str, op: str, right: int | float) -> dict:
    return {
        "compare": {
            "left": {"func": func, "args": ["c", "y"]},
            "op": op,
            "right": right,
        }
    }


def _base_ir(*, if_expr, law: str) -> dict:
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
            },
            {
                "name": "total_assets",
                "args": ["Company", "FinancialYear"],
                "returns": "Real",
                "kind": "observable",
            },
        ],
        "rules": [
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "y", "type": "FinancialYear"},
                ],
                "if": if_expr if isinstance(if_expr, list) else [if_expr],
                "then": [{"pred": "is_classification", "args": ["c", "y"]}],
                "operator": "implies",
            }
        ],
        "_law": law,
    }


LAW_MICRO = (
    "Article 1:25. Micro-companies: employees: 10; turnover: 900,000 euros; total assets: 450,000 euros."
)


def test_parse_european_and_us_number_formats():
    assert parse_numeric_token("900,000") == 900000.0
    assert parse_numeric_token("450.000") == 450000.0
    assert parse_numeric_token("11,250,000") == 11250000.0
    assert parse_numeric_token("11.250.000") == 11250000.0


def test_law_extract_and_match():
    vals = extract_numeric_values_from_law_text(LAW_MICRO)
    assert numeric_value_matches_law(900000.0, vals)
    assert numeric_value_matches_law(450000, vals)
    assert not numeric_value_matches_law(1900000, vals)


def test_rule_900000_passes():
    ir = _base_ir(if_expr=_cmp("annual_net_turnover", "=<", 900000.0), law=LAW_MICRO)
    law = ir.pop("_law")
    compile_validate_json_ir(ir, law_text_for_lints=law)


def test_rule_1900000_fails():
    ir = _base_ir(if_expr=_cmp("annual_net_turnover", ">", 1900000), law=LAW_MICRO)
    law = ir.pop("_law")
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir, law_text_for_lints=law)
    msg = str(exc.value)
    assert "does not appear in the scoped law text" in msg
    assert classify_json_ir_validation_error(msg) == JsonIRErrorKind.RULES_REPAIR_ONLY


def test_cardinality_constants_1_and_2_allowed():
    ir = _base_ir(if_expr=_cmp("annual_net_turnover", ">", 2), law="No numbers here.")
    law = ir.pop("_law")
    compile_validate_json_ir(ir, law_text_for_lints=law)
