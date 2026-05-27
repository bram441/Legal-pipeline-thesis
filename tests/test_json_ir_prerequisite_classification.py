"""Prerequisite classification closure and repair hints."""

from __future__ import annotations

import inspect

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir
from pipeline.kb.json_ir_compile_loop import _build_repair_hints, compile_json_ir_structured
from pipeline.kb.prerequisite_classification_repair_hints import (
    build_prerequisite_classification_supplement,
)
from pipeline.utils.prompt_paths import REQUIRED_PROMPT_PATHS


def _company_kb(*, predicates, rules):
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": predicates,
        "functions": [],
        "rules": rules,
    }


def test_compile_json_ir_structured_has_no_rule_plan_parameter() -> None:
    params = inspect.signature(compile_json_ir_structured).parameters
    assert "rule_plan_llm" not in params


def test_rule_plan_prompt_not_required() -> None:
    assert "rule_plan" not in "\n".join(REQUIRED_PROMPT_PATHS)


def test_micro_company_if_uses_undefined_small_company_fails_with_hint() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "fact",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "observable",
            },
            {
                "name": "is_small_company",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
                "legal_output": True,
                "output_category": "classification",
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
        rules=[
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [
                    {"pred": "is_small_company", "args": ["c", "fy"]},
                    {"pred": "fact", "args": ["c", "fy"]},
                ],
                "then": [{"pred": "is_micro_company", "args": ["c", "fy"]}],
                "operator": "implies",
            }
        ],
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir)
    msg = str(exc.value)
    assert "is_small_company" in msg
    assert "never appear in any rule THEN" in msg or "without a defining rule" in msg


def test_small_company_defined_before_micro_company_passes() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "fact",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "observable",
            },
            {
                "name": "is_small_company",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
            },
            {
                "name": "is_micro_company",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
            },
        ],
        rules=[
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [{"pred": "fact", "args": ["c", "fy"]}],
                "then": [{"pred": "is_small_company", "args": ["c", "fy"]}],
                "operator": "implies",
            },
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [
                    {"pred": "is_small_company", "args": ["c", "fy"]},
                    {"pred": "fact", "args": ["c", "fy"]},
                ],
                "then": [{"pred": "is_micro_company", "args": ["c", "fy"]}],
                "operator": "implies",
            },
        ],
    )
    compile_validate_json_ir(ir)


def test_small_company_observable_does_not_require_derived_definition() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "is_small_company",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
            },
            {
                "name": "is_micro_company",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
            },
        ],
        rules=[
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [{"pred": "is_small_company", "args": ["c", "fy"]}],
                "then": [{"pred": "is_micro_company", "args": ["c", "fy"]}],
                "operator": "implies",
            }
        ],
    )
    compile_validate_json_ir(ir)


def test_derived_not_defined_repair_hint_is_generic() -> None:
    supplement = build_prerequisite_classification_supplement(
        error_message=(
            "derived predicate(s) is_small_company never appear in any rule THEN."
        ),
        symbol_table={
            "predicates": [
                {
                    "name": "is_small_company",
                    "args": ["Company", "FinancialYear"],
                    "returns": "Bool",
                    "kind": "derived",
                }
            ]
        },
        merged_ir={
            "rules": [
                {
                    "if": [{"pred": "is_small_company", "args": ["c", "fy"]}],
                    "then": [{"pred": "is_micro_company", "args": ["c", "fy"]}],
                }
            ]
        },
    )
    assert "is_small_company" in supplement
    assert "directly_observable" in supplement
    assert "micro-company" not in supplement.lower()


def test_build_repair_hints_include_prerequisite_supplement() -> None:
    hints = _build_repair_hints(
        "derived predicate(s) is_small_company never appear in any rule THEN.",
        "prev",
        error_code="derived_predicate_not_defined",
        layer="rules",
        merged_ir={
            "rules": [
                {
                    "if": [{"pred": "is_small_company", "args": ["c", "fy"]}],
                    "then": [],
                }
            ]
        },
        symbol_table={
            "predicates": [
                {
                    "name": "is_small_company",
                    "kind": "derived",
                }
            ]
        },
    )
    assert "PREREQUISITE STATUS" in hints
