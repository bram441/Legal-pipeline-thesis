"""Tests for threshold classification exclusion grounding (Task D)."""

from __future__ import annotations

import unittest

from pipeline.kb.json_ir import JSONIRCompilationError
from pipeline.kb.threshold_classification_negative import (
    validate_threshold_classification_negative_support,
)


LAW_AT_MOST_ONE = (
    "A company is a small company when it has legal personality and "
    "not more than one of the following criteria is exceeded: employees above 50, "
    "turnover above 900000, balance sheet above 450000."
)


def _run009_style_kb(*, with_exclusion: bool) -> tuple[dict, dict[str, str]]:
    rules = [
        {
            "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
            "if": [
                {"pred": "has_legal_personality", "args": ["c"]},
                {"not": {"pred": "more_than_one_small_criterion_exceeded", "args": ["c", "fy"]}},
            ],
            "then": [{"pred": "small_company", "args": ["c"]}],
            "operator": "implies",
        },
        {
            "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
            "if": [
                {
                    "or": [
                        {
                            "and": [
                                {"pred": "employees_exceeded", "args": ["c", "fy"]},
                                {"pred": "turnover_exceeded", "args": ["c", "fy"]},
                            ]
                        },
                        {
                            "and": [
                                {"pred": "employees_exceeded", "args": ["c", "fy"]},
                                {"pred": "balance_sheet_exceeded", "args": ["c", "fy"]},
                            ]
                        },
                        {
                            "and": [
                                {"pred": "turnover_exceeded", "args": ["c", "fy"]},
                                {"pred": "balance_sheet_exceeded", "args": ["c", "fy"]},
                            ]
                        },
                    ]
                }
            ],
            "then": [{"pred": "more_than_one_small_criterion_exceeded", "args": ["c", "fy"]}],
            "operator": "implies",
        },
    ]
    if with_exclusion:
        rules.append(
            {
                "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
                "if": [{"pred": "more_than_one_small_criterion_exceeded", "args": ["c", "fy"]}],
                "then": [{"pred": "small_company", "args": ["c"], "negated": True}],
                "operator": "implies",
            }
        )
    ir = {"rules": rules}
    pred_kinds = {
        "has_legal_personality": "observable",
        "employees_exceeded": "helper",
        "turnover_exceeded": "helper",
        "balance_sheet_exceeded": "helper",
        "more_than_one_small_criterion_exceeded": "helper",
        "small_company": "derived",
    }
    return ir, pred_kinds


class TestThresholdClassificationNegative(unittest.TestCase):
    def test_qualification_only_fails_validation(self):
        ir, pred_kinds = _run009_style_kb(with_exclusion=False)
        with self.assertRaises(JSONIRCompilationError) as ctx:
            validate_threshold_classification_negative_support(
                ir, pred_kinds, law_text_for_lints=LAW_AT_MOST_ONE
            )
        self.assertIn("cannot prove disqualification", str(ctx.exception).lower())

    def test_exclusion_rule_passes_validation(self):
        ir, pred_kinds = _run009_style_kb(with_exclusion=True)
        validate_threshold_classification_negative_support(
            ir, pred_kinds, law_text_for_lints=LAW_AT_MOST_ONE
        )

    def test_negated_helper_in_qualification_if_not_counted_as_exclusion(self):
        ir, pred_kinds = _run009_style_kb(with_exclusion=False)
        with self.assertRaises(JSONIRCompilationError):
            validate_threshold_classification_negative_support(
                ir, pred_kinds, law_text_for_lints=LAW_AT_MOST_ONE
            )


if __name__ == "__main__":
    unittest.main()
