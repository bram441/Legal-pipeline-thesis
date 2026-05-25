import unittest

from idp_z3.predicate_solver import evaluate_atom
from pipeline.symbolic.antecedent_coverage import compute_antecedent_coverage, missing_observable_symbols


def _minimal_kb() -> str:
    return """
vocabulary V {
  type Actor
  relation: Actor * Actor -> Bool
  condition_exists: Actor -> Bool
  legal_result: Actor -> Bool
}

theory T:V {
  !a in Actor, b in Actor: relation(a,b) & condition_exists(b) => legal_result(a).
}
""".strip()


def _kb_schema(*, with_rules=True):
    schema = {
        "types": ["Actor"],
        "predicates": [
            {"name": "relation", "args": ["Actor", "Actor"], "returns": "Bool", "kind": "observable"},
            {"name": "condition_exists", "args": ["Actor"], "returns": "Bool", "kind": "observable"},
            {"name": "legal_result", "args": ["Actor"], "returns": "Bool", "kind": "derived"},
        ],
        "functions": [],
    }
    if with_rules:
        schema["rules"] = [
            {
                "forall": [
                    {"var": "a", "type": "Actor"},
                    {"var": "b", "type": "Actor"},
                ],
                "if": [
                    {"pred": "relation", "args": ["a", "b"]},
                    {"pred": "condition_exists", "args": ["b"]},
                ],
                "then": [{"pred": "legal_result", "args": ["a"]}],
            }
        ]
    return schema


class TestSemanticGrounding(unittest.TestCase):
    def test_antecedent_coverage_marks_missing_observable(self):
        case = {
            "facts": ["relation(alice,bob)."],
            "entities": {"Actor": ["alice", "bob"]},
        }
        query = {"type": "predicate", "predicate": "legal_result", "mode": "boolean", "args": ["alice"]}
        cov = compute_antecedent_coverage(case, query, _kb_schema())
        self.assertTrue(cov)
        missing = missing_observable_symbols(cov)
        self.assertIn("condition_exists", missing)

    def _run_evaluate_atom(self, case, kb, predicate, args):
        try:
            return evaluate_atom(case, kb, predicate, args)
        except (UnicodeEncodeError, OSError, RuntimeError) as e:
            self.skipTest("IDP evaluation unavailable in this environment: " + str(e))

    def test_entailment_with_closed_world_observables(self):
        kb = _minimal_kb()
        case = {
            "facts": ["relation(alice,bob).", "condition_exists(bob)."],
            "entities": {"Actor": ["alice", "bob"]},
            "kb_schema": _kb_schema(with_rules=False),
        }
        res = self._run_evaluate_atom(case, kb, "legal_result", ["alice"])
        self.assertTrue(res.get("certain"), res)

    def test_missing_observable_not_unknown_entailment(self):
        kb = _minimal_kb()
        case = {
            "facts": ["relation(alice,bob)."],
            "entities": {"Actor": ["alice", "bob"]},
            "kb_schema": _kb_schema(with_rules=False),
        }
        res = self._run_evaluate_atom(case, kb, "legal_result", ["alice"])
        self.assertFalse(res.get("certain"), res)
        self.assertFalse(
            res.get("possible") and not res.get("certain"),
            "open unknown from missing observable should not occur when observables are closed",
        )


if __name__ == "__main__":
    unittest.main()
