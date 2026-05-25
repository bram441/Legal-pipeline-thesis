"""Tests for pre-query satisfiability gating."""

import unittest
from unittest.mock import patch

from pipeline.semantic.intent_routing import INTENT_DEDUCTION, INTENT_SATISFIABLE, classify_symbolic_intent
from pipeline.symbolic.consistency_check import (
    run_pre_query_satisfiability_check,
    should_block_query_after_unsat,
)
from pipeline.symbolic.intent_execution import execute_routed_symbolic_query


class TestPreQuerySatisfiability(unittest.TestCase):
    def test_unsat_blocks_deduction(self):
        routing = classify_symbolic_intent(
            question_text="Does X apply?",
            expected={"mode": "boolean", "value": True},
            query={"type": "predicate", "predicate": "X", "mode": "boolean", "args": ["a"]},
        )
        sat_check = {
            "stage": "pre_query",
            "kb_case_satisfiable": False,
            "status": "unsat",
            "details": "unsat",
        }
        self.assertTrue(should_block_query_after_unsat(routing, sat_check))

    def test_unsat_allows_satisfiable_intent(self):
        routing = {"selected_intent": INTENT_SATISFIABLE}
        sat_check = {"kb_case_satisfiable": False, "status": "unsat"}
        self.assertFalse(should_block_query_after_unsat(routing, sat_check))

    @patch("pipeline.symbolic.intent_execution.run_query")
    @patch("pipeline.symbolic.intent_execution.run_pre_query_satisfiability_check")
    def test_execute_blocks_deduction_on_unsat(self, mock_sat, mock_run):
        mock_sat.return_value = {
            "stage": "pre_query",
            "kb_case_satisfiable": False,
            "status": "unsat",
            "details": "KB+case theory is unsatisfiable",
        }
        case = {"facts": ["p(a)."], "entities": {"Person": ["a"]}}
        query = {"type": "predicate", "predicate": "q", "mode": "boolean", "args": ["a"]}
        routing = classify_symbolic_intent(
            question_text="Does q hold?",
            expected={"mode": "boolean", "value": True},
            query=query,
        )
        sat, result, _ = execute_routed_symbolic_query(
            case,
            query,
            "theory T { p: Person -> Bool. q: Person -> Bool. }",
            user_question="Does q hold?",
            expected={"mode": "boolean", "value": True},
            kb_schema={
                "types": ["Person"],
                "predicates": [{"name": "q", "args": ["Person"], "returns": "Bool", "kind": "derived"}],
                "functions": [],
            },
        )
        mock_run.assert_not_called()
        self.assertFalse(sat)
        self.assertEqual(result.get("symbolic_status"), "inconsistent")

    @patch("idp_z3.tasks.satisfiable_check")
    def test_sat_check_ok(self, mock_check):
        mock_check.return_value = {"sat": True}
        out = run_pre_query_satisfiability_check(
            {"facts": ["p(a)."]},
            "theory T { p: Person -> Bool. }",
        )
        self.assertEqual(out["status"], "ok")
        self.assertTrue(out["kb_case_satisfiable"])


if __name__ == "__main__":
    unittest.main()
