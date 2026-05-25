"""Query target selection prefers legal-output over temporal support relations."""

from __future__ import annotations

import pytest

from pipeline.extraction.json_ir import ExtractionIRValidationError, normalize_query_ir
from pipeline.extraction.query_target_selection import (
    apply_query_target_selection,
    is_temporal_support_background_target,
    select_boolean_query_predicate,
)
from pipeline.kb.legal_effect import predicate_represents_legal_effect_output
from pipeline.semantic.legal_question import question_asks_legal_conclusion

_EFFECT_QUESTION = (
    "Do the legal consequences apply from the financial year following the financial year 2025?"
)

_KB_SCHEMA = {
    "predicates": [
        {
            "name": "next_financial_year",
            "kind": "observable",
            "args": ["FinancialYear", "FinancialYear"],
            "returns": "Bool",
            "directly_observable": True,
            "background": True,
            "description": "The second financial year immediately follows the first.",
        },
        {
            "name": "consequences_apply_due_to_criteria_change",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "legal_output": True,
            "output_category": "legal_effect",
            "description": "Legal consequences apply from the following financial year.",
        },
        {
            "name": "is_small_company",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "output_category": "classification",
            "description": "Company qualifies as small.",
        },
    ],
    "functions": [],
}

_CASE = {
    "entities": {
        "Company": ["acme"],
        "FinancialYear": ["fy2025", "fy2026"],
    },
    "facts": [],
}


def test_temporal_support_background_detected():
    sym = _KB_SCHEMA["predicates"][0]
    assert is_temporal_support_background_target(sym) is True


def test_legal_effect_question_prefers_legal_output_predicate():
    chosen, diag = apply_query_target_selection(
        pred_hint="next_financial_year",
        user_question=_EFFECT_QUESTION,
        kb_schema=_KB_SCHEMA,
        current_pred="next_financial_year",
    )
    assert chosen == "consequences_apply_due_to_criteria_change"
    assert "temporal_support_not_final_answer" in str(diag.get("rejected", []))
    assert any(
        r.get("name") == "next_financial_year"
        and r.get("rejection_reason") == "temporal_support_not_final_answer"
        for r in diag.get("rejected", [])
    )


def test_temporal_not_chosen_by_lexical_overlap_alone():
    sel = select_boolean_query_predicate(
        pred_hint="next_financial_year",
        user_question=_EFFECT_QUESTION,
        kb_schema=_KB_SCHEMA,
        current_pred="next_financial_year",
    )
    assert sel.chosen_predicate == "consequences_apply_due_to_criteria_change"
    assert sel.chosen_predicate != "next_financial_year"


def test_normalize_query_ir_selects_legal_output():
    query = normalize_query_ir(
        {
            "kind": "predicate",
            "predicate_hint": "next_financial_year",
            "mode": "boolean",
            "args": ["acme", "fy2026"],
        },
        _CASE,
        _KB_SCHEMA,
        _EFFECT_QUESTION,
    )
    assert query["predicate"] == "consequences_apply_due_to_criteria_change"
    assert query.get("predicate_kind") == "derived"
    diag = query.get("query_target_selection") or {}
    assert diag.get("chosen_predicate") == "consequences_apply_due_to_criteria_change"


def test_only_temporal_relation_fallback_with_warning():
    schema = {
        "predicates": [_KB_SCHEMA["predicates"][0]],
        "functions": [],
    }
    sel = select_boolean_query_predicate(
        pred_hint="next_financial_year",
        user_question=_EFFECT_QUESTION,
        kb_schema=schema,
        current_pred="next_financial_year",
    )
    assert sel.warning == "no_legal_output_predicate_available"


def test_classification_question_unchanged():
    q = "Is the company a small company in financial year 2025?"
    assert question_asks_legal_conclusion(q) or True
    chosen, diag = apply_query_target_selection(
        pred_hint="is_small_company",
        user_question=q,
        kb_schema=_KB_SCHEMA,
        current_pred="is_small_company",
    )
    assert chosen == "is_small_company"


def test_validate_rejects_temporal_when_legal_output_exists():
    with pytest.raises(ExtractionIRValidationError) as exc:
        from pipeline.extraction.json_ir import _validate_query_target_for_legal_question

        _validate_query_target_for_legal_question(
            "next_financial_year",
            _EFFECT_QUESTION,
            _KB_SCHEMA,
        )
    assert "temporal support" in str(exc.value).lower()


def test_legal_effect_name_not_temporal_support():
    sym = _KB_SCHEMA["predicates"][1]
    assert predicate_represents_legal_effect_output(
        sym["name"],
        kind=sym["kind"],
        legal_output=True,
        output_category=sym["output_category"],
    )
    assert not is_temporal_support_background_target(sym)
