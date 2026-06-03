"""Threshold repair progress, evidence collection, and stall logic."""

from __future__ import annotations

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir
from pipeline.kb.json_ir_repair import normalize_error_code
from pipeline.kb.repair_cards import format_repair_card
from pipeline.kb.threshold_repair_progress import (
    ThresholdRepairSnapshot,
    build_threshold_repair_snapshot,
    detect_threshold_cardinality_progress,
    rules_fingerprint,
    should_stall_threshold_cardinality_repeat,
)
from pipeline.kb.exclusion_repair_hints import (
    build_missing_exclusion_repair_supplement,
    extract_classification_predicates,
)
from pipeline.kb.json_ir_compile_loop import _build_repair_hints
from pipeline.kb.json_ir_repair import normalize_error_code
from pipeline.kb.repair_cards import get_repair_card
from pipeline.kb.validation_evidence import collect_validation_repair_evidence

LAW_AT_MOST_ONE = (
    "Article 1:24. A company is a small company if not more than one of the following criteria is exceeded: "
    "employees 50, turnover 11,250,000 euros, balance sheet 6,000,000 euros."
)

LAW_MICRO = (
    "Article 1:25. A micro-company if not more than one criterion is exceeded: "
    "employees 10, turnover 900,000 euros, total assets 450,000 euros."
)


def _cmp(func: str, op: str, right: int | float) -> dict:
    return {
        "compare": {
            "left": {"func": func, "args": ["c", "fy"]},
            "op": op,
            "right": right,
        }
    }


def _base_symbols():
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {
                "name": "is_classification",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
            }
        ],
        "functions": [
            {
                "name": "metric_a",
                "args": ["Company", "FinancialYear"],
                "returns": "Int",
                "kind": "observable",
            },
            {
                "name": "metric_b",
                "args": ["Company", "FinancialYear"],
                "returns": "Real",
                "kind": "observable",
            },
            {
                "name": "metric_c",
                "args": ["Company", "FinancialYear"],
                "returns": "Real",
                "kind": "observable",
            },
        ],
    }


def _pred_kinds():
    return {
        "is_classification": "derived",
        "metric_a": "observable",
        "metric_b": "observable",
        "metric_c": "observable",
    }


EXCLUSION_ERROR = (
    "JSON_IR_RULE_DESIGN_ERROR: This law defines a classification by threshold criteria "
    "(not more than one criterion exceeded). The rule set can prove favorable cases but cannot prove "
    "disqualification. To answer false cases, add an exclusion rule such as "
    "at_least_two_exceeded => not is_micro_company (negated predicate in THEN). "
    "Do not rely on absence of proof for a negative legal answer. "
    "Affected classification predicate(s): is_micro_company. Repair layer: rules."
)


# --- Exclusion repair card / prompt tests ---


def test_exclusion_error_selects_specific_repair_card():
    code = normalize_error_code(EXCLUSION_ERROR)
    assert code == "missing_threshold_classification_exclusion"
    card = get_repair_card(code)
    assert card.card_id == "missing_threshold_classification_exclusion"


def test_exclusion_card_contains_pairwise_negative_pattern():
    card_text = format_repair_card("missing_threshold_classification_exclusion")
    assert "((A AND B) OR (A AND C) OR (B AND C)) => NOT classification" in card_text
    assert "A OR B OR C => NOT classification" in card_text
    assert "positive qualification rules" in card_text.lower()


def test_exclusion_repair_prompt_includes_pred_thresholds_and_secondary():
    secondary = (
        "numeric_threshold_not_in_law_text:\n"
        "  - Rule rules[0] uses numeric threshold 1900000, not in scoped law text.\n"
        "  Allowed law-text thresholds: 10, 900000, 450000"
    )
    supplement = build_missing_exclusion_repair_supplement(
        EXCLUSION_ERROR,
        law_text=LAW_MICRO,
        secondary_diagnostics=secondary,
    )
    assert extract_classification_predicates(EXCLUSION_ERROR) == ["is_micro_company"]
    assert "is_micro_company" in supplement
    assert "900000" in supplement or "900,000" in supplement
    assert "disqualify" in supplement.lower() or "exclusion" in supplement.lower()
    assert "exclusion" in supplement.lower() or "pairwise" in supplement.lower()
    assert "1900000" in supplement

    hints = _build_repair_hints(
        EXCLUSION_ERROR,
        '{"rules":[]}',
        error_code="missing_threshold_classification_exclusion",
        layer="rules",
        secondary_diagnostics=secondary,
        law_text=LAW_MICRO,
    )
    assert "MISSING EXCLUSION RULE" in hints
    assert "is_micro_company" in hints
    assert "1900000" in hints


# --- Test A / B: stall logic ---


def test_a_progress_allows_another_attempt_despite_same_signature():
    prev = ThresholdRepairSnapshot(
        cardinality_violation_count=2,
        cardinality_paths=["rules[1].if[1].and[1]"],
        has_correct_pairwise_positive=False,
        rules_fingerprint="aaa",
    )
    cur = ThresholdRepairSnapshot(
        cardinality_violation_count=1,
        cardinality_paths=["rules[1].if[1]"],
        has_correct_pairwise_positive=True,
        rules_fingerprint="bbb",
    )
    verdict = detect_threshold_cardinality_progress(prev, cur)
    assert verdict.progress_detected
    assert not should_stall_threshold_cardinality_repeat(
        signature_repeat_count=2,
        repeated_error_limit=2,
        progress=verdict,
        rules_attempt=2,
        max_rules_attempts=3,
    )


def test_b_identical_rules_stalls_at_repeated_limit():
    fp = rules_fingerprint([{"forall": [], "if": [], "then": []}])
    prev = ThresholdRepairSnapshot(
        cardinality_violation_count=1,
        cardinality_paths=["rules[1].if[1]"],
        rules_fingerprint=fp,
    )
    cur = ThresholdRepairSnapshot(
        cardinality_violation_count=1,
        cardinality_paths=["rules[1].if[1]"],
        rules_fingerprint=fp,
    )
    verdict = detect_threshold_cardinality_progress(prev, cur)
    assert not verdict.progress_detected
    assert verdict.progress_reason == "identical_rules_output"
    assert should_stall_threshold_cardinality_repeat(
        signature_repeat_count=2,
        repeated_error_limit=2,
        progress=verdict,
        rules_attempt=2,
        max_rules_attempts=3,
    )


# --- Test C: repair card exclusion pattern ---


def test_c_repair_card_contains_explicit_exclusion_pattern():
    card = format_repair_card("threshold_cardinality_or_singleton")
    assert "((A AND B) OR (A AND C) OR (B AND C)) => NOT classification" in card
    assert "negated THEN" in card
    assert "A OR B OR C => NOT classification" in card


# --- Test D: dual diagnostics ---


def test_d_cardinality_primary_with_secondary_numeric_provenance():
    ir = {
        **_base_symbols(),
        "rules": [
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [
                    {
                        "or": [
                            _cmp("metric_a", ">", 50),
                            _cmp("metric_b", ">", 1900000),
                            _cmp("metric_c", ">", 1450000),
                        ]
                    }
                ],
                "then": [{"pred": "is_classification", "args": ["c", "fy"]}],
                "operator": "implies",
            }
        ],
    }
    evidence = collect_validation_repair_evidence(
        ir, _pred_kinds(), law_text_for_lints=LAW_MICRO
    )
    assert len(evidence.cardinality_violations) >= 1
    assert len(evidence.numeric_provenance_issues) >= 2
    sec = evidence.format_secondary_diagnostics()
    assert "numeric_threshold_not_in_law_text" in sec
    assert "1900000" in sec
    assert "1450000" in sec
    assert "900000" in sec or "450000" in sec

    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir, law_text_for_lints=LAW_MICRO)
    assert normalize_error_code(str(exc.value)) == "threshold_cardinality_or_singleton"


# --- Test E: run_009-style ---


def test_e_run009_style_positive_ok_exclusion_simple_or_fails():
    ir = {
        **_base_symbols(),
        "rules": [
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [
                    {
                        "not": {
                            "or": [
                                {
                                    "and": [
                                        _cmp("metric_a", ">", 50),
                                        _cmp("metric_b", ">", 11250000),
                                    ]
                                },
                                {
                                    "and": [
                                        _cmp("metric_a", ">", 50),
                                        _cmp("metric_c", ">", 6000000),
                                    ]
                                },
                                {
                                    "and": [
                                        _cmp("metric_b", ">", 11250000),
                                        _cmp("metric_c", ">", 6000000),
                                    ]
                                },
                            ]
                        }
                    }
                ],
                "then": [{"pred": "is_classification", "args": ["c", "fy"]}],
                "operator": "implies",
            },
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [
                    {
                        "or": [
                            _cmp("metric_a", ">", 50),
                            _cmp("metric_b", ">", 11250000),
                            _cmp("metric_c", ">", 6000000),
                        ]
                    }
                ],
                "then": [
                    {"pred": "is_classification", "args": ["c", "fy"], "negated": True}
                ],
                "operator": "implies",
            },
        ],
    }
    evidence = collect_validation_repair_evidence(
        ir, _pred_kinds(), law_text_for_lints=LAW_AT_MOST_ONE
    )
    snap = build_threshold_repair_snapshot(
        ir,
        _pred_kinds(),
        cardinality_violations=evidence.cardinality_violations,
        numeric_provenance_count=len(evidence.numeric_provenance_issues),
    )
    assert snap.has_correct_pairwise_positive
    assert snap.has_exclusion_negated_then
    assert snap.has_malformed_exclusion_simple_or
    assert len(evidence.cardinality_violations) == 1

    card = format_repair_card("threshold_cardinality_or_singleton")
    assert "pairwise exceeded" in card.lower() or "A AND B" in card
    assert "negated THEN" in card

    with pytest.raises(JSONIRCompilationError):
        compile_validate_json_ir(ir, law_text_for_lints=LAW_AT_MOST_ONE)


# --- Test F: run_117-style ---


def test_f_run117_style_within_or_and_invented_thresholds_in_evidence():
    ir = {
        **_base_symbols(),
        "predicates": [
            {
                "name": "is_micro_company",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
            }
        ],
        "rules": [
            {
                "forall": [
                    {"var": "c", "type": "Company"},
                    {"var": "fy", "type": "FinancialYear"},
                ],
                "if": [
                    {
                        "or": [
                            _cmp("metric_a", "<=", 10),
                            _cmp("metric_b", "<=", 1900000),
                            _cmp("metric_c", "<=", 1450000),
                        ]
                    }
                ],
                "then": [{"pred": "is_micro_company", "args": ["c", "fy"]}],
                "operator": "implies",
            }
        ],
    }
    pred_kinds = {
        "is_micro_company": "derived",
        "metric_a": "observable",
        "metric_b": "observable",
        "metric_c": "observable",
    }
    evidence = collect_validation_repair_evidence(
        ir, pred_kinds, law_text_for_lints=LAW_MICRO
    )
    assert evidence.cardinality_violations
    assert any(i["threshold"] == 1900000 for i in evidence.numeric_provenance_issues)
    assert any(i["threshold"] == 1450000 for i in evidence.numeric_provenance_issues)
    sec = evidence.format_secondary_diagnostics()
    assert "1900000" in sec and "900000" in sec
