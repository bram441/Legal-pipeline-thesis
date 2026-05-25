"""Tests for threshold exclusion scaffold and predicate/function misuse (Tasks B–D)."""

from __future__ import annotations

import unittest

from pipeline.kb.json_ir_repair import normalize_error_code
from pipeline.kb.predicate_function_repair_hints import (
    build_predicate_function_misuse_supplement,
    extract_misused_function_name,
)
from pipeline.kb.threshold_exclusion_scaffold import (
    build_threshold_exclusion_gap_report,
    build_threshold_exclusion_repair_scaffold,
)
from pipeline.kb.helper_repair_progress import (
    build_helper_repair_snapshot,
    detect_helper_definition_progress,
)


def _mini_symbol_table() -> dict:
    return {
        "types": ["Company", "FinancialYear"],
        "predicates": [
            {"name": "small_company", "args": ["Company", "FinancialYear"], "returns": "Bool", "kind": "derived"},
            {
                "name": "employee_criterion_exceeded_small",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "helper",
            },
            {
                "name": "turnover_criterion_exceeded_small",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "helper",
            },
            {
                "name": "balance_sheet_criterion_exceeded_small",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "helper",
            },
            {
                "name": "more_than_one_small_criterion_exceeded",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "helper",
            },
        ],
        "functions": [
            {
                "name": "annual_average_employees_fte",
                "args": ["Company", "FinancialYear"],
                "returns": "Real",
                "kind": "observable",
            },
        ],
    }


class TestThresholdExclusionScaffold(unittest.TestCase):
    def test_scaffold_mentions_pairwise_and_exclusion(self):
        text = build_threshold_exclusion_repair_scaffold(
            _mini_symbol_table(),
            merged_ir={"rules": []},
            query_predicate="small_company",
            law_text="not more than one criterion is exceeded. Threshold 50 employees.",
        )
        self.assertIn("small_company", text)
        self.assertIn("pairwise", text.lower())
        self.assertIn("negated", text.lower())
        self.assertIn("employee_criterion_exceeded_small", text)

    def test_gap_detects_missing_exclusion(self):
        ir = {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}, {"var": "y", "type": "FinancialYear"}],
                    "if": [
                        {"pred": "has_legal_personality", "args": ["c"]},
                        {"not": {"pred": "more_than_one_small_criterion_exceeded", "args": ["c", "y"]}},
                    ],
                    "then": [{"pred": "small_company", "args": ["c", "y"]}],
                    "operator": "implies",
                }
            ],
            "predicates": _mini_symbol_table()["predicates"],
        }
        gap = build_threshold_exclusion_gap_report(
            ir,
            _mini_symbol_table(),
            query_predicate="small_company",
            law_text="not more than one criterion is exceeded",
        )
        self.assertTrue(gap["positive_rule_present"])
        self.assertFalse(gap["negative_rule_usable"])


class TestPredicateFunctionMisuse(unittest.TestCase):
    def test_normalize_function_used_as_predicate(self):
        msg = (
            "JSON_IR_SCHEMA_DESIGN_ERROR: Rules use 'annual_average_employees_fte' as a Bool "
            "predicate atom, but the symbol table lists it only under functions."
        )
        self.assertEqual(normalize_error_code(msg), "function_used_as_predicate")

    def test_normalize_predicate_used_as_function(self):
        msg = (
            "JSON_IR_SCHEMA_DESIGN_ERROR: rules[2] uses predicate 'small_company' as a function term. "
            "Predicates are Boolean atoms."
        )
        self.assertEqual(normalize_error_code(msg), "predicate_used_as_function")

    def test_repair_hint_mentions_negated_then(self):
        msg = (
            "Rules use 'annual_average_employees_fte' as a Bool predicate atom, "
            "but the symbol table lists it only under functions."
        )
        self.assertEqual(extract_misused_function_name(msg), "annual_average_employees_fte")
        hint = build_predicate_function_misuse_supplement(msg)
        self.assertIn("negated", hint.lower())
        self.assertIn("false", hint.lower())


class TestHelperProgressWithScaffold(unittest.TestCase):
    def test_no_progress_without_then(self):
        ir = {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}],
                    "if": [{"pred": "more_than_one_small_criterion_exceeded", "args": ["c", "y"]}],
                    "then": [{"pred": "small_company", "args": ["c", "y"]}],
                }
            ]
        }
        snap = build_helper_repair_snapshot(ir, helper_name="more_than_one_small_criterion_exceeded")
        verdict = detect_helper_definition_progress(snap, snap)
        self.assertFalse(verdict.progress_detected)

    def test_progress_when_helper_in_then(self):
        ir_before = {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}],
                    "if": [{"pred": "more_than_one_small_criterion_exceeded", "args": ["c", "y"]}],
                    "then": [{"pred": "small_company", "args": ["c", "y"]}],
                }
            ]
        }
        ir_after = {
            "rules": ir_before["rules"]
            + [
                {
                    "forall": [{"var": "c", "type": "Company"}, {"var": "y", "type": "FinancialYear"}],
                    "if": [
                        {
                            "and": [
                                {"pred": "employee_criterion_exceeded_small", "args": ["c", "y"]},
                                {"pred": "turnover_criterion_exceeded_small", "args": ["c", "y"]},
                            ]
                        }
                    ],
                    "then": [{"pred": "more_than_one_small_criterion_exceeded", "args": ["c", "y"]}],
                }
            ]
        }
        prev = build_helper_repair_snapshot(ir_before, helper_name="more_than_one_small_criterion_exceeded")
        cur = build_helper_repair_snapshot(ir_after, helper_name="more_than_one_small_criterion_exceeded")
        self.assertTrue(detect_helper_definition_progress(prev, cur).progress_detected)


if __name__ == "__main__":
    unittest.main()
