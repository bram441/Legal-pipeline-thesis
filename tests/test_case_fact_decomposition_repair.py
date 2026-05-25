"""Decomposition-oriented case extraction repair hints and empty-fact retry."""

from __future__ import annotations

import pytest

from pipeline.extraction.case_fact_validation import (
    CaseFactAssertionRejected,
    build_rejection_diagnostics,
    case_object_has_non_entity_facts,
    decomposition_required_from_case_text,
    suggest_observable_replacements,
    validate_decomposition_repair_or_raise,
)
from pipeline.extraction.extractor import _run_case_extraction_loop


_THRESHOLD_KB = {
    "predicates": [
        {
            "name": "exceeds_more_than_one_criterion",
            "kind": "helper",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "description": "Company exceeds more than one criterion threshold.",
        },
        {
            "name": "legal_consequences_apply",
            "kind": "derived",
            "args": ["Company", "FinancialYear"],
            "returns": "Bool",
            "legal_output": True,
            "output_category": "legal_effect",
        },
    ],
    "functions": [
        {
            "name": "annual_average_number_of_employees",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Int",
            "description": "Annual average number of employees.",
        },
        {
            "name": "annual_net_turnover_excluding_vat",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Real",
            "description": "Annual net turnover excluding VAT.",
        },
        {
            "name": "total_assets",
            "kind": "observable",
            "args": ["Company", "FinancialYear"],
            "returns": "Real",
            "description": "Balance sheet total assets.",
        },
    ],
}

_COMPOSITE_ONLY_CASE = (
    "Company Alpha exceeded more than one threshold during two consecutive financial years. "
    "The second year is financial year 2025."
)

_NUMERIC_CASE = (
    "Company Sigma has legal personality. On balance sheet date it has 11 full-time equivalents, "
    "annual net turnover of 1000000 euro excluding VAT and balance sheet total of 420000 euro."
)


def test_rejected_helper_lists_matching_numeric_observables():
    suggestions = suggest_observable_replacements(
        "exceeds_more_than_one_criterion",
        _THRESHOLD_KB,
        rejection_code="derived_or_helper",
        case_text=_NUMERIC_CASE,
    )
    names = [s["name"] for s in suggestions]
    assert "annual_average_number_of_employees" in names
    assert "annual_net_turnover_excluding_vat" in names
    assert any(s.get("symbol_type") == "function" for s in suggestions)


def test_decomposition_hint_prioritizes_semantic_overlap():
    diag = build_rejection_diagnostics(
        "exceeds_more_than_one_criterion",
        "derived_or_helper",
        _THRESHOLD_KB,
        case_text=_NUMERIC_CASE,
    )
    assert diag.suggested_observable_replacements
    top = diag.suggested_observable_replacements[0]
    assert top["symbol_type"] == "function"
    assert diag.decomposition_required is True


def test_empty_facts_after_rejection_with_numeric_case_triggers_retry():
    diag = build_rejection_diagnostics(
        "exceeds_more_than_one_criterion",
        "derived_or_helper",
        _THRESHOLD_KB,
        case_text=_NUMERIC_CASE,
    )
    empty_case = {"facts": [], "entities": {"Company": ["sigma"], "FinancialYear": ["fy2025"]}}
    with pytest.raises(CaseFactAssertionRejected, match="added no observable"):
        validate_decomposition_repair_or_raise(empty_case, diag)
    assert diag.empty_facts_after_repair is True


def test_numeric_observable_repair_passes_decomposition_check():
    diag = build_rejection_diagnostics(
        "exceeds_more_than_one_criterion",
        "derived_or_helper",
        _THRESHOLD_KB,
        case_text=_NUMERIC_CASE,
    )
    repaired = {
        "facts": [
            "annual_average_number_of_employees(sigma,fy2025) = 11.",
            "annual_net_turnover_excluding_vat(sigma,fy2025) = 1000000.",
        ],
        "entities": {"Company": ["sigma"], "FinancialYear": ["fy2025"]},
    }
    validate_decomposition_repair_or_raise(repaired, diag)
    assert case_object_has_non_entity_facts(repaired)


def test_entities_only_allowed_when_no_decomposition_required():
    diag = build_rejection_diagnostics(
        "exceeds_more_than_one_criterion",
        "derived_or_helper",
        _THRESHOLD_KB,
        case_text=_COMPOSITE_ONLY_CASE,
    )
    assert decomposition_required_from_case_text(_COMPOSITE_ONLY_CASE, diag.suggested_observable_replacements) is False
    empty_case = {"facts": [], "entities": {"Company": ["alpha"], "FinancialYear": ["fy2025"]}}
    validate_decomposition_repair_or_raise(empty_case, diag)


def test_article_reference_numbers_do_not_force_decomposition():
    from pipeline.extraction.case_fact_validation import case_text_has_numeric_values

    assert case_text_has_numeric_values(
        "BV Horizon exceeded thresholds from article 1:24, paragraph 1 during two consecutive financial years. "
        "The second year is financial year 2025."
    ) is False


def test_legal_output_still_rejected():
    from pipeline.extraction.json_ir import normalize_case_ir

    with pytest.raises(CaseFactAssertionRejected, match="legal-output"):
        normalize_case_ir(
            {
                "entities": {"Company": ["acme"], "FinancialYear": ["fy2025"]},
                "assertions": [{"symbol": "legal_consequences_apply", "args": ["acme", "fy2025"]}],
            },
            _THRESHOLD_KB,
        )


def test_run_case_loop_retries_on_empty_decomposition(monkeypatch):
    calls = {"n": 0}

    def fake_extract(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "entities": {"Company": ["sigma"], "FinancialYear": ["fy2025"]},
                "assertions": [
                    {"symbol": "exceeds_more_than_one_criterion", "args": ["sigma", "fy2025"]},
                ],
            }
        return {
            "entities": {"Company": ["sigma"], "FinancialYear": ["fy2025"]},
            "value_assertions": [
                {
                    "symbol": "annual_average_number_of_employees",
                    "args": ["sigma", "fy2025"],
                    "value": 11,
                },
            ],
        }

    monkeypatch.setattr(
        "pipeline.extraction.extractor.extract_case_ir_only_openai",
        fake_extract,
    )
    monkeypatch.setattr(
        "pipeline.extraction.extractor.normalize_and_validate_case",
        lambda case_obj, kb_schema=None: case_obj,
    )
    monkeypatch.setattr(
        "pipeline.extraction.case_entity_seed.seed_person_entities_from_case_text",
        lambda *args, **kwargs: None,
    )

    case = _run_case_extraction_loop(
        _NUMERIC_CASE,
        kb_schema=_THRESHOLD_KB,
        provider="openai",
        model="test",
        max_retries=4,
        use_json_ir=True,
    )
    assert calls["n"] >= 2
    assert case_object_has_non_entity_facts(case)
