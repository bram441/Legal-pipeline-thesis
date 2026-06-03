"""Regression tests for case fact validation."""
import os
import unittest

from pipeline.config import reload_config
from pipeline.extraction import extractor
from pipeline.validation.fo_validation import normalize_and_validate_case, normalize_and_validate_query


class TestQueryArityErrors(unittest.TestCase):
    def test_boolean_query_empty_args_reports_arity_detail(self):
        schema = {"predicates": [{"name": "illegalStay", "args": ["Person"], "returns": "Bool"}]}
        case = {"facts": ["illegalStay(ahmed)."]}
        with self.assertRaises(ValueError) as ctx:
            normalize_and_validate_query(
                {"type": "predicate", "predicate": "illegalStay", "mode": "boolean", "args": []},
                case,
                kb_schema=schema,
            )
        self.assertIn("expected 1", str(ctx.exception))
        self.assertIn("got 0", str(ctx.exception))

    def test_extractor_feedback_appends_arity_remediation(self):
        schema = {"predicates": [{"name": "P", "args": ["Person"], "returns": "Bool"}]}
        err = (
            'Predicate arity mismatch for P: expected 1 arg(s) [Person] for mode="boolean", '
            "got 0 non-empty arg(s) []. List one case constant per position"
        )
        prev = {"query": {"type": "predicate", "predicate": "P", "mode": "boolean", "args": []}}
        msg = extractor._schema_feedback_message(ValueError(err), prev, kb_schema=schema)
        self.assertIn("REMEDIATION", msg)
        self.assertIn("exactly 1", msg)


class TestExclusiveSuccessionBranches(unittest.TestCase):
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

    def test_rejects_two_branches_same_entity(self):
        raw = {
            "facts": [
                "deceasedLeavesDescendants(bert).",
                "deceasedLeavesOtherHeirsOrNoHeirs(bert).",
            ]
        }
        with self.assertRaises(ValueError) as ctx:
            normalize_and_validate_case(raw)
        self.assertIn("incompatible succession branches", str(ctx.exception).lower())

    def test_allows_single_branch(self):
        raw = {
            "facts": [
                "deceasedLeavesDescendants(bert).",
                "spouseIsSurvivingSpouse(anna).",
            ]
        }
        out = normalize_and_validate_case(raw)
        self.assertEqual(len(out["facts"]), 2)


class TestFactArgumentValidation(unittest.TestCase):
    def test_rejects_wildcard_placeholder_argument(self):
        raw = {"facts": ["isDescendant(_,carla)."]}
        with self.assertRaises(ValueError) as ctx:
            normalize_and_validate_case(raw)
        self.assertIn("wildcard argument", str(ctx.exception).lower())

    def test_canonicalizes_case_entity_type_keys_to_schema(self):
        raw = {
            "facts": ["p(anna)."],
            "entities": {"person": ["anna"]},
        }
        schema = {"types": ["Person"], "predicates": [{"name": "p", "args": ["Person"], "returns": "Bool"}]}
        out = normalize_and_validate_case(raw, kb_schema=schema)
        self.assertIn("Person", out.get("entities", {}))
        self.assertNotIn("person", out.get("entities", {}))

    def test_rejects_query_when_arg_not_valid_for_typed_entity_pool(self):
        case = {
            "facts": ["p(anna)."],
            "entities": {"Person": ["anna"], "Estate": ["estate_bert"]},
        }
        schema = {
            "types": ["Person", "Estate"],
            "predicates": [{"name": "q", "args": ["Person", "Estate"], "returns": "Bool"}],
        }
        with self.assertRaises(ValueError) as ctx:
            normalize_and_validate_query(
                {
                    "type": "predicate",
                    "predicate": "q",
                    "mode": "boolean",
                    "args": ["anna", "not_in_case_estate"],
                },
                case,
                kb_schema=schema,
            )
        self.assertIn("not a valid Estate entity", str(ctx.exception))

    def test_allows_wildcard_for_missing_required_type(self):
        case = {"facts": ["p(anna)."], "entities": {"Person": ["anna"]}}
        schema = {
            "types": ["Person", "Estate"],
            "predicates": [{"name": "q", "args": ["Person", "Estate"], "returns": "Bool"}],
        }
        out = normalize_and_validate_query(
            {"type": "predicate", "predicate": "q", "mode": "boolean", "args": ["anna", "?"]},
            case,
            kb_schema=schema,
        )
        self.assertEqual(out["args"], ["anna", "?"])


if __name__ == "__main__":
    unittest.main()
