"""Tests for get_range / optimization routing."""

import unittest

from pipeline.semantic.intent_routing import INTENT_GET_RANGE, INTENT_OPTIMIZATION, classify_symbolic_intent
from pipeline.symbolic.intent_execution import build_execution_query
from pipeline.symbolic.results import normalize_get_range


class TestGetRangeIntent(unittest.TestCase):
    def test_routes_range_question(self):
        r = classify_symbolic_intent(question_text="What is the possible fine range?")
        self.assertEqual(r["selected_intent"], INTENT_GET_RANGE)

    def test_minimum_routes_optimization_when_supported(self):
        r = classify_symbolic_intent(
            question_text="What is the minimum fine?",
            optimization_supported=True,
        )
        self.assertEqual(r["selected_intent"], INTENT_OPTIMIZATION)

    def test_build_get_range_query(self):
        routing = classify_symbolic_intent(
            question_text="What is the fine amount?",
            query={"type": "intent", "intent": "get_range", "function": "fine_amount", "args": ["a"]},
        )
        kb = {
            "types": ["Person"],
            "predicates": [],
            "functions": [{"name": "fine_amount", "args": ["Person"], "returns": "Int", "kind": "observable"}],
        }
        q = build_execution_query(
            {"type": "intent", "intent": "get_range", "function": "fine_amount", "args": ["a"]},
            routing,
            kb_schema=kb,
        )
        self.assertEqual(q["function"], "fine_amount")

    def test_normalize_possible_model_only(self):
        out = normalize_get_range(
            {"range": "1 -> 5", "via_model_expand": True},
            {"function": "fine_amount"},
        )
        self.assertEqual(out["confidence"], "possible_model_only")

    def test_normalize_unsupported(self):
        out = normalize_get_range({"status": "unsupported", "message": "no binding"}, {})
        self.assertEqual(out["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
