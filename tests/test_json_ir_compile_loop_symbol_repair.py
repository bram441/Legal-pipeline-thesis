"""Compile-loop control flow for chained symbol-stage repairs."""

from __future__ import annotations

import pytest

from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.json_ir import JSONIRCompilationError, SCHEMA_DESIGN_TAG, validate_json_ir_symbols
from pipeline.kb.json_ir_compile_loop import CompileLoopLimits, _build_repair_hints, compile_json_ir_structured
from pipeline.kb.json_ir_repair import (
    JsonIRErrorKind,
    classify_json_ir_validation_error,
    is_symbol_stage_repairable_error,
    normalize_error_code,
)

_EFFECT_LAW = (
    "When a condition holds for two consecutive financial years, "
    "the legal consequences apply from the following financial year."
)
_EFFECT_QUESTION = "Do the legal consequences apply from the following financial year?"
_EFFECT_SCOPE = {
    "contains_effect_language": True,
    "question_asks_legal_effect": True,
}


def _repair_summary(exc: LawCompilationError) -> dict:
    snap = exc.repair_snapshot or {}
    summary = snap.get("repair_summary")
    return summary if isinstance(summary, dict) else snap

_NO_DERIVED_MSG = (
    SCHEMA_DESIGN_TAG
    + ": Symbol table contains no derived legal outputs. A reusable legal KB must expose "
    "at least one derived predicate/function representing legal classifications, consequences, "
    "rights, obligations, permissions, prohibitions, exceptions, sanctions, validity results, "
    "entitlements, or exclusions."
)


def _observable_only_symbols() -> dict:
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {"name": "has_legal_personality", "kind": "observable", "args": ["Company"], "returns": "Bool"},
        ],
        "functions": [
            {
                "name": "annual_net_turnover",
                "kind": "observable",
                "args": ["Company", "FinancialYear"],
                "returns": "Real",
            },
        ],
    }


def _symbols_with_legal_effect_no_temporal() -> dict:
    sym = _observable_only_symbols()
    sym["predicates"].append(
        {
            "name": "legal_consequences_apply_from_following_financial_year",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "legal_output": True,
            "output_category": "legal_effect",
        }
    )
    return sym


def _symbols_with_temporal() -> dict:
    sym = _symbols_with_legal_effect_no_temporal()
    sym["functions"].append(
        {
            "name": "next_financial_year",
            "kind": "helper",
            "args": ["FinancialYear"],
            "returns": "FinancialYear",
            "description": "The financial year immediately following the given year.",
        }
    )
    return sym


def test_no_derived_maps_to_missing_legal_effect_and_symbols_repair():
    assert normalize_error_code(_NO_DERIVED_MSG) == "missing_legal_effect_output"
    assert is_symbol_stage_repairable_error("missing_legal_effect_output")
    assert (
        classify_json_ir_validation_error(_NO_DERIVED_MSG)
        == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
    )


def test_no_derived_repair_hints_include_legal_effect_supplement():
    hints = _build_repair_hints(
        _NO_DERIVED_MSG,
        "",
        error_code="missing_legal_effect_output",
        layer="symbols",
        law_text=_EFFECT_LAW,
        question_text=_EFFECT_QUESTION,
        scope_metadata=_EFFECT_SCOPE,
        symbol_table=_observable_only_symbols(),
    )
    assert "MISSING LEGAL-EFFECT OUTPUT" in hints
    assert "derived" in hints.lower()


def test_chained_symbol_repair_reaches_temporal_then_rules():
    symbol_versions: list[int] = []
    repair_hints_seen: list[str] = []

    def symbols_llm(_src, repair=False, error_message="", machine_hints="", **kwargs):
        symbol_versions.append(len(symbol_versions) + 1)
        if repair:
            repair_hints_seen.append(machine_hints)
        if len(symbol_versions) == 1:
            return _observable_only_symbols(), "{}"
        if len(symbol_versions) == 2:
            return _symbols_with_legal_effect_no_temporal(), "{}"
        return _symbols_with_temporal(), "{}"

    rules_calls: list[int] = []

    def rules_llm(_src, _symbol_table, **kwargs):
        rules_calls.append(1)
        return {"rules": []}, "[]"

    limits = CompileLoopLimits(
        max_symbol_versions=2,
        max_rules_attempts_per_symbol_version=1,
        max_total_kb_llm_calls=6,
        repeated_error_limit=3,
        max_rules_before_symbol_escalation=2,
    )

    with pytest.raises(LawCompilationError) as exc:
        compile_json_ir_structured(
            _EFFECT_LAW,
            symbols_llm=symbols_llm,
            rules_llm=rules_llm,
            repair_context_fn=lambda **kw: "",
            limits=limits,
            scope_metadata=_EFFECT_SCOPE,
            question_text=_EFFECT_QUESTION,
        )

    assert len(symbol_versions) >= 3, "expected symbol_v03 after chained symbol repairs"
    assert any("MISSING TEMPORAL SUPPORT SYMBOL" in h for h in repair_hints_seen)
    assert len(rules_calls) >= 1
    summary = _repair_summary(exc.value)
    assert summary.get("symbol_version_count", 0) >= 3


def test_temporal_failure_with_budget_stops_only_when_symbol_cap_exhausted():
    symbol_versions: list[int] = []

    def symbols_llm(_src, repair=False, **kwargs):
        symbol_versions.append(len(symbol_versions) + 1)
        if len(symbol_versions) == 1:
            return _observable_only_symbols(), "{}"
        return _symbols_with_legal_effect_no_temporal(), "{}"

    limits = CompileLoopLimits(
        max_symbol_versions=2,
        max_rules_attempts_per_symbol_version=1,
        max_total_kb_llm_calls=3,
        repeated_error_limit=3,
        max_rules_before_symbol_escalation=2,
    )

    with pytest.raises(LawCompilationError) as exc:
        compile_json_ir_structured(
            _EFFECT_LAW,
            symbols_llm=symbols_llm,
            rules_llm=lambda *_a, **_k: ({"rules": []}, "[]"),
            repair_context_fn=lambda **kw: "",
            limits=limits,
            scope_metadata=_EFFECT_SCOPE,
            question_text=_EFFECT_QUESTION,
        )

    summary = _repair_summary(exc.value)
    assert len(symbol_versions) >= 3
    assert summary.get("final_normalized_error_code") == "missing_temporal_support_symbol"
    assert summary.get("final_failure_category") in {
        "validation_exhausted",
        "symbol_budget_exhausted",
        "budget_exhausted",
    }
    assert summary.get("budget_exhausted") is not True


def test_threshold_cardinality_not_symbol_stage_repairable():
    msg = (
        SCHEMA_DESIGN_TAG
        + ": Cannot prove disqualification; add an exclusion rule such as not_qualified."
    )
    assert normalize_error_code(msg) == "missing_threshold_classification_exclusion"
    assert not is_symbol_stage_repairable_error("missing_threshold_classification_exclusion")


def test_missing_helper_not_symbol_stage_repairable_code():
    msg = "Helper predicate 'aux_threshold_exceeded' is used as a rule condition but has no defining rule"
    assert normalize_error_code(msg) == "missing_helper_definition"
    assert not is_symbol_stage_repairable_error("missing_helper_definition")
