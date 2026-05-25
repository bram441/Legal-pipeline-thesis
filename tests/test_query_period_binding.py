"""Temporal query period argument binding and diagnostics."""

from __future__ import annotations

from pipeline.extraction.json_ir import normalize_query_ir
from pipeline.extraction.query_period_binding import (
    analyze_query_period_binding,
    apply_query_period_binding,
    infer_query_period_role,
)
from pipeline.diagnostics.symbolic_proof_gap import build_symbolic_proof_gap_report


def _effect_schema(*, pred_name: str = "consequences_apply_from_financial_year", desc: str | None = None):
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {
                "name": "next_financial_year",
                "kind": "observable",
                "args": ["FinancialYear", "FinancialYear"],
                "returns": "Bool",
            },
            {
                "name": pred_name,
                "kind": "derived",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "legal_output": True,
                "description": desc or "Legal consequences apply from the given financial year.",
            },
            {
                "name": "exceeded_two_consecutive_years",
                "kind": "helper",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "description": "Second year of exceedance during two consecutive financial years.",
            },
            {
                "name": "ambiguous_legal_effect",
                "kind": "derived",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "legal_output": True,
                "description": "Some legal effect holds for the company.",
            },
        ],
        "functions": [],
        "rules": [],
    }


def _case_with_chain():
    return {
        "entities": {
            "Company": ["acme"],
            "FinancialYear": ["fy_2024", "fy_2025", "fy_2026"],
        },
        "facts": [
            "next_financial_year(fy_2025,fy_2026).",
            "next_financial_year(fy_2024,fy_2025).",
        ],
    }


def test_infer_effect_year_from_from_financial_year_wording():
    sig = _effect_schema()["predicates"][1]
    assert infer_query_period_role(sig) == "effect_year"


def test_infer_second_exceedance_year_from_description():
    sig = _effect_schema()["predicates"][2]
    assert infer_query_period_role(sig) == "second_exceedance_year"


def test_following_2025_selects_successor_for_effect_year_predicate():
    schema = _effect_schema()
    case = _case_with_chain()
    question = "Do consequences apply from the financial year following 2025?"
    query_obj = {
        "type": "predicate",
        "predicate": "consequences_apply_from_financial_year",
        "mode": "boolean",
        "args": ["acme", "fy_2025"],
    }
    diag = apply_query_period_binding(query_obj, case, schema, question)
    assert query_obj["args"][1] == "fy_2026"
    assert diag.get("auto_adjusted_to_successor") is True
    assert diag.get("query_period_role") == "effect_year"
    assert diag.get("matches_question_wording") is True


def test_following_2025_does_not_keep_predecessor_fy_2024():
    schema = _effect_schema()
    case = _case_with_chain()
    question = "Do consequences apply from the financial year following 2025?"
    query_obj = {
        "type": "predicate",
        "predicate": "consequences_apply_from_financial_year",
        "mode": "boolean",
        "args": ["acme", "fy_2024"],
    }
    diag = analyze_query_period_binding(
        query=query_obj,
        case=case,
        kb_schema=schema,
        user_question=question,
        predicate_sig=schema["predicates"][1],
    )
    assert diag["matches_question_wording"] is False
    assert any("predecessor" in w.lower() for w in diag["query_argument_binding_warnings"])


def test_second_exceedance_predicate_may_use_anchor_year():
    schema = _effect_schema()
    case = _case_with_chain()
    question = "Was the second year of exceedance during two consecutive years ending with 2025?"
    query_obj = {
        "type": "predicate",
        "predicate": "exceeded_two_consecutive_years",
        "mode": "boolean",
        "args": ["acme", "fy_2025"],
    }
    diag = analyze_query_period_binding(
        query=query_obj,
        case=case,
        kb_schema=schema,
        user_question=question,
        predicate_sig=schema["predicates"][2],
    )
    assert diag["query_period_role"] == "second_exceedance_year"
    assert diag["selected_query_period"] == "fy_2025"


def test_ambiguous_predicate_emits_binding_warning():
    schema = _effect_schema()
    case = _case_with_chain()
    question = "Do consequences apply from the financial year following 2025?"
    query_obj = {
        "type": "predicate",
        "predicate": "ambiguous_legal_effect",
        "mode": "boolean",
        "args": ["acme", "fy_2025"],
    }
    diag = analyze_query_period_binding(
        query=query_obj,
        case=case,
        kb_schema=schema,
        user_question=question,
        predicate_sig=schema["predicates"][3],
    )
    assert diag["query_period_role"] == "unknown"
    assert diag["query_argument_binding_warnings"]


def test_normalize_query_ir_auto_adjusts_effect_year_period():
    schema = _effect_schema(
        pred_name="consequences_apply_due_to_criteria_change",
        desc="Legal consequences apply from the following financial year.",
    )
    case = _case_with_chain()
    question = "Do the legal consequences apply from the financial year following 2025?"
    query = normalize_query_ir(
        {
            "kind": "predicate",
            "predicate_hint": "consequences_apply_due_to_criteria_change",
            "mode": "boolean",
            "args": ["acme", "fy_2025"],
        },
        case,
        schema,
        question,
    )
    binding = query.get("query_period_binding") or {}
    assert query["args"][1] == "fy_2026"
    assert binding.get("query_period_role") == "effect_year"


def test_proof_gap_includes_query_period_binding_diagnostics():
    schema = _effect_schema()
    case = _case_with_chain()
    query = {
        "type": "predicate",
        "predicate": "consequences_apply_from_financial_year",
        "mode": "boolean",
        "args": ["acme", "fy_2025"],
    }
    report = build_symbolic_proof_gap_report(
        case=case,
        query=query,
        kb_schema=schema,
        user_question="Do consequences apply from the financial year following 2025?",
    )
    assert report.get("temporal_query_issues")
    assert report["temporal_query_issues"][0].get("query_period_binding")
