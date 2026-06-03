"""
Regression tests for deterministic query arg repair (role questions vs case facts).

Run from repo root:
  python -m unittest discover -s tests -p "test_*.py" -v
"""
import copy
import os
import unittest

from pipeline.config import reload_config
from pipeline.extraction.query_role_resolve import (
    apply_role_arg_consistency,
    question_role_intent,
)


class TestQuestionRoleIntent(unittest.TestCase):
    def test_english_surviving_spouse(self):
        self.assertEqual(
            question_role_intent(
                "Does the surviving spouse have usufruct of the entire estate under Article 4.17?"
            ),
            "surviving_spouse",
        )

    def test_dutch_surviving_spouse(self):
        self.assertEqual(
            question_role_intent(
                "Heeft de langstlevende echtgenoot recht op vruchtgebruik van de gehele nalatenschap volgens artikel 4.17?"
            ),
            "surviving_spouse",
        )

    def test_dutch_overlevende_partner(self):
        self.assertEqual(
            question_role_intent("Rechten van de overlevende partner bij erfenis?"),
            "surviving_spouse",
        )

    def test_english_the_deceased(self):
        self.assertEqual(
            question_role_intent("What rights does the deceased have under the will?"),
            "deceased",
        )

    def test_dutch_overledene(self):
        self.assertEqual(
            question_role_intent("Welke rechten heeft de overledene?"),
            "deceased",
        )

    def test_none_for_unrelated(self):
        self.assertIsNone(question_role_intent("Is theft punishable under Article 410?"))

    def test_none_empty(self):
        self.assertIsNone(question_role_intent(""))
        self.assertIsNone(question_role_intent(None))


class TestApplyRoleArgConsistency(unittest.TestCase):
    def setUp(self):
        self._prev_domain_heuristics = os.environ.get("LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS")
        os.environ["LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS"] = "1"
        reload_config()

    def tearDown(self):
        if self._prev_domain_heuristics is None:
            os.environ.pop("LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS", None)
        else:
            os.environ["LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS"] = self._prev_domain_heuristics
        reload_config()

    _q_nl = (
        "Heeft de langstlevende echtgenoot recht op vruchtgebruik "
        "van de gehele nalatenschap volgens artikel 4.17?"
    )
    _q_en = (
        "Does the surviving spouse have the right to usufruct of the entire estate according to article 4.17?"
    )

    def _case_inheritance(self):
        return {
            "facts": [
                "deceased(bert).",
                "survivingSpouse(anna).",
                "deceasedLeavesDescendants(bert).",
            ]
        }

    def test_rewrites_deceased_arg_to_survivor_nl(self):
        case = self._case_inheritance()
        query = {"type": "predicate", "mode": "boolean", "predicate": "acquiredUsufructEntireEstate", "args": ["bert"]}
        qcopy = copy.deepcopy(query)
        self.assertTrue(apply_role_arg_consistency(self._q_nl, qcopy, case))
        self.assertEqual(qcopy["args"], ["anna"])

    def test_rewrites_deceased_arg_to_survivor_en(self):
        case = self._case_inheritance()
        query = {"type": "predicate", "mode": "boolean", "predicate": "usufructEntireEstate", "args": ["bert"]}
        qcopy = copy.deepcopy(query)
        self.assertTrue(apply_role_arg_consistency(self._q_en, qcopy, case))
        self.assertEqual(qcopy["args"], ["anna"])

    def test_noop_when_already_survivor(self):
        case = self._case_inheritance()
        query = {"type": "predicate", "mode": "boolean", "predicate": "p", "args": ["anna"]}
        qcopy = copy.deepcopy(query)
        self.assertFalse(apply_role_arg_consistency(self._q_en, qcopy, case))
        self.assertEqual(qcopy["args"], ["anna"])

    def test_noop_when_question_names_person(self):
        case = self._case_inheritance()
        query = {"type": "predicate", "mode": "boolean", "predicate": "p", "args": ["bert"]}
        qcopy = copy.deepcopy(query)
        self.assertFalse(
            apply_role_arg_consistency("Does Bert have usufruct of the entire estate?", qcopy, case)
        )
        self.assertEqual(qcopy["args"], ["bert"])

    def test_noop_when_two_survivors_ambiguous(self):
        case = {
            "facts": [
                "deceased(bert).",
                "survivingSpouse(anna).",
                "survivingLegalCohabitant(charlie).",
            ]
        }
        query = {"type": "predicate", "mode": "boolean", "predicate": "p", "args": ["bert"]}
        qcopy = copy.deepcopy(query)
        self.assertFalse(apply_role_arg_consistency(self._q_en, qcopy, case))
        self.assertEqual(qcopy["args"], ["bert"])

    def test_deceased_intent_rewrites_survivor_to_sole_deceased(self):
        case = {"facts": ["deceased(bert).", "survivingSpouse(anna)."]}
        query = {"type": "predicate", "mode": "boolean", "predicate": "p", "args": ["anna"]}
        qcopy = copy.deepcopy(query)
        self.assertTrue(
            apply_role_arg_consistency("What debts apply to the deceased under the estate?", qcopy, case)
        )
        self.assertEqual(qcopy["args"], ["bert"])

    def test_skips_non_predicate_query(self):
        case = self._case_inheritance()
        query = {"type": "intent", "intent": "get_range", "symbol": "f", "entity": "bert"}
        qcopy = copy.deepcopy(query)
        self.assertFalse(apply_role_arg_consistency(self._q_en, qcopy, case))

    def test_skips_set_mode(self):
        case = self._case_inheritance()
        query = {"type": "predicate", "mode": "set", "predicate": "heirsOf", "args": []}
        qcopy = copy.deepcopy(query)
        self.assertFalse(apply_role_arg_consistency(self._q_en, qcopy, case))

    def test_survivedby_marks_deceased(self):
        """Estate-style unary facts sometimes use survivedBy* for the deceased."""
        case = {"facts": ["survivedByDescendantAdoptedDescendant(bert).", "survivingSpouse(anna)."]}
        query = {"type": "predicate", "mode": "boolean", "predicate": "p", "args": ["bert"]}
        qcopy = copy.deepcopy(query)
        self.assertTrue(apply_role_arg_consistency(self._q_en, qcopy, case))
        self.assertEqual(qcopy["args"], ["anna"])

    def test_binary_query_rewrites_first_person_arg_using_inferred_survivor(self):
        case = {
            "facts": [
                "IsDeceased(bert).",
                "LeavesDescendants(bert).",
            ],
            "entities": {"Person": ["anna", "bert"]},
        }
        query = {
            "type": "predicate",
            "mode": "boolean",
            "predicate": "SurvivingSpouseHasRightToUsufructOfEntireEstate",
            "args": ["bert", "?"],
        }
        schema = {
            "predicates": [
                {"name": "SurvivingSpouseHasRightToUsufructOfEntireEstate", "args": ["Person", "Estate"], "returns": "Bool"}
            ]
        }
        qcopy = copy.deepcopy(query)
        self.assertTrue(apply_role_arg_consistency(self._q_en, qcopy, case, kb_schema=schema))
        self.assertEqual(qcopy["args"], ["anna", "?"])


if __name__ == "__main__":
    unittest.main()
