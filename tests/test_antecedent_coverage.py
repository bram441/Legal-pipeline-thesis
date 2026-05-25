import unittest

from pipeline.symbolic.antecedent_coverage import compute_antecedent_coverage


class TestAntecedentCoverage(unittest.TestCase):
    def test_resolves_quant_vars_from_binary_case_facts(self):
        kb_schema = {
            "types": ["Actor"],
            "predicates": [
                {"name": "relation_of", "args": ["Actor", "Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "condition_holds", "args": ["Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "legal_result", "args": ["Actor"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [
                        {"var": "subject", "type": "Actor"},
                        {"var": "other", "type": "Actor"},
                    ],
                    "if": [
                        {"pred": "relation_of", "args": ["subject", "other"]},
                        {"pred": "condition_holds", "args": ["other"]},
                    ],
                    "then": [{"pred": "legal_result", "args": ["subject"]}],
                }
            ],
        }
        case = {
            "facts": [
                "relation_of(alice,bob).",
                "condition_holds(bob).",
            ],
        }
        query = {
            "type": "predicate",
            "predicate": "legal_result",
            "mode": "boolean",
            "args": ["alice"],
        }
        cov = compute_antecedent_coverage(case, query, kb_schema)
        self.assertEqual(len(cov), 1)
        statuses = {c["atom"]: c["status"] for c in cov[0]["conditions"]}
        self.assertEqual(statuses.get("relation_of(alice,bob)"), "present")
        self.assertEqual(statuses.get("condition_holds(bob)"), "present")

    def test_alternative_rule_missing_marked_non_blocking_when_entailed(self):
        kb_schema = {
            "types": ["Actor"],
            "predicates": [
                {"name": "relation_of", "args": ["Actor", "Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "condition_holds", "args": ["Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "other_condition", "args": ["Actor"], "returns": "Bool", "kind": "observable"},
                {"name": "legal_result", "args": ["Actor"], "returns": "Bool", "kind": "derived"},
            ],
            "functions": [],
            "rules": [
                {
                    "forall": [
                        {"var": "subject", "type": "Actor"},
                        {"var": "other", "type": "Actor"},
                    ],
                    "if": [
                        {"pred": "relation_of", "args": ["subject", "other"]},
                        {"pred": "condition_holds", "args": ["other"]},
                    ],
                    "then": [{"pred": "legal_result", "args": ["subject"]}],
                },
                {
                    "forall": [{"var": "subject", "type": "Actor"}],
                    "if": [{"pred": "other_condition", "args": ["subject"]}],
                    "then": [{"pred": "legal_result", "args": ["subject"]}],
                },
            ],
        }
        case = {"facts": ["relation_of(alice,bob).", "condition_holds(bob)."]}
        query = {"type": "predicate", "predicate": "legal_result", "mode": "boolean", "args": ["alice"]}
        cov = compute_antecedent_coverage(
            case,
            query,
            kb_schema,
            symbolic_result={"label": "entailed", "certain": True, "possible": True},
        )
        statuses = {}
        for block in cov:
            for c in block["conditions"]:
                statuses[c["atom"]] = c["status"]
        self.assertEqual(statuses.get("other_condition(alice)"), "missing_non_blocking")
        from pipeline.symbolic.antecedent_coverage import missing_observable_symbols

        self.assertNotIn("other_condition", missing_observable_symbols(cov))


if __name__ == "__main__":
    unittest.main()
