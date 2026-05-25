import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.extraction.json_ir import (
    ExtractionIRValidationError,
    _pick_most_specific_derived_predicate,
    _validate_query_target_for_legal_question,
)


class TestQueryTargetValidation(unittest.TestCase):
    def test_rejects_observable_when_derived_exists(self):
        kb = {
            "predicates": [
                {"name": "has_status", "args": ["Person"], "returns": "Bool", "kind": "observable"},
                {"name": "legal_status_holds", "args": ["Person"], "returns": "Bool", "kind": "derived"},
            ]
        }
        q = "Does the person qualify as X within the meaning of Article 2?"
        with self.assertRaises(ExtractionIRValidationError):
            _validate_query_target_for_legal_question("has_status", q, kb)

    def test_rejects_observable_when_only_observables_and_definition_question(self):
        kb = {
            "predicates": [
                {"name": "has_status", "args": ["Person"], "returns": "Bool", "kind": "observable"},
            ]
        }
        q = "Is status X within the meaning of Article 2?"
        with self.assertRaises(ExtractionIRValidationError):
            _validate_query_target_for_legal_question("has_status", q, kb)

    def test_prefers_effect_predicate_over_classification(self):
        kb = {
            "predicates": [
                {
                    "name": "is_size_category",
                    "args": ["Company", "Period"],
                    "returns": "Bool",
                    "kind": "derived",
                    "description": "Indicates size category.",
                },
                {
                    "name": "consequences_apply_from_following_period",
                    "args": ["Company", "Period"],
                    "returns": "Bool",
                    "kind": "derived",
                    "description": "Indicates legal consequences apply from the following period.",
                },
            ]
        }
        q = "Do the consequences apply from the period following 2025?"
        picked = _pick_most_specific_derived_predicate(q, kb, "is_size_category")
        self.assertEqual(picked, "consequences_apply_from_following_period")


if __name__ == "__main__":
    unittest.main()
