"""Intent-aware scoring regression tests."""

import unittest

from pipeline.eval.scoring import score_question
from pipeline.symbolic.results import normalize_deduction


class TestIntentAwareScoring(unittest.TestCase):
    def test_boolean_deduction_unchanged_true(self):
        sym = normalize_deduction({"possible": True, "certain": True}, {"predicate": "p", "args": ["a"]})
        out = score_question({"mode": "boolean", "value": True}, sym)
        self.assertTrue(out["match"])
        self.assertTrue(out.get("decisive"))

    def test_boolean_deduction_unchanged_false(self):
        sym = normalize_deduction({"possible": False, "certain": False}, {"predicate": "p", "args": ["a"]})
        out = score_question({"mode": "boolean", "value": False}, sym)
        self.assertTrue(out["match"])

    def test_model_expansion_not_boolean_decisive(self):
        sym = {
            "intent": "model_expansion",
            "symbolic_status": "ok",
            "status": "ok",
            "model_expansion": {
                "possible_outputs": [{"symbol": "sanction", "args": []}],
                "model_count": 1,
            },
        }
        out = score_question({"mode": "boolean", "value": True}, sym)
        self.assertFalse(out["match"])
        self.assertTrue(out.get("inconclusive"))
        self.assertEqual(out.get("failure_category"), "unscored_intent")

    def test_inconsistent_not_scored_as_false(self):
        sym = {
            "intent": "deduction",
            "symbolic_status": "inconsistent",
            "status": "inconsistent",
            "message": "KB+case theory is unsatisfiable",
        }
        out = score_question({"mode": "boolean", "value": False}, sym)
        self.assertFalse(out["match"])
        self.assertEqual(out.get("failure_category"), "inconsistent_kb_case")
        self.assertTrue(out.get("inconclusive"))

    def test_unknown_boolean_inconclusive(self):
        sym = normalize_deduction({"possible": True, "certain": False}, {"predicate": "p", "args": ["a"]})
        out = score_question({"mode": "boolean", "value": True}, sym)
        self.assertFalse(out["match"])
        self.assertTrue(out.get("inconclusive"))

    def test_satisfiable_scoring(self):
        sym = {
            "intent": "satisfiable",
            "symbolic_status": "ok",
            "satisfiable": True,
        }
        out = score_question({"intent": "satisfiable", "value": True}, sym)
        self.assertTrue(out["match"])

    def test_unsupported_intent_unscored(self):
        sym = {
            "intent": "model_expansion",
            "symbolic_status": "unsupported",
            "status": "unsupported",
            "message": "backend missing",
        }
        out = score_question({"mode": "boolean", "value": True}, sym)
        self.assertEqual(out.get("failure_category"), "unsupported_intent")


if __name__ == "__main__":
    unittest.main()
