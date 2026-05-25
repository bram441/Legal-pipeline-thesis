import unittest

from pipeline.kb.json_ir import JSONIRCompilationError, preflight_json_ir_rule_predicates


class TestJsonIrPreflight(unittest.TestCase):
    def test_function_used_as_predicate_atom_raises(self):
        ir = {
            "types": ["Person"],
            "predicates": [{"name": "P", "args": ["Person"], "returns": "Bool"}],
            "functions": [{"name": "Share", "args": ["Person"], "returns": "Real"}],
            "rules": [
                {
                    "if": [{"pred": "P", "args": ["x"]}],
                    "then": [{"pred": "Share", "args": ["x"]}],
                    "operator": "implies",
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError) as ctx:
            preflight_json_ir_rule_predicates(ir)
        self.assertIn("Share", str(ctx.exception))

    def test_non_bool_predicate_in_rules_raises(self):
        ir = {
            "types": ["Person"],
            "predicates": [{"name": "Age", "args": ["Person"], "returns": "Int"}],
            "functions": [],
            "rules": [
                {
                    "if": [{"pred": "Age", "args": ["x"]}],
                    "then": [{"pred": "Age", "args": ["x"]}],
                    "operator": "implies",
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError) as ctx:
            preflight_json_ir_rule_predicates(ir)
        self.assertIn("Int", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
