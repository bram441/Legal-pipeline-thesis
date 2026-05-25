"""Legal-effect symbols repair card and prompt supplements."""

from __future__ import annotations

import pytest

from pipeline.extraction.json_ir import (
    ExtractionIRValidationError,
    _validate_query_target_for_legal_question,
)
from pipeline.kb.json_ir_compile_loop import _build_repair_hints
from pipeline.kb.json_ir_repair import normalize_error_code
from pipeline.kb.legal_effect_repair_hints import (
    build_missing_legal_effect_repair_supplement,
    suggest_legal_effect_predicate_names,
)
from pipeline.kb.repair_cards import format_repair_card, get_repair_card

from tests.test_legal_effect_validation import (
    LAW_CONSEQUENCES_TIMING,
    QUESTION_CONSEQUENCES,
    _derived,
)

LEGAL_EFFECT_ERROR = (
    "JSON_IR_SCHEMA_DESIGN_ERROR: The scoped law text contains legal-effect or timing language "
    '("The consequences apply from the financial year following the year in which the '
    'criteria were exceeded for the second consecutive time."), but the JSON IR has no derived '
    "legal-output predicate representing that effect. Do not model the provision only as "
    "classification or threshold predicates. Repair layer: symbols."
)

SCOPE_DUAL_PARAGRAPH = {
    "contains_effect_language": True,
    "question_asks_legal_effect": True,
    "cited_paragraph": 2,
    "included_dependency_chunks": ["1:24/p1"],
    "selected_chunk_ids": ["1:24/p2", "1:24/p1"],
}


def test_a_missing_legal_effect_selects_specific_card():
    code = normalize_error_code(LEGAL_EFFECT_ERROR)
    assert code == "missing_legal_effect_output"
    assert get_repair_card(code).card_id == "missing_legal_effect_output"


def test_b_card_contains_legal_output_and_output_category_guidance():
    card = format_repair_card("missing_legal_effect_output")
    assert "legal_output=true" in card
    assert "output_category" in card
    assert "legal_effect" in card
    assert "classification predicates" in card.lower()


def test_c_repair_hint_includes_question_effect_and_candidates():
    symbol_table = {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            _derived("is_small_company", ["Company", "FinancialYear"], output_category="classification"),
        ],
    }
    supplement = build_missing_legal_effect_repair_supplement(
        LEGAL_EFFECT_ERROR,
        law_text=LAW_CONSEQUENCES_TIMING,
        question_text=QUESTION_CONSEQUENCES,
        scope_metadata=SCOPE_DUAL_PARAGRAPH,
        symbol_table=symbol_table,
    )
    assert "consequences apply" in supplement.lower() or "financial year following" in supplement.lower()
    assert QUESTION_CONSEQUENCES[:40] in supplement
    assert "legal_output" in supplement
    assert "output_category" in supplement
    assert "is_small_company" in supplement
    assert "classification" in supplement.lower() and "effect" in supplement.lower()

    names = suggest_legal_effect_predicate_names(LAW_CONSEQUENCES_TIMING, QUESTION_CONSEQUENCES)
    assert any("consequence" in n for n in names)

    hints = _build_repair_hints(
        LEGAL_EFFECT_ERROR,
        "{}",
        error_code="missing_legal_effect_output",
        layer="symbols",
        law_text=LAW_CONSEQUENCES_TIMING,
        question_text=QUESTION_CONSEQUENCES,
        scope_metadata=SCOPE_DUAL_PARAGRAPH,
        symbol_table=symbol_table,
    )
    assert "MISSING LEGAL-EFFECT OUTPUT" in hints
    assert "Do the consequences" in hints or "consequences" in hints.lower()


def test_d_effect_question_must_not_fall_back_to_classification():
    kb = {
        "predicates": [
            _derived("is_micro_company", ["Company", "FinancialYear"], output_category="classification"),
            _derived("is_small_company", ["Company", "FinancialYear"], output_category="classification"),
        ]
    }
    with pytest.raises(ExtractionIRValidationError):
        _validate_query_target_for_legal_question("is_micro_company", QUESTION_CONSEQUENCES, kb)
