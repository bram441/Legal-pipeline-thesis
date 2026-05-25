import unittest

from pipeline.extraction.json_ir import ExtractionIRValidationError, normalize_query_ir
from pipeline.eval.scoring import score_question
from pipeline.symbolic.intent_registry import (
    IntentAccessError,
    get_intent_spec,
    list_public_intents,
    validate_intent_name,
)
from pipeline.symbolic.query_validate import migrate_legacy_intent_query, validate_and_finalize_query
from pipeline.symbolic.results import normalize_deduction, normalize_propagation
from pipeline.symbolic.router import run_query
from pipeline.rendering.intent_renderers import render_model_expansion, render_propagation


class TestIntentRegistry(unittest.TestCase):
    def test_public_intents_exclude_internal(self):
        public = set(list_public_intents())
        self.assertIn("propagation", public)
        self.assertNotIn("deduction", public)
        self.assertNotIn("deduction_set", public)

    def test_internal_rejected_from_extraction(self):
        with self.assertRaises(IntentAccessError):
            validate_intent_name("deduction", allow_internal=False)

    def test_all_registry_intents_have_specs(self):
        for name in list_public_intents():
            spec = get_intent_spec(name)
            self.assertTrue(spec.public)


class TestQueryValidation(unittest.TestCase):
    def setUp(self):
        self.kb = {
            "types": ["Person"],
            "predicates": [
                {"name": "Obs", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "Der", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [
                {"name": "Amount", "args": ["Person"], "returns": "Int", "kind": "observable"},
            ],
        }
        self.case = {"facts": ["Obs(anna)."], "entities": {"Person": ["anna"]}}

    def test_predicate_boolean_valid(self):
        q = validate_and_finalize_query(
            {"type": "predicate", "predicate": "Der", "mode": "boolean", "args": ["anna"]},
            self.case,
            self.kb,
        )
        self.assertEqual(q["internal_intent"], "deduction")

    def test_predicate_set_unary_only(self):
        q = validate_and_finalize_query(
            {"type": "predicate", "predicate": "Der", "mode": "set", "args": []},
            self.case,
            self.kb,
        )
        self.assertEqual(q["internal_intent"], "deduction_set")
        self.assertEqual(q["args"], ["?"])

    def test_predicate_set_rejects_binary(self):
        kb2 = {
            "types": ["Person"],
            "predicates": [
                {"name": "Rel", "args": ["Person", "Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
        }
        with self.assertRaises(ValueError):
            validate_and_finalize_query(
                {"type": "predicate", "predicate": "Rel", "mode": "set", "args": []},
                self.case,
                kb2,
            )

    def test_propagation_defaults_derived_symbols(self):
        q = validate_and_finalize_query(
            {"type": "intent", "intent": "propagation"},
            self.case,
            self.kb,
        )
        self.assertIn("Der", q["focus_symbols"])
        self.assertNotIn("Obs", q["focus_symbols"])

    def test_model_expansion_max_models_cap(self):
        with self.assertRaises(ValueError):
            validate_and_finalize_query(
                {"type": "intent", "intent": "model_expansion", "max_models": 99},
                self.case,
                self.kb,
            )

    def test_get_range_rejects_unknown_function(self):
        with self.assertRaises(ValueError):
            validate_and_finalize_query(
                {
                    "type": "intent",
                    "intent": "get_range",
                    "function": "MissingFn",
                    "args": ["anna"],
                },
                self.case,
                self.kb,
            )

    def test_satisfiable_valid(self):
        q = validate_and_finalize_query({"type": "intent", "intent": "satisfiable"}, self.case, self.kb)
        self.assertEqual(q["intent"], "satisfiable")

    def test_migrate_deprecated_deduction(self):
        q = migrate_legacy_intent_query(
            {"type": "intent", "intent": "deduction", "predicate": "Der", "args": ["anna"]},
            self.kb,
        )
        self.assertEqual(q["type"], "predicate")
        self.assertEqual(q["mode"], "boolean")


class TestNormalizedResults(unittest.TestCase):
    def test_deduction_unknown_not_entailed(self):
        out = normalize_deduction({"possible": True, "certain": False}, {"predicate": "P", "args": ["a"]})
        self.assertEqual(out["label"], "unknown")
        self.assertEqual(out["certainty_class"], "inconclusive")

    def test_propagation_structure(self):
        out = normalize_propagation(
            {"certain_true": [{"predicate": "Der", "args": ["anna"]}], "certain_false": []},
            {"focus_symbols": ["Der"]},
        )
        self.assertEqual(len(out["certain_true"]), 1)


class TestScoringIntents(unittest.TestCase):
    def test_model_expansion_not_decisive(self):
        r = score_question(
            {"mode": "boolean", "value": True},
            {
                "intent": "model_expansion",
                "output_kind": "models",
                "models": [{"true_atoms": [{"predicate": "Der", "args": ["anna"]}]}],
                "certainty_class": "possible_model",
            },
        )
        self.assertFalse(r.get("match"))
        self.assertTrue(r.get("inconclusive"))

    def test_propagation_certain_true_boolean(self):
        r = score_question(
            {
                "mode": "boolean",
                "value": True,
                "target_predicate": "Der",
                "target_args": ["anna"],
            },
            {
                "intent": "propagation",
                "output_kind": "certain_facts",
                "certain_true": [{"predicate": "Der", "args": ["anna"]}],
                "certain_false": [],
            },
        )
        self.assertTrue(r["match"])


class TestRenderers(unittest.TestCase):
    def test_propagation_uses_certain_language(self):
        text = render_propagation({"certain_true": [{"predicate": "Der", "args": ["a"]}], "certain_false": []})
        self.assertIn("certain", text.lower())

    def test_model_expansion_uses_possible_language(self):
        text = render_model_expansion(
            {"models": [{"true_atoms": [{"predicate": "Der", "args": ["a"]}], "false_atoms": [], "function_values": []}]}
        )
        self.assertIn("possible", text.lower())


class TestExtractionRejectsInternalIntent(unittest.TestCase):
    def test_direct_deduction_in_ir_rejected(self):
        with self.assertRaises(ExtractionIRValidationError):
            normalize_query_ir(
                {"kind": "intent", "intent": "deduction", "predicate_hint": "Der", "args": ["anna"]},
                {"entities": {"Person": ["anna"]}},
                {"predicates": [{"name": "Der", "args": ["Person"], "kind": "derived", "returns": "Bool"}]},
                "Is Der true?",
            )


if __name__ == "__main__":
    unittest.main()
