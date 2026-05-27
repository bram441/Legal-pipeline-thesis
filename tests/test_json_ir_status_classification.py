"""Generic status/classification observable vs derived validation and repair hints."""

from __future__ import annotations

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir, validate_json_ir_symbols
from pipeline.kb.json_ir_compile_loop import _build_repair_hints
from pipeline.kb.prerequisite_classification_repair_hints import (
    build_prerequisite_classification_supplement,
)


def _person_kb(*, predicates, rules):
    return {
        "types": ["Person"],
        "predicates": predicates,
        "functions": [],
        "rules": rules,
    }


def test_is_foreigner_observable_directly_observable_accepted() -> None:
    ir = _person_kb(
        predicates=[
            {
                "name": "is_foreigner",
                "args": ["Person"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
            },
            {
                "name": "may_enter",
                "args": ["Person"],
                "returns": "Bool",
                "kind": "derived",
                "legal_output": True,
            },
        ],
        rules=[
            {
                "forall": [{"var": "p", "type": "Person"}],
                "if": [{"pred": "is_foreigner", "args": ["p"]}],
                "then": [{"pred": "may_enter", "args": ["p"]}],
                "operator": "implies",
            }
        ],
    )
    compile_validate_json_ir(ir)


def test_is_foreigner_observable_without_directly_observable_rejected() -> None:
    with pytest.raises(JSONIRCompilationError) as exc:
        validate_json_ir_symbols(
            {
                "types": ["Person"],
                "predicates": [
                    {
                        "name": "is_foreigner",
                        "args": ["Person"],
                        "returns": "Bool",
                        "kind": "observable",
                    },
                    {
                        "name": "may_enter",
                        "args": ["Person"],
                        "returns": "Bool",
                        "kind": "derived",
                        "legal_output": True,
                    },
                ],
                "functions": [],
            }
        )
    assert "status/classification" in str(exc.value).lower()
    assert "directly_observable" in str(exc.value)


def test_is_foreigner_derived_in_if_without_then_gives_targeted_hint() -> None:
    msg = (
        "JSON_IR_RULE_DESIGN_ERROR: Derived predicate 'is_foreigner' is used in rules[0].if "
        "without a defining rule (never in any rule THEN)."
    )
    supplement = build_prerequisite_classification_supplement(
        error_message=msg,
        symbol_table={
            "predicates": [
                {
                    "name": "is_foreigner",
                    "kind": "derived",
                }
            ]
        },
        merged_ir={
            "rules": [
                {
                    "if": [{"pred": "is_foreigner", "args": ["p"]}],
                    "then": [{"pred": "may_enter", "args": ["p"]}],
                }
            ]
        },
    )
    assert "is_foreigner" in supplement
    assert "directly_observable" in supplement
    assert "PREREQUISITE STATUS" in supplement


def test_third_country_national_derived_from_observable_subconditions_passes() -> None:
    ir = _person_kb(
        predicates=[
            {
                "name": "is_not_union_citizen",
                "args": ["Person"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
            },
            {
                "name": "not_covered_by_free_movement_law",
                "args": ["Person"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
            },
            {
                "name": "is_third_country_national",
                "args": ["Person"],
                "returns": "Bool",
                "kind": "derived",
            },
            {
                "name": "requires_visa",
                "args": ["Person"],
                "returns": "Bool",
                "kind": "derived",
                "legal_output": True,
            },
        ],
        rules=[
            {
                "forall": [{"var": "p", "type": "Person"}],
                "if": [
                    {"pred": "is_not_union_citizen", "args": ["p"]},
                    {"pred": "not_covered_by_free_movement_law", "args": ["p"]},
                ],
                "then": [{"pred": "is_third_country_national", "args": ["p"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "p", "type": "Person"}],
                "if": [
                    {"pred": "is_not_union_citizen", "args": ["p"]},
                    {"pred": "not_covered_by_free_movement_law", "args": ["p"]},
                ],
                "then": [{"pred": "requires_visa", "args": ["p"]}],
                "operator": "implies",
            },
        ],
    )
    compile_validate_json_ir(ir)


def test_circular_prerequisite_hint_warns_against_mutual_definitions() -> None:
    supplement = build_prerequisite_classification_supplement(
        error_message=(
            "derived predicate(s) is_foreigner, is_third_country_national never appear in any rule THEN."
        ),
        symbol_table={
            "predicates": [
                {"name": "is_foreigner", "kind": "derived"},
                {"name": "is_third_country_national", "kind": "derived"},
            ]
        },
        merged_ir={
            "rules": [
                {
                    "if": [{"pred": "is_third_country_national", "args": ["p"]}],
                    "then": [],
                },
                {
                    "if": [
                        {"pred": "is_foreigner", "args": ["p"]},
                        {"pred": "is_third_country_national", "args": ["p"]},
                    ],
                    "then": [],
                },
            ]
        },
    )
    assert "Circular dependency" in supplement
    assert "do not define each from the other" in supplement.lower()


def test_directly_observable_legal_output_still_rejected() -> None:
    with pytest.raises(JSONIRCompilationError) as exc:
        validate_json_ir_symbols(
            {
                "types": ["Person"],
                "predicates": [
                    {
                        "name": "is_eligible_status",
                        "args": ["Person"],
                        "returns": "Bool",
                        "kind": "observable",
                        "directly_observable": True,
                        "legal_output": True,
                        "output_category": "classification",
                    },
                    {
                        "name": "placeholder_derived",
                        "args": ["Person"],
                        "returns": "Bool",
                        "kind": "derived",
                        "legal_output": True,
                    },
                ],
                "functions": [],
            }
        )
    assert "directly_observable" in str(exc.value)
    assert "legal_output" in str(exc.value)


def test_build_repair_hints_include_status_supplement_for_missing_helper_code() -> None:
    hints = _build_repair_hints(
        "Derived predicate 'is_foreigner' is used in rules[0].if without a defining rule.",
        "prev",
        error_code="missing_helper_definition",
        layer="rules",
        merged_ir={
            "rules": [{"if": [{"pred": "is_foreigner", "args": ["p"]}], "then": []}]
        },
        symbol_table={"predicates": [{"name": "is_foreigner", "kind": "derived"}]},
    )
    assert "PREREQUISITE STATUS" in hints
    assert "directly_observable" in hints
