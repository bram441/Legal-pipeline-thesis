"""Tests for model_expansion routing and normalization."""

import unittest

from pipeline.semantic.intent_routing import classify_symbolic_intent
from pipeline.symbolic.intent_execution import build_execution_query, build_unified_symbolic_result
from pipeline.symbolic.model_expansion_outputs import extract_possible_outputs


class TestModelExpansionIntent(unittest.TestCase):
    def test_routes_possible_question(self):
        r = classify_symbolic_intent(question_text="Which legal consequences may apply?")
        self.assertEqual(r["selected_intent"], "model_expansion")

    def test_build_execution_query(self):
        routing = classify_symbolic_intent(question_text="Which sanctions can apply?")
        q = build_execution_query(
            {"type": "intent", "intent": "model_expansion"},
            routing,
            kb_schema={"types": [], "predicates": [], "functions": []},
        )
        self.assertEqual(q["intent"], "model_expansion")
        self.assertGreaterEqual(q["max_models"], 1)

    def test_possible_outputs_extraction(self):
        models = [
            {
                "true_atoms": [{"predicate": "sanction_fine", "args": ["ann"]}],
                "function_values": [],
            },
            {
                "true_atoms": [{"predicate": "sanction_prison", "args": ["ann"]}],
                "function_values": [],
            },
        ]
        out = extract_possible_outputs(models, legal_output_symbols=["sanction_fine", "sanction_prison"])
        self.assertEqual(len(out), 2)
        symbols = {o["symbol"] for o in out}
        self.assertIn("sanction_fine", symbols)
        self.assertIn("sanction_prison", symbols)

    def test_unified_result_shape(self):
        routing = classify_symbolic_intent(question_text="Which sanctions can apply?")
        normalized = {
            "intent": "model_expansion",
            "status": "ok",
            "models": [{"true_atoms": [{"predicate": "s1", "args": []}], "function_values": []}],
        }
        unified = build_unified_symbolic_result(
            routing=routing,
            sat_check={"status": "ok", "kb_case_satisfiable": True},
            normalized=normalized,
            exec_query={"type": "intent", "intent": "model_expansion", "max_models": 2},
        )
        me = unified.get("model_expansion") or {}
        self.assertIn("possible_outputs", me)
        self.assertEqual(me["max_models"], 2)


if __name__ == "__main__":
    unittest.main()
