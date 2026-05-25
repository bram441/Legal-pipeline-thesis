import unittest

from idp_z3.case_structure import build_structure_block_from_facts


class TestCaseStructureCloseWorld(unittest.TestCase):
    def test_closes_observable_not_derived(self):
        structure = build_structure_block_from_facts(
            facts=[],
            entities={"Actor": ["a"]},
            kb_primary_type="Actor",
            kb_types=["Actor"],
            kb_predicate_names=["obs", "result"],
            predicate_kinds={"obs": "observable", "result": "derived"},
        )
        self.assertIn("obs := {}.", structure)
        self.assertNotIn("result := {}", structure)

    def test_observable_with_positive_fact(self):
        structure = build_structure_block_from_facts(
            facts=["obs(a)."],
            entities={"Actor": ["a"]},
            kb_primary_type="Actor",
            kb_types=["Actor"],
            kb_predicate_names=["obs", "result"],
            predicate_kinds={"obs": "observable", "result": "derived"},
        )
        self.assertIn("obs := {'a'}.", structure)
        self.assertNotIn("result := {}", structure)


if __name__ == "__main__":
    unittest.main()
