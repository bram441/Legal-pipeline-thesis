"""Tests for helper closure repair progress (Task C)."""

from __future__ import annotations

import unittest

from pipeline.kb.helper_repair_progress import (
    HelperRepairSnapshot,
    build_helper_repair_snapshot,
    detect_helper_definition_progress,
)
from pipeline.kb.validation_evidence import MissingHelperEvidence, _helper_signature_from_symbol_table


class TestHelperRepairProgress(unittest.TestCase):
    def test_missing_helper_repair_hint_contains_signature(self):
        symbol_table = {
            "predicates": [
                {
                    "name": "exceeds_employee_threshold",
                    "args": ["Company", "FinancialYear"],
                    "returns": "Bool",
                    "kind": "helper",
                }
            ]
        }
        sig = _helper_signature_from_symbol_table("exceeds_employee_threshold", symbol_table)
        self.assertIn("Company", sig)
        self.assertIn("FinancialYear", sig)
        ev = MissingHelperEvidence(
            helper_name="exceeds_employee_threshold",
            helper_signature=sig,
            helper_kind_hint="threshold",
            helper_kind_hints=["threshold", "counting"],
        )
        text = ev.format_diagnostics()
        self.assertIn("exceeds_employee_threshold", text)
        self.assertIn("Company * FinancialYear", text)
        self.assertIn("pairwise", text.lower())

    def test_no_progress_when_rules_identical_without_then(self):
        ir = {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}],
                    "if": [{"pred": "missing_helper", "args": ["c"]}],
                    "then": [{"pred": "derived_out", "args": ["c"]}],
                    "operator": "implies",
                }
            ]
        }
        snap = build_helper_repair_snapshot(ir, helper_name="missing_helper")
        verdict = detect_helper_definition_progress(snap, snap)
        self.assertFalse(verdict.progress_detected)
        self.assertEqual(verdict.progress_reason, "no_helper_definition_progress")

    def test_progress_when_helper_added_to_then(self):
        ir_before = {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}],
                    "if": [{"pred": "missing_helper", "args": ["c"]}],
                    "then": [{"pred": "derived_out", "args": ["c"]}],
                    "operator": "implies",
                }
            ]
        }
        ir_after = {
            "rules": ir_before["rules"]
            + [
                {
                    "forall": [{"var": "c", "type": "Company"}],
                    "if": [{"pred": "raw_fact", "args": ["c"]}],
                    "then": [{"pred": "missing_helper", "args": ["c"]}],
                    "operator": "implies",
                }
            ]
        }
        prev = build_helper_repair_snapshot(ir_before, helper_name="missing_helper")
        cur = build_helper_repair_snapshot(ir_after, helper_name="missing_helper")
        verdict = detect_helper_definition_progress(prev, cur)
        self.assertTrue(verdict.progress_detected)
        self.assertEqual(verdict.progress_reason, "helper_now_defined_in_then")


if __name__ == "__main__":
    unittest.main()
