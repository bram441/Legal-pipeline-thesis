"""Tests for pipeline.semantic.intent_routing."""

import unittest

from pipeline.semantic.intent_routing import (
    INTENT_DEDUCTION,
    INTENT_EXPLAIN,
    INTENT_GET_RANGE,
    INTENT_MODEL_EXPANSION,
    INTENT_OPTIMIZATION,
    INTENT_SATISFIABLE,
    QUESTION_TYPE_BOOLEAN,
    QUESTION_TYPE_CONSISTENCY,
    QUESTION_TYPE_EXPLANATION,
    QUESTION_TYPE_POSSIBLE_LIST,
    QUESTION_TYPE_RANGE_VALUE,
    classify_symbolic_intent,
)


class TestIntentRoutingClassifier(unittest.TestCase):
    def test_boolean_question(self):
        r = classify_symbolic_intent(
            question_text="Is the company a micro-company under article 4?",
            expected={"mode": "boolean", "value": True},
            query={"type": "predicate", "predicate": "micro", "mode": "boolean", "args": ["x"]},
        )
        self.assertEqual(r["detected_question_type"], QUESTION_TYPE_BOOLEAN)
        self.assertEqual(r["selected_intent"], INTENT_DEDUCTION)

    def test_possible_punishments(self):
        r = classify_symbolic_intent(
            question_text="What possible punishments could this person receive?",
        )
        self.assertEqual(r["detected_question_type"], QUESTION_TYPE_POSSIBLE_LIST)
        self.assertEqual(r["selected_intent"], INTENT_MODEL_EXPANSION)

    def test_which_sanctions(self):
        r = classify_symbolic_intent(question_text="Which sanctions can apply?")
        self.assertEqual(r["selected_intent"], INTENT_MODEL_EXPANSION)

    def test_fine_range(self):
        r = classify_symbolic_intent(question_text="What is the possible fine range?")
        self.assertEqual(r["detected_question_type"], QUESTION_TYPE_RANGE_VALUE)
        self.assertEqual(r["selected_intent"], INTENT_GET_RANGE)

    def test_minimum_fine_optimization_or_warning(self):
        r = classify_symbolic_intent(
            question_text="What is the minimum fine?",
            optimization_supported=True,
        )
        self.assertIn(r["selected_intent"], (INTENT_OPTIMIZATION, INTENT_GET_RANGE))

    def test_minimum_without_optimization(self):
        r = classify_symbolic_intent(
            question_text="What is the minimum fine?",
            optimization_supported=False,
        )
        self.assertEqual(r["selected_intent"], INTENT_GET_RANGE)
        self.assertTrue(any("optimization_not_supported" in w for w in r["warnings"]))

    def test_consistency(self):
        r = classify_symbolic_intent(question_text="Are these facts consistent with the law?")
        self.assertEqual(r["detected_question_type"], QUESTION_TYPE_CONSISTENCY)
        self.assertEqual(r["selected_intent"], INTENT_SATISFIABLE)

    def test_explanation(self):
        r = classify_symbolic_intent(question_text="Explain why the legal consequences apply.")
        self.assertEqual(r["detected_question_type"], QUESTION_TYPE_EXPLANATION)
        self.assertEqual(r["selected_intent"], INTENT_EXPLAIN)

    def test_ambiguous_without_target(self):
        r = classify_symbolic_intent(question_text="What about this situation?")
        self.assertEqual(r["selected_intent"], "unknown")

    def test_ambiguous_with_boolean_target(self):
        r = classify_symbolic_intent(
            question_text="What about this situation?",
            query={"type": "predicate", "predicate": "applies", "mode": "boolean", "args": ["a"]},
        )
        self.assertEqual(r["selected_intent"], INTENT_DEDUCTION)


if __name__ == "__main__":
    unittest.main()
