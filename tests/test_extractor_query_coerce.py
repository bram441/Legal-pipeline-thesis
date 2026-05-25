import unittest

from pipeline.extraction.extractor import _coerce_query_args_to_schema


class TestExtractorQueryCoerce(unittest.TestCase):
    def test_pads_boolean_args_to_expected_arity(self):
        query = {
            "type": "predicate",
            "predicate": "IsMicroVennootschap",
            "mode": "boolean",
            "args": ["nv"],
            "explain": False,
        }
        case = {
            "facts": [],
            "entities": {
                "Vennootschap": ["nv"],
                "Boekjaar": ["laatstAfgeslotenBoekjaar"],
            },
        }
        kb_schema = {
            "predicates": [
                {"name": "IsMicroVennootschap", "args": ["Vennootschap", "Boekjaar"], "returns": "Bool"}
            ]
        }

        changed = _coerce_query_args_to_schema(query, case, kb_schema)
        self.assertTrue(changed)
        self.assertEqual(query["args"], ["nv", "laatstafgeslotenboekjaar"])

    def test_prefers_fact_grounded_entity_over_question_alias(self):
        query = {
            "type": "predicate",
            "predicate": "IsMicroVennootschap",
            "mode": "boolean",
            "args": ["nv"],
            "explain": False,
        }
        case = {
            "facts": ["IsDochtervennootschap(nvdelta)."],
            "entities": {
                "Vennootschap": ["nv", "nvdelta"],
                "Boekjaar": ["b1"],
            },
        }
        kb_schema = {
            "predicates": [
                {"name": "IsMicroVennootschap", "args": ["Vennootschap", "Boekjaar"], "returns": "Bool"}
            ]
        }
        _coerce_query_args_to_schema(query, case, kb_schema)
        self.assertEqual(query["args"], ["nvdelta", "b1"])

    def test_fuzzy_maps_predicate_name_to_schema_canonical(self):
        query = {
            "type": "predicate",
            "predicate": "surviving_spouse_has_usufruct_on_entire_estate",
            "mode": "boolean",
            "args": ["anna", "estate1"],
            "explain": False,
        }
        case = {"facts": ["IsSurvivingSpouse(anna)."], "entities": {"Person": ["anna"], "Estate": ["estate1"]}}
        kb_schema = {
            "predicates": [
                {"name": "SurvivingSpouseHasRightToUsufructOfEntireEstate", "args": ["Person", "Estate"], "returns": "Bool"}
            ]
        }

        changed = _coerce_query_args_to_schema(query, case, kb_schema)
        self.assertTrue(changed)
        self.assertEqual(query["predicate"], "SurvivingSpouseHasRightToUsufructOfEntireEstate")
        self.assertEqual(query["args"], ["anna", "estate1"])

    def test_maps_predicate_name_even_when_mode_set(self):
        query = {
            "type": "predicate",
            "predicate": "surviving_spouse_has_usufruct_on_entire_estate",
            "mode": "set",
            "args": [],
            "explain": False,
        }
        case = {"facts": [], "entities": {}}
        kb_schema = {
            "predicates": [
                {"name": "SurvivingSpouseHasRightToUsufructOfEntireEstate", "args": ["Person", "Estate"], "returns": "Bool"}
            ]
        }
        changed = _coerce_query_args_to_schema(query, case, kb_schema)
        self.assertTrue(changed)
        self.assertEqual(query["predicate"], "SurvivingSpouseHasRightToUsufructOfEntireEstate")

    def test_question_aware_matching_prefers_entire_estate_predicate(self):
        query = {
            "type": "predicate",
            "predicate": "surviving_spouse_has_usufruct_on_entire_estate",
            "mode": "boolean",
            "args": ["bert", "?"],
            "explain": False,
        }
        case = {"facts": ["IsDeceased(bert)."], "entities": {"Person": ["bert"]}}
        kb_schema = {
            "predicates": [
                {"name": "SurvivingSpouseHasUsufructOnGoodsWithLegalReversion", "args": ["Person", "Good"], "returns": "Bool"},
                {"name": "SurvivingSpouseHasRightToUsufructOfEntireEstate", "args": ["Person", "Estate"], "returns": "Bool"},
            ]
        }
        _coerce_query_args_to_schema(
            query,
            case,
            kb_schema,
            user_question="Does the surviving spouse have the right to usufruct of the entire estate?",
        )
        self.assertEqual(query["predicate"], "SurvivingSpouseHasRightToUsufructOfEntireEstate")

    def test_question_reranker_overrides_valid_but_weaker_predicate(self):
        query = {
            "type": "predicate",
            "predicate": "SurvivingSpouseHasUsufructOnGoodsWithLegalReversion",
            "mode": "boolean",
            "args": ["anna", "?"],
            "explain": False,
        }
        case = {"facts": ["IsDeceased(bert)."], "entities": {"Person": ["anna", "bert"]}}
        kb_schema = {
            "predicates": [
                {"name": "SurvivingSpouseHasUsufructOnGoodsWithLegalReversion", "args": ["Person", "Good"], "returns": "Bool"},
                {"name": "SurvivingSpouseHasRightToUsufructOfEntireEstate", "args": ["Person", "Estate"], "returns": "Bool"},
            ]
        }
        _coerce_query_args_to_schema(
            query,
            case,
            kb_schema,
            user_question="Does the surviving spouse have the right to usufruct of the entire estate according to article 4.17?",
        )
        self.assertEqual(query["predicate"], "SurvivingSpouseHasRightToUsufructOfEntireEstate")

    def test_question_reranker_prefers_legal_effect_over_is_status_predicate(self):
        query = {
            "type": "predicate",
            "predicate": "IsSurvivingSpouse",
            "mode": "boolean",
            "args": ["anna"],
            "explain": False,
        }
        case = {"facts": ["IsDeceased(bert)."], "entities": {"Person": ["anna", "bert"]}}
        kb_schema = {
            "predicates": [
                {"name": "IsSurvivingSpouse", "args": ["Person"], "returns": "Bool"},
                {"name": "SurvivingSpouseHasRightToUsufructOfEntireEstate", "args": ["Person", "Estate"], "returns": "Bool"},
            ]
        }
        _coerce_query_args_to_schema(
            query,
            case,
            kb_schema,
            user_question="Does the surviving spouse have the right to usufruct of the entire estate according to article 4.17?",
        )
        self.assertEqual(query["predicate"], "SurvivingSpouseHasRightToUsufructOfEntireEstate")


if __name__ == "__main__":
    unittest.main()
