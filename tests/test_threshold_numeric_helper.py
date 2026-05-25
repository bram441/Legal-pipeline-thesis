"""Tests for numeric threshold helper scaffold and function helper progress (Task F)."""

from __future__ import annotations

import json
import unittest

from pipeline.kb.helper_repair_progress import (
    build_helper_repair_snapshot,
    detect_helper_definition_progress,
)
from pipeline.kb.json_ir_repair import (
    JsonIRErrorKind,
    classify_json_ir_validation_error,
    normalize_error_code,
)
from pipeline.kb.threshold_exclusion_scaffold import build_threshold_exclusion_repair_scaffold
from pipeline.kb.threshold_numeric_helper_scaffold import (
    build_numeric_threshold_helper_scaffold,
    build_threshold_numeric_helper_gap_report,
    looks_like_case_value_function,
    suggest_law_literals_for_function,
)


LAW_TEXT = """
Article 3. A small company shall not exceed more than one of the following criteria:
employees 50, net turnover 11250000 euros, balance sheet total 4500000 euros.
A micro company uses employees 10, turnover 900000 euros, balance sheet 450000 euros.
"""


def _symbol_table_with_threshold_fn() -> dict:
    return {
        "types": [{"name": "Company"}, {"name": "FinancialYear"}],
        "predicates": [
            {
                "name": "small_company",
                "args": ["Company", "FinancialYear"],
                "returns": "Bool",
                "kind": "derived",
            }
        ],
        "functions": [
            {
                "name": "annual_average_employees_fte",
                "args": ["Company", "FinancialYear"],
                "returns": "Real",
                "kind": "observable",
            },
            {
                "name": "adjusted_small_employee_threshold",
                "args": ["Company", "FinancialYear"],
                "returns": "Real",
                "kind": "helper",
                "description": "Adjusted employee threshold for small company classification",
            },
        ],
    }


class TestThresholdNumericHelper(unittest.TestCase):
    def test_missing_real_threshold_helper_scaffold_uses_then_compare(self):
        st = _symbol_table_with_threshold_fn()
        text = build_numeric_threshold_helper_scaffold(
            st,
            helper_name="adjusted_small_employee_threshold",
            law_text=LAW_TEXT,
        )
        self.assertIn("compare", text)
        self.assertIn('"op": "="', text)
        self.assertIn("adjusted_small_employee_threshold", text)
        self.assertIn("50", text)

    def test_scaffold_uses_only_law_text_literals(self):
        likely, candidates, ambiguous = suggest_law_literals_for_function(
            "adjusted_small_employee_threshold",
            "Adjusted employee threshold for small company",
            law_text=LAW_TEXT,
        )
        self.assertFalse(ambiguous)
        self.assertEqual(likely, [50.0])
        self.assertTrue(all(v in candidates for v in likely))

    def test_case_value_applicable_employees_not_threshold(self):
        self.assertTrue(
            looks_like_case_value_function("applicable_annual_average_employees_micro")
        )
        text = build_numeric_threshold_helper_scaffold(
            _symbol_table_with_threshold_fn(),
            helper_name="applicable_annual_average_employees_micro",
            law_text=LAW_TEXT,
        )
        self.assertIn("case metric", text.lower())
        self.assertNotIn("Use this literal", text)

    def test_annual_average_observable_not_from_law_threshold(self):
        self.assertTrue(looks_like_case_value_function("annual_average_employees_fte"))
        text = build_numeric_threshold_helper_scaffold(
            _symbol_table_with_threshold_fn(),
            helper_name="annual_average_employees_fte",
            law_text=LAW_TEXT,
        )
        self.assertIn("case metric", text.lower())
        self.assertNotIn("Use this literal", text)

    def test_function_used_as_predicate_normalizes(self):
        msg = (
            "Schema design: Rules use 'annual_average_employees_fte' as a Bool predicate atom, "
            "but the symbol table lists it only under functions. Repair layer: rules."
        )
        self.assertEqual(normalize_error_code(msg), "function_used_as_predicate")
        self.assertEqual(
            classify_json_ir_validation_error(msg),
            JsonIRErrorKind.RULES_REPAIR_ONLY,
        )

    def test_predicate_used_as_function_normalizes(self):
        msg = (
            "Schema design: rules[2] uses predicate 'small_company' as a function term. "
            "Predicates are Boolean atoms used as P(args) or negated P(args) in IF/THEN."
        )
        self.assertEqual(normalize_error_code(msg), "predicate_used_as_function")
        self.assertEqual(
            classify_json_ir_validation_error(msg),
            JsonIRErrorKind.RULES_REPAIR_ONLY,
        )

    def test_progress_detects_function_equality_in_then(self):
        ir_before = {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
                    "if": [
                        {
                            "compare": {
                                "left": {"func": "annual_average_employees_fte", "args": ["c", "fy"]},
                                "op": "<=",
                                "right": {"func": "adjusted_small_employee_threshold", "args": ["c", "fy"]},
                            }
                        }
                    ],
                    "then": [{"pred": "small_company", "args": ["c", "fy"]}],
                    "operator": "implies",
                }
            ]
        }
        ir_after = {
            "rules": ir_before["rules"]
            + [
                {
                    "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
                    "if": [],
                    "then": [
                        {
                            "compare": {
                                "left": {"func": "adjusted_small_employee_threshold", "args": ["c", "fy"]},
                                "op": "=",
                                "right": 50,
                            }
                        }
                    ],
                    "operator": "implies",
                }
            ]
        }
        fun_kinds = {"adjusted_small_employee_threshold": "helper"}
        prev = build_helper_repair_snapshot(
            ir_before,
            helper_name="adjusted_small_employee_threshold",
            helper_kind="function",
            fun_kinds=fun_kinds,
        )
        cur = build_helper_repair_snapshot(
            ir_after,
            helper_name="adjusted_small_employee_threshold",
            helper_kind="function",
            fun_kinds=fun_kinds,
        )
        self.assertFalse(prev.defined_in_then)
        self.assertTrue(cur.defined_in_then)
        verdict = detect_helper_definition_progress(prev, cur)
        self.assertTrue(verdict.progress_detected)
        self.assertEqual(verdict.progress_reason, "helper_function_equality_in_then")

    def test_progress_rejects_if_only_reuse(self):
        ir = {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
                    "if": [
                        {
                            "compare": {
                                "left": {"func": "annual_average_employees_fte", "args": ["c", "fy"]},
                                "op": "<=",
                                "right": {"func": "adjusted_small_employee_threshold", "args": ["c", "fy"]},
                            }
                        }
                    ],
                    "then": [{"pred": "small_company", "args": ["c", "fy"]}],
                    "operator": "implies",
                }
            ]
        }
        snap = build_helper_repair_snapshot(
            ir,
            helper_name="adjusted_small_employee_threshold",
            helper_kind="function",
            fun_kinds={"adjusted_small_employee_threshold": "helper"},
        )
        verdict = detect_helper_definition_progress(snap, snap)
        self.assertFalse(verdict.progress_detected)

    def test_boolean_threshold_exclusion_scaffold_still_works(self):
        st = {
            "predicates": [
                {"name": "small_company", "args": ["Company", "FinancialYear"], "kind": "derived"},
                {"name": "more_than_one_criterion_exceeded", "args": ["Company", "FinancialYear"], "kind": "helper"},
                {"name": "employees_exceeded", "args": ["Company", "FinancialYear"], "kind": "helper"},
            ],
            "functions": [],
        }
        text = build_threshold_exclusion_repair_scaffold(
            st,
            missing_helper_name="more_than_one_criterion_exceeded",
            query_predicate="small_company",
        )
        self.assertIn("pairwise", text.lower())
        self.assertIn("negated", text.lower())

    def test_run_009_style_decisive_false_exclusion_gap(self):
        st = {
            "predicates": [
                {"name": "small_company", "args": ["Company", "FinancialYear"], "kind": "derived", "legal_output": True},
                {"name": "more_than_one_criterion_exceeded", "args": ["Company", "FinancialYear"], "kind": "helper"},
            ],
            "functions": [],
        }
        ir = {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
                    "if": [{"pred": "more_than_one_criterion_exceeded", "args": ["c", "fy"]}],
                    "then": [{"pred": "small_company", "args": ["c", "fy"], "negated": True}],
                    "operator": "implies",
                }
            ]
        }
        from pipeline.kb.threshold_exclusion_scaffold import build_threshold_exclusion_gap_report

        gap = build_threshold_exclusion_gap_report(ir, st, query_predicate="small_company", law_text=LAW_TEXT)
        self.assertTrue(gap.get("negative_rule_usable"))


if __name__ == "__main__":
    unittest.main()
