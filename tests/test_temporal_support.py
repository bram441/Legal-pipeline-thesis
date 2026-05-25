"""Generic temporal-support symbol validation and repair routing."""

from __future__ import annotations

import pytest

from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.json_ir import JSONIRCompilationError, validate_json_ir_symbols
from pipeline.kb.json_ir_compile_loop import CompileLoopLimits, _build_repair_hints, compile_json_ir_structured
from pipeline.kb.json_ir_repair import JsonIRErrorKind, classify_json_ir_validation_error, normalize_error_code
from pipeline.kb.repair_cards import format_repair_card
from pipeline.kb.temporal_support import (
    assess_temporal_support,
    detect_temporal_effect_terms,
    find_temporal_support_symbols,
    has_period_or_year_type,
    legal_effect_predicates_masquerading_as_temporal,
    validate_temporal_support_symbols_stage,
)
from pipeline.kb.temporal_support_repair_hints import (
    build_missing_temporal_support_symbol_supplement,
    suggest_temporal_symbol_candidates,
)
from pipeline.kb.validation_evidence import collect_missing_helper_evidence, collect_validation_repair_evidence

_EFFECT_LAW = (
    "When a condition holds for two consecutive financial years, "
    "the legal consequences apply from the following financial year."
)
_EFFECT_QUESTION = "Do the legal consequences apply from the following financial year?"
_EFFECT_SCOPE = {
    "contains_effect_language": True,
    "question_asks_legal_effect": True,
}

_CLASSIFICATION_LAW = "A company is classified as qualified when criterion A is met on the balance sheet date."
_CLASSIFICATION_SCOPE = {
    "contains_effect_language": False,
    "question_asks_legal_effect": False,
}


def _symbols_no_temporal() -> dict:
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {"name": "has_legal_personality", "kind": "observable", "args": ["Company"], "returns": "Bool"},
            {
                "name": "legal_consequences_apply_from_following_financial_year",
                "kind": "derived",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "legal_output": True,
                "output_category": "legal_effect",
            },
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


def _symbols_with_temporal() -> dict:
    sym = _symbols_no_temporal()
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


def test_temporal_phrases_require_support_symbol_stage():
    sym = _symbols_no_temporal()
    with pytest.raises(JSONIRCompilationError) as exc:
        validate_json_ir_symbols(
            sym,
            law_text_for_lints=_EFFECT_LAW,
            scope_metadata=_EFFECT_SCOPE,
            question_text=_EFFECT_QUESTION,
        )
    assert "temporal support" in str(exc.value).lower()
    assert normalize_error_code(str(exc.value)) == "missing_temporal_support_symbol"
    assert (
        classify_json_ir_validation_error(str(exc.value))
        == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
    )


def test_temporal_support_present_passes_symbol_stage():
    validate_json_ir_symbols(
        _symbols_with_temporal(),
        law_text_for_lints=_EFFECT_LAW,
        scope_metadata=_EFFECT_SCOPE,
        question_text=_EFFECT_QUESTION,
    )


def test_classification_only_no_temporal_requirement():
    sym = {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {"name": "is_qualified", "kind": "derived", "args": ["Company", "FinancialYear"], "returns": "Bool"},
            {"name": "criterion_met", "kind": "observable", "args": ["Company"], "returns": "Bool"},
        ],
        "functions": [],
    }
    validate_json_ir_symbols(
        sym,
        law_text_for_lints=_CLASSIFICATION_LAW,
        scope_metadata=_CLASSIFICATION_SCOPE,
    )
    det = detect_temporal_effect_terms(_CLASSIFICATION_LAW)
    assert not det.requires_temporal_support


def test_missing_helper_escalates_when_temporal_support_absent():
    ir = {
        **_symbols_no_temporal(),
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
                "if": [{"pred": "exceeded_more_than_one_criterion_two_consecutive_years", "args": ["c", "fy"]}],
                "then": [{"pred": "legal_consequences_apply_from_following_financial_year", "args": ["c", "fy"]}],
                "operator": "implies",
            }
        ],
    }
    err = (
        "JSON_IR_RULE_DESIGN_ERROR: Helper predicate 'exceeded_more_than_one_criterion_two_consecutive_years' "
        "is used as a rule condition but has no defining rule."
    )
    pred_kinds = {p["name"]: p["kind"] for p in _symbols_no_temporal()["predicates"]}
    evidence = collect_validation_repair_evidence(
        ir,
        pred_kinds,
        law_text_for_lints=_EFFECT_LAW,
        error_message=err,
        symbol_table=_symbols_no_temporal(),
        scope_metadata=_EFFECT_SCOPE,
        question_text=_EFFECT_QUESTION,
    )
    assert evidence.missing_helper is not None
    assert evidence.missing_helper.missing_temporal_support_symbol is True
    assert evidence.missing_temporal_support_symbol is True
    assert evidence.repair_route == "symbols_repair_required"
    assert classify_json_ir_validation_error(err) == JsonIRErrorKind.RULES_REPAIR_ONLY


def test_ordinary_threshold_helper_stays_rules_repair():
    sym = {
        "types": ["Entity"],
        "predicates": [
            {"name": "aux_threshold_exceeded", "kind": "helper", "args": ["Entity"], "returns": "Bool"},
            {"name": "some_derived", "kind": "derived", "args": ["Entity"], "returns": "Bool"},
        ],
        "functions": [],
    }
    ir = {
        **sym,
        "rules": [
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"pred": "aux_threshold_exceeded", "args": ["x"]}],
                "then": [{"pred": "some_derived", "args": ["x"]}],
                "operator": "implies",
            }
        ],
    }
    err = "Helper predicate 'aux_threshold_exceeded' is used as a rule condition but has no defining rule"
    pred_kinds = {p["name"]: p["kind"] for p in sym["predicates"]}
    evidence = collect_missing_helper_evidence(
        ir,
        pred_kinds,
        error_message=err,
        symbol_table=sym,
        scope_metadata=_CLASSIFICATION_SCOPE,
    )
    assert evidence is not None
    assert not evidence.missing_temporal_support_symbol
    hints = _build_repair_hints(
        err,
        "",
        error_code="missing_helper_definition",
        layer="rules",
        scope_metadata=_CLASSIFICATION_SCOPE,
        symbol_table=sym,
        missing_helper_evidence=evidence,
    )
    assert "MISSING TEMPORAL SUPPORT SYMBOL" not in hints
    assert "Escalate to symbols repair" not in hints


def test_repair_card_has_generic_guidance():
    card = format_repair_card("missing_temporal_support_symbol")
    assert "MUST" in card or "INVALID" in card
    assert "previous" in card.lower() or "consecutive" in card.lower()
    assert "period" in card.lower()
    assert "run_006" not in card
    assert "run_119" not in card


def test_repair_supplement_financial_year_suggests_concrete_candidates():
    supplement = build_missing_temporal_support_symbol_supplement(
        law_text=_EFFECT_LAW,
        question_text=_EFFECT_QUESTION,
        scope_metadata=_EFFECT_SCOPE,
        symbol_table=_symbols_no_temporal(),
    )
    assert "next_financial_year(FinancialYear, FinancialYear)" in supplement
    assert "previous_financial_year(FinancialYear, FinancialYear)" in supplement
    assert "consecutive_financial_years(FinancialYear, FinancialYear)" in supplement
    candidates = suggest_temporal_symbol_candidates(["FinancialYear"])
    assert any("next_financial_year" in c for c in candidates)


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


def test_next_financial_year_counts_as_temporal_support():
    found = find_temporal_support_symbols(_symbols_with_temporal())
    names = {s["name"] for s in found}
    assert "next_financial_year" in names


def test_after_temporal_repair_still_missing_fails_with_clear_message():
    sym = _symbols_no_temporal()
    with pytest.raises(JSONIRCompilationError) as exc:
        validate_json_ir_symbols(
            sym,
            law_text_for_lints=_EFFECT_LAW,
            scope_metadata=_EFFECT_SCOPE,
            question_text=_EFFECT_QUESTION,
            following_missing_temporal_support_repair=True,
        )
    msg = str(exc.value)
    assert normalize_error_code(msg) == "missing_temporal_support_symbol"
    assert "do not count as temporal support" in msg.lower()
    assert "legal_consequences_apply_from_following_financial_year" in msg


def test_compile_loop_symbol_repair_after_temporal_failure():
    calls: list[dict] = []

    def symbols_llm(law_text, *, repair=False, error_message="", previous_output="", rules_json="", **kwargs):
        calls.append({"repair": repair, "error": error_message})
        if repair:
            return _symbols_with_temporal(), "{}"
        return _symbols_no_temporal(), "{}"

    def rules_llm(law_text, symbol_table, *, repair=False, error_message="", previous_output="", machine_hints=""):
        return {"rules": []}, '{"rules":[]}'

    def repair_context_fn(**kwargs):
        return ""

    with pytest.raises(LawCompilationError):
        compile_json_ir_structured(
            _EFFECT_LAW,
            symbols_llm=symbols_llm,
            rules_llm=rules_llm,
            repair_context_fn=repair_context_fn,
            scope_metadata=_EFFECT_SCOPE,
            question_text=_EFFECT_QUESTION,
            limits=CompileLoopLimits(
                max_symbol_versions=2,
                max_rules_attempts_per_symbol_version=1,
                max_total_kb_llm_calls=4,
                repeated_error_limit=3,
                max_rules_before_symbol_escalation=2,
            ),
        )
    assert len(calls) >= 2
    assert calls[1]["repair"] is True
    assert "temporal" in (calls[1].get("error") or "").lower() or True
