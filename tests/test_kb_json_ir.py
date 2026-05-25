import os
import unittest

from pipeline.kb.json_ir import JSONIRCompilationError, parse_json_ir, render_json_ir_to_fo


class TestKBJsonIR(unittest.TestCase):
    def test_render_minimal_ir(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "Alive", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "LegallyAlive", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": ["!x in Person: Alive(x) => LegallyAlive(x)."],
        }
        fo = render_json_ir_to_fo(ir)
        self.assertIn("vocabulary V {", fo)
        self.assertIn("type Person", fo)
        self.assertIn("Alive: Person -> Bool", fo)
        self.assertIn("theory T:V {", fo)
        self.assertIn("Alive(x) => LegallyAlive(x)", fo)

    def test_parse_strips_code_fences(self):
        raw = """```json
{"types":["Person"],"predicates":[{"name":"P","args":["Person"],"returns":"Bool","kind":"observable"},{"name":"D","args":["Person"],"returns":"Bool","kind":"derived"}],"functions":[],"rules":["!x in Person: P(x) => D(x)."]}
```"""
        obj = parse_json_ir(raw)
        self.assertEqual(obj["types"], ["Person"])

    def test_parse_recovers_balanced_object_from_noisy_output(self):
        raw = """Some preamble
not json
{"types":["Person"],"predicates":[{"name":"P","args":["Person"],"returns":"Bool","kind":"observable"},{"name":"D","args":["Person"],"returns":"Bool","kind":"derived"}],"functions":[],"rules":["!x in Person: P(x) => D(x)."]}
trailing garbage } }"""
        obj = parse_json_ir(raw)
        self.assertIn("P(x)", obj["rules"][0])

    def test_rejects_unknown_type_reference(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "P", "args": ["Animal"], "returns": "Bool", "kind": "observable"},
                {"name": "D", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": ["!x in Person: P(x) => D(x)."],
        }
        with self.assertRaises(JSONIRCompilationError):
            render_json_ir_to_fo(ir)

    def test_rejects_undeclared_rule_symbol_by_default(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "Known", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "DerivedKnown", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": ["!x in Person: Missing(x) => DerivedKnown(x)."],
        }
        with self.assertRaises(JSONIRCompilationError):
            render_json_ir_to_fo(ir)

    def test_can_synthesize_undeclared_when_env_enabled_for_debugging(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "Known", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "DerivedKnown", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": ["!x in Person: Missing(x) => DerivedKnown(x)."],
        }
        old = os.environ.get("JSON_IR_SYNTHESIZE_UNDECLARED")
        os.environ["JSON_IR_SYNTHESIZE_UNDECLARED"] = "1"
        try:
            fo = render_json_ir_to_fo(ir)
        finally:
            if old is None:
                os.environ.pop("JSON_IR_SYNTHESIZE_UNDECLARED", None)
            else:
                os.environ["JSON_IR_SYNTHESIZE_UNDECLARED"] = old
        self.assertIn("Missing: Person -> Bool", fo)

    def test_rewrites_symbol_to_declared_variant(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "HasDescendants", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "HasDescendantsDerived", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": ["!x in Person: has_descendants(x) => HasDescendantsDerived(x)."],
        }
        fo = render_json_ir_to_fo(ir)
        self.assertIn("HasDescendantsDerived(x)", fo)

    def test_normalizes_rule_quantifier_variants(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "P", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "Q", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": ["!x,y in Person: (exists(d *in Person: P(d)) && !P(x)) => Q(x)."],
        }
        fo = render_json_ir_to_fo(ir)
        self.assertIn("! x in Person, y in Person:", fo)
        self.assertIn("? d in Person: P(d)", fo)
        self.assertIn("~P(x)", fo)

    def test_renders_rule_object_format(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "Cond", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "Out", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [{"var": "x", "type": "Person"}],
                    "if": [{"pred": "Cond", "args": ["x"]}],
                    "then": [{"pred": "Out", "args": ["x"]}],
                }
            ],
        }
        fo = render_json_ir_to_fo(ir)
        self.assertIn("Cond(x)", fo)
        self.assertIn("=>", fo)
        self.assertIn("Out(x)", fo)

    def test_rule_object_rejects_wrong_arity_instead_of_guessing(self):
        ir = {
            "types": ["Person", "Estate", "Goods"],
            "predicates": [
                {"name": "HasGood", "args": ["Goods"], "returns": "Bool", "kind": "observable"},
                {"name": "HasGoodDerived", "args": ["Goods"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [{"var": "estate", "type": "Estate"}],
                    "if": [],
                    "then": [{"pred": "HasGood", "args": ["estate", "extra"]}],
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError):
            render_json_ir_to_fo(ir)

    def test_renders_numeric_comparison_rule_object(self):
        ir = {
            "types": ["Company", "FinancialYear"],
            "predicates": [
                {"name": "ExceedsEmployeeCriterion", "args": ["Company", "FinancialYear"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [
                {"name": "AnnualAverageEmployees", "args": ["Company", "FinancialYear"], "returns": "Int", "kind": "observable"},
            ],
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}, {"var": "fy", "type": "FinancialYear"}],
                    "if": [{"left": {"func": "AnnualAverageEmployees", "args": ["c", "fy"]}, "op": ">", "right": 10}],
                    "then": [{"pred": "ExceedsEmployeeCriterion", "args": ["c", "fy"]}],
                    "operator": "iff",
                }
            ],
        }
        fo = render_json_ir_to_fo(ir)
        self.assertIn("ExceedsEmployeeCriterion(c,fy)", fo)
        self.assertIn("<=>", fo)
        self.assertIn("AnnualAverageEmployees(c,fy) > 10", fo)

    def test_rejects_unconstrained_consequent_variable(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "Obs", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "Der", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [{"var": "x", "type": "Person"}, {"var": "y", "type": "Person"}],
                    "if": [{"pred": "Obs", "args": ["x"]}],
                    "then": [{"pred": "Der", "args": ["y"]}],
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError) as ctx:
            render_json_ir_to_fo(ir)
        self.assertIn("unconstrained consequent variable", str(ctx.exception).lower())

    def test_rejects_derived_conclusion_without_observable_bridge(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "Obs", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "DerA", "args": ["Person"], "returns": "Bool", "kind": "derived"},
                {"name": "DerB", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [{"var": "x", "type": "Person"}],
                    "if": [{"pred": "DerA", "args": ["x"]}],
                    "then": [{"pred": "DerB", "args": ["x"]}],
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError) as ctx:
            render_json_ir_to_fo(ir)
        self.assertIn("not grounded", str(ctx.exception).lower())

    def test_rejects_non_reflexive_self_relation(self):
        ir = {
            "types": ["Person"],
            "predicates": [
                {"name": "Obs", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "RelatedTo", "args": ["Person", "Person"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [{"var": "x", "type": "Person"}],
                    "if": [{"pred": "Obs", "args": ["x"]}],
                    "then": [{"pred": "RelatedTo", "args": ["x", "x"]}],
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError) as ctx:
            render_json_ir_to_fo(ir)
        self.assertIn("same variable twice", str(ctx.exception).lower())

    def _floating_helper_ir(self, *, helper_kind="helper", extra_rules=None):
        rules = [
            {
                "forall": [{"var": "x", "type": "Actor"}],
                "if": [
                    {"pred": "fact_a", "args": ["x"]},
                    {"pred": "helper_h", "args": ["x"]},
                ],
                "then": [{"pred": "result", "args": ["x"]}],
            }
        ]
        if extra_rules:
            rules = extra_rules + rules
        return {
            "types": ["Actor"],
            "predicates": [
                {"name": "fact_a", "args": ["Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "helper_h", "args": ["Actor"], "returns": "Bool", "kind": helper_kind},
                {"name": "result", "args": ["Actor"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": rules,
        }

    def test_rejects_floating_helper_predicate(self):
        with self.assertRaises(JSONIRCompilationError) as ctx:
            render_json_ir_to_fo(self._floating_helper_ir())
        self.assertIn("helper predicate 'helper_h'", str(ctx.exception).lower())
        self.assertIn("never defined", str(ctx.exception).lower())

    def test_accepts_helper_defined_in_then(self):
        ir = self._floating_helper_ir(
            extra_rules=[
                {
                    "forall": [{"var": "x", "type": "Actor"}],
                    "if": [{"pred": "fact_a", "args": ["x"]}],
                    "then": [{"pred": "helper_h", "args": ["x"]}],
                }
            ]
        )
        fo = render_json_ir_to_fo(ir)
        self.assertIn("helper_h", fo)

    def test_accepts_helper_reclassified_as_observable(self):
        ir = self._floating_helper_ir(helper_kind="observable")
        fo = render_json_ir_to_fo(ir)
        self.assertIn("helper_h", fo)

    def test_rejects_unary_role_conflation_on_single_variable(self):
        ir = {
            "types": ["Actor"],
            "predicates": [
                {"name": "is_surviving_party", "args": ["Actor"], "returns": "Bool", "kind": "observable",
                 "description": "The person is the surviving party."},
                {"name": "is_deceased", "args": ["Actor"], "returns": "Bool", "kind": "observable",
                 "description": "The person is deceased."},
                {"name": "legal_result", "args": ["Actor"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [{"var": "x", "type": "Actor"}],
                    "if": [
                        {"pred": "is_surviving_party", "args": ["x"]},
                        {"pred": "is_deceased", "args": ["x"]},
                    ],
                    "then": [{"pred": "legal_result", "args": ["x"]}],
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError) as ctx:
            render_json_ir_to_fo(ir)
        self.assertIn("incompatible unary subject roles", str(ctx.exception).lower())

    def test_accepts_separate_variables_with_binary_relation(self):
        ir = {
            "types": ["Actor"],
            "predicates": [
                {"name": "status_of", "args": ["Actor", "Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "condition_holds", "args": ["Actor"], "returns": "Bool", "kind": "observable",
                 "description": "The deceased actor satisfies the condition."},
                {"name": "legal_result", "args": ["Actor"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [
                        {"var": "a", "type": "Actor"},
                        {"var": "b", "type": "Actor"},
                    ],
                    "if": [
                        {"pred": "status_of", "args": ["a", "b"]},
                        {"pred": "condition_holds", "args": ["b"]},
                    ],
                    "then": [{"pred": "legal_result", "args": ["a"]}],
                }
            ],
        }
        fo = render_json_ir_to_fo(ir)
        self.assertIn("legal_result", fo)

    def test_rejects_floating_helper_in_nested_or(self):
        ir = {
            "types": ["Actor"],
            "predicates": [
                {"name": "fact_a", "args": ["Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "helper_h", "args": ["Actor"], "returns": "Bool", "kind": "helper"},
                {"name": "other_condition", "args": ["Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "result", "args": ["Actor"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [{"var": "x", "type": "Actor"}],
                    "if": [
                        {"pred": "fact_a", "args": ["x"]},
                        {
                            "or": [
                                {"pred": "helper_h", "args": ["x"]},
                                {"pred": "other_condition", "args": ["x"]},
                            ]
                        },
                    ],
                    "then": [{"pred": "result", "args": ["x"]}],
                }
            ],
        }
        with self.assertRaises(JSONIRCompilationError) as ctx:
            render_json_ir_to_fo(ir)
        self.assertIn("helper predicate 'helper_h'", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
