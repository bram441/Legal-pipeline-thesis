"""Early symbol-stage legal-effect output validation and compile-loop routing."""

from __future__ import annotations

import pytest

from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.json_ir import JSONIRCompilationError, validate_json_ir_symbols
from pipeline.kb.json_ir_compile_loop import CompileLoopLimits, compile_json_ir_structured
from pipeline.kb.json_ir_repair import (
    JsonIRErrorKind,
    classify_json_ir_validation_error,
    normalize_error_code,
)
from pipeline.kb.legal_effect import validate_legal_effect_symbols_stage

_EFFECT_LAW_SNIPPET = (
    "The legal consequences apply from the following financial year."
)

_CLASSIFICATION_SCOPE = {
    "contains_effect_language": False,
    "question_asks_legal_effect": False,
    "selected_granularity": "paragraph",
}

_EFFECT_SCOPE = {
    "contains_effect_language": True,
    "question_asks_legal_effect": True,
    "selected_granularity": "paragraph",
    "cited_paragraph": 2,
}


def _classification_only_symbols() -> dict:
    return {
        "types": [{"name": "Company", "description": "Legal entity"}],
        "predicates": [
            {
                "name": "declared_revenue_known",
                "kind": "observable",
                "args": ["Company"],
                "returns": "Bool",
            },
            {
                "name": "is_small_company",
                "kind": "derived",
                "args": ["Company"],
                "returns": "Bool",
                "output_category": "classification",
            },
        ],
        "functions": [
            {
                "name": "revenue",
                "kind": "observable",
                "args": ["Company"],
                "returns": "Int",
            },
        ],
    }


def _symbols_with_legal_effect() -> dict:
    base = _classification_only_symbols()
    base["types"].append({"name": "FinancialYear", "description": "Financial year"})
    base["predicates"].append(
        {
            "name": "legal_consequences_apply_from_following_financial_year",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "legal_output": True,
            "output_category": "legal_effect",
        }
    )
    base["functions"].append(
        {
            "name": "next_financial_year",
            "kind": "helper",
            "args": ["FinancialYear"],
            "returns": "FinancialYear",
            "description": "Financial year immediately following the given year.",
        }
    )
    return base


def test_symbol_validation_fails_classification_only_on_effect_scope():
    with pytest.raises(JSONIRCompilationError) as exc:
        validate_json_ir_symbols(
            _classification_only_symbols(),
            law_text_for_lints=_EFFECT_LAW_SNIPPET,
            scope_metadata=_EFFECT_SCOPE,
        )
    msg = str(exc.value)
    assert "JSON_IR_SCHEMA_DESIGN_ERROR" in msg
    assert "legal-effect or timing language" in msg
    assert normalize_error_code(msg) == "missing_legal_effect_output"
    assert (
        classify_json_ir_validation_error(msg)
        == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
    )


def test_symbol_validation_passes_classification_scope():
    validate_json_ir_symbols(
        _classification_only_symbols(),
        law_text_for_lints="A company is a small company when its revenue does not exceed a threshold.",
        scope_metadata=_CLASSIFICATION_SCOPE,
    )


def test_symbol_validation_passes_with_legal_output_derived():
    validate_json_ir_symbols(
        _symbols_with_legal_effect(),
        law_text_for_lints=_EFFECT_LAW_SNIPPET,
        scope_metadata=_EFFECT_SCOPE,
    )


def test_compile_loop_routes_missing_effect_before_rules():
    rules_calls: list[int] = []

    def symbols_llm(_src, repair=False, **kwargs):
        return _classification_only_symbols(), "{}"

    def rules_llm(_src, _symbol_table, **kwargs):
        rules_calls.append(1)
        return {"rules": []}, "[]"

    limits = CompileLoopLimits(
        max_symbol_versions=2,
        max_rules_attempts_per_symbol_version=2,
        max_total_kb_llm_calls=4,
        repeated_error_limit=3,
        max_rules_before_symbol_escalation=2,
    )

    with pytest.raises(LawCompilationError):
        compile_json_ir_structured(
            _EFFECT_LAW_SNIPPET,
            symbols_llm=symbols_llm,
            rules_llm=rules_llm,
            repair_context_fn=lambda **kw: "",
            limits=limits,
            scope_metadata=_EFFECT_SCOPE,
            question_text="From when do the legal consequences apply?",
        )

    assert rules_calls == []


def test_run006_style_loop_reaches_rules_after_effect_symbol_added():
    symbol_calls: list[bool] = []
    rules_calls: list[int] = []

    def symbols_llm(_src, repair=False, **kwargs):
        symbol_calls.append(repair)
        if not repair:
            return _classification_only_symbols(), "{}"
        return _symbols_with_legal_effect(), "{}"

    def rules_llm(_src, _symbol_table, **kwargs):
        rules_calls.append(1)
        return {"rules": []}, "[]"

    limits = CompileLoopLimits(
        max_symbol_versions=3,
        max_rules_attempts_per_symbol_version=2,
        max_total_kb_llm_calls=7,
        repeated_error_limit=3,
        max_rules_before_symbol_escalation=2,
    )

    with pytest.raises(LawCompilationError):
        compile_json_ir_structured(
            _EFFECT_LAW_SNIPPET,
            symbols_llm=symbols_llm,
            rules_llm=rules_llm,
            repair_context_fn=lambda **kw: "",
            limits=limits,
            scope_metadata=_EFFECT_SCOPE,
            question_text="From when do the legal consequences apply?",
        )

    assert symbol_calls[0] is False
    assert any(symbol_calls[1:])
    assert len(rules_calls) >= 1


def test_symbols_stage_helper_requires_effect_predicate():
    predicates, _, _ = validate_json_ir_symbols(_classification_only_symbols())
    with pytest.raises(JSONIRCompilationError):
        validate_legal_effect_symbols_stage(
            predicates,
            law_text_for_lints=_EFFECT_LAW_SNIPPET,
            scope_metadata=_EFFECT_SCOPE,
        )
