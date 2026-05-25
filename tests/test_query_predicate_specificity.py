import unittest

from pipeline.extraction.json_ir import _pick_most_specific_derived_predicate


class TestQueryPredicateSpecificity(unittest.TestCase):
    def test_prefers_more_specific_derived_name(self):
        kb_schema = {
            "predicates": [
                {
                    "name": "party_acquires_benefit",
                    "args": ["Actor"],
                    "returns": "Bool",
                    "kind": "derived",
                    "description": "Party acquires a benefit.",
                },
                {
                    "name": "party_acquires_benefit_of_entire_estate",
                    "args": ["Actor"],
                    "returns": "Bool",
                    "kind": "derived",
                    "description": "Party acquires benefit of the entire estate.",
                },
            ],
        }
        q = "Does the party acquire the benefit of the entire estate?"
        picked = _pick_most_specific_derived_predicate(
            q, kb_schema, "party_acquires_benefit"
        )
        self.assertEqual(picked, "party_acquires_benefit_of_entire_estate")


if __name__ == "__main__":
    unittest.main()
