"""Temporal support relations exempt from missing_helper_definition when structural."""

from __future__ import annotations

import pytest

from pipeline.kb.json_ir import (
    JSONIRCompilationError,
    SymbolDecl,
    validate_combined_json_ir_schema,
)
from pipeline.kb.json_ir_repair import normalize_error_code
from pipeline.kb.temporal_support import (
    find_temporal_support_symbols,
    legal_effect_predicates_masquerading_as_temporal,
    temporal_support_exempt_from_helper_definition,
)


def _next_fy_decl(*, kind: str = "observable", directly_observable: bool = True, **extra) -> SymbolDecl:
    return SymbolDecl(
        name="next_financial_year",
        args=["FinancialYear", "FinancialYear"],
        returns="Bool",
        kind=kind,
        description="The second financial year immediately follows the first.",
        directly_observable=directly_observable,
        background=extra.get("background", False),
        case_input=extra.get("case_input", False),
        legal_output=extra.get("legal_output"),
        output_category=extra.get("output_category", ""),
    )


def _base_predicates(next_decl: SymbolDecl) -> list[SymbolDecl]:
    return [
        SymbolDecl(
            name="has_legal_personality",
            kind="observable",
            args=["Company"],
            returns="Bool",
        ),
        SymbolDecl(
            name="legal_consequences_apply",
            kind="derived",
            args=["Company", "FinancialYear"],
            returns="Bool",
            legal_output=True,
            output_category="legal_effect",
        ),
        next_decl,
    ]


def _rules_using_next_fy() -> list[dict]:
    return [
        {
            "forall": [
                {"var": "c", "type": "Company"},
                {"var": "y1", "type": "FinancialYear"},
                {"var": "y2", "type": "FinancialYear"},
            ],
            "if": [
                {"pred": "has_legal_personality", "args": ["c"]},
                {"pred": "next_financial_year", "args": ["y1", "y2"]},
            ],
            "then": [{"pred": "legal_consequences_apply", "args": ["c", "y2"]}],
            "operator": "implies",
        }
    ]


def test_temporal_support_exempt_observable_directly_observable():
    decl = _next_fy_decl(kind="observable", directly_observable=True, background=True)
    assert temporal_support_exempt_from_helper_definition(decl) is True
    validate_combined_json_ir_schema(
        {"rules": _rules_using_next_fy()},
        _base_predicates(decl),
        [],
    )


def test_temporal_support_exempt_helper_without_defining_rule():
    decl = _next_fy_decl(kind="helper", directly_observable=False)
    assert temporal_support_exempt_from_helper_definition(decl) is True
    validate_combined_json_ir_schema(
        {"rules": _rules_using_next_fy()},
        _base_predicates(decl),
        [],
    )


def test_temporal_support_derived_still_requires_definition():
    decl = _next_fy_decl(kind="derived", directly_observable=False, legal_output=False)
    assert temporal_support_exempt_from_helper_definition(decl) is False
    with pytest.raises(JSONIRCompilationError) as exc:
        validate_combined_json_ir_schema(
            {"rules": _rules_using_next_fy()},
            _base_predicates(decl),
            [],
        )
    msg = str(exc.value)
    assert "next_financial_year" in msg
    assert "never appear in any rule THEN" in msg or "no defining rule" in msg


def test_non_temporal_helper_still_missing_helper():
    predicates = [
        SymbolDecl(
            name="aux_threshold_exceeded",
            kind="helper",
            args=["Company"],
            returns="Bool",
        ),
        SymbolDecl(name="some_derived", kind="derived", args=["Company"], returns="Bool"),
    ]
    ir = {
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": "aux_threshold_exceeded", "args": ["c"]}],
                "then": [{"pred": "some_derived", "args": ["c"]}],
                "operator": "implies",
            }
        ]
    }
    with pytest.raises(JSONIRCompilationError) as exc:
        validate_combined_json_ir_schema(ir, predicates, [])
    assert normalize_error_code(str(exc.value)) == "missing_helper_definition"
    assert "aux_threshold_exceeded" in str(exc.value)


def test_legal_effect_following_name_not_temporal_support():
    sym = {
        "types": ["Year"],
        "predicates": [
            {
                "name": "consequences_apply_from_following_year",
                "kind": "derived",
                "args": ["Year"],
                "returns": "Bool",
                "legal_output": True,
                "output_category": "legal_effect",
            },
        ],
        "functions": [],
    }
    assert find_temporal_support_symbols(sym) == []
    assert legal_effect_predicates_masquerading_as_temporal(sym) == [
        "consequences_apply_from_following_year"
    ]
    assert temporal_support_exempt_from_helper_definition(sym["predicates"][0]) is False
