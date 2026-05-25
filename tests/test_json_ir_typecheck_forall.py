import unittest

from pipeline.kb.json_ir import JSONIRCompilationError, normalize_json_ir


class TestJsonIrForallTypecheck(unittest.TestCase):
    def test_observable_in_then_reported_before_unbound_var(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "p_hold", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "p_derived", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [],
                    "if": [],
                    "then": [{"pred": "p_hold", "args": ["x"]}],
                    "operator": "implies",
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError) as ctx:
            normalize_json_ir(ir)
        msg = str(ctx.exception).lower()
        self.assertIn("observable", msg)
        self.assertIn("then", msg)

    def test_empty_forall_allows_nullary_predicate(self):
        ir = {
            "types": ["Person"],
            "predicates": [{"name": "p_axiom", "args": [], "returns": "Bool", "kind": "derived"}],
            "functions": [],
            "rules": [
                {
                    "forall": [],
                    "if": [],
                    "then": [{"pred": "p_axiom", "args": []}],
                    "operator": "implies",
                }
            ],
        }
        norm = normalize_json_ir(ir)
        self.assertEqual(len(norm["rules"]), 1)
        self.assertIn("p_axiom", norm["rules"][0])


if __name__ == "__main__":
    unittest.main()
