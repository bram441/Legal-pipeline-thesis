import os
import unittest

from pipeline.extraction.json_ir import ExtractionIRValidationError, normalize_case_ir, normalize_query_ir


class TestExtractionJSONIR(unittest.TestCase):
    def test_normalize_case_ir_renders_assertions(self):
        schema = {
            "types": ["Person"],
            "predicates": [{"name": "IsDeceased", "args": ["Person"], "returns": "Bool", "kind": "observable"}],
            "functions": [],
        }
        case_ir = {
            "entities": {"Person": ["Bert"]},
            "assertions": [{"symbol": "is_deceased", "args": ["bert"], "negated": False}],
            "value_assertions": [],
        }
        out = normalize_case_ir(case_ir, schema)
        self.assertEqual(out["facts"], ["IsDeceased(bert)."])
        self.assertEqual(out["entities"]["Person"], ["bert"])

    def test_normalize_case_ir_renders_function_value_assertions(self):
        schema = {
            "types": ["Company", "FinancialYear"],
            "predicates": [],
            "functions": [
                {"name": "AnnualNetTurnover", "args": ["Company", "FinancialYear"], "returns": "Real", "kind": "observable"}
            ],
        }
        case_ir = {
            "entities": {"Company": ["NV Delta"], "FinancialYear": ["FY1"]},
            "assertions": [],
            "value_assertions": [{"symbol": "annual net turnover", "args": ["nv_delta", "fy1"], "value": 800000}],
        }
        out = normalize_case_ir(case_ir, schema)
        self.assertEqual(out["facts"], ["AnnualNetTurnover(nv_delta,fy1) = 800000."])

    def test_normalize_case_ir_rejects_wrong_function_arity(self):
        schema = {
            "types": ["Company", "FinancialYear"],
            "predicates": [],
            "functions": [{"name": "EmployeeCount", "args": ["Company", "FinancialYear"], "returns": "Int"}],
        }
        case_ir = {
            "entities": {"Company": ["acme"], "FinancialYear": ["fy1"]},
            "assertions": [],
            "value_assertions": [{"symbol": "EmployeeCount", "args": ["acme"], "value": 9}],
        }
        with self.assertRaises(ExtractionIRValidationError):
            normalize_case_ir(case_ir, schema)

    def test_normalize_query_ir_resolves_predicate_and_singletons(self):
        schema = {
            "types": ["Company", "FinancialYear"],
            "predicates": [
                {"name": "IsMicroCompany", "args": ["Company", "FinancialYear"], "returns": "Bool", "kind": "derived"}
            ],
            "functions": [],
        }
        case = {"facts": [], "entities": {"Company": ["nv_delta"], "FinancialYear": ["fy1"]}}
        qir = {
            "kind": "predicate",
            "predicate_hint": "micro company",
            "mode": "boolean",
            "args": ["?", "?"],
            "intent": "",
            "symbol_hint": "",
            "entity_hint": "",
            "explain": False,
        }
        out = normalize_query_ir(qir, case=case, kb_schema=schema, user_question="Is the company a micro-company?")
        self.assertEqual(out["predicate"], "IsMicroCompany")
        self.assertEqual(out["args"], ["nv_delta", "fy1"])

    def test_normalize_query_ir_rejects_type_name_args(self):
        schema = {
            "types": ["Company"],
            "predicates": [{"name": "IsCompany", "args": ["Company"], "returns": "Bool", "kind": "derived"}],
            "functions": [],
        }
        case = {"facts": [], "entities": {"Company": ["acme"]}}
        qir = {
            "kind": "predicate",
            "predicate_hint": "IsCompany",
            "mode": "boolean",
            "args": ["Company"],
            "intent": "",
            "symbol_hint": "",
            "entity_hint": "",
            "explain": False,
        }
        out = normalize_query_ir(qir, case=case, kb_schema=schema, user_question="Is this company a company?")
        self.assertEqual(out["args"], ["acme"])

    def test_normalize_query_ir_splits_duplicate_person_args_using_is_deceased(self):
        old = os.environ.get("LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS")
        os.environ["LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS"] = "1"
        schema = {
            "types": ["Person"],
            "predicates": [
                {
                    "name": "SurvivingSpouseHasUsufructEntireEstate",
                    "args": ["Person", "Person"],
                    "returns": "Bool",
                    "kind": "derived",
                }
            ],
            "functions": [],
        }
        case = {
            "facts": ["IsDeceased(bert)."],
            "entities": {"Person": ["anna"]},
        }
        qir = {
            "kind": "predicate",
            "predicate_hint": "SurvivingSpouseHasUsufructEntireEstate",
            "mode": "boolean",
            "args": ["anna", "anna"],
            "intent": "",
            "symbol_hint": "",
            "entity_hint": "",
            "explain": False,
        }
        try:
            out = normalize_query_ir(
                qir,
                case=case,
                kb_schema=schema,
                user_question="Does the surviving spouse have usufruct of the entire estate?",
            )
        finally:
            if old is None:
                os.environ.pop("LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS", None)
            else:
                os.environ["LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS"] = old
        self.assertEqual(out["args"], ["anna", "bert"])

    def test_normalize_query_ir_swaps_deceased_arg_for_surviving_spouse_role(self):
        old = os.environ.get("LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS")
        os.environ["LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS"] = "1"
        schema = {
            "types": ["Person", "Estate"],
            "predicates": [
                {"name": "SurvivingSpouseHasRightToUsufructOfEntireEstate", "args": ["Person", "Estate"], "returns": "Bool", "kind": "derived"}
            ],
            "functions": [],
        }
        case = {
            "facts": ["IsDeceased(bert)."],
            "entities": {"Person": ["anna", "bert"], "Estate": ["estate_bert"]},
        }
        qir = {
            "kind": "predicate",
            "predicate_hint": "SurvivingSpouseHasRightToUsufructOfEntireEstate",
            "mode": "boolean",
            "args": ["bert", "estate_bert"],
            "intent": "",
            "symbol_hint": "",
            "entity_hint": "",
            "explain": False,
        }
        try:
            out = normalize_query_ir(
                qir,
                case=case,
                kb_schema=schema,
                user_question="Does the surviving spouse have right to usufruct of entire estate?",
            )
        finally:
            if old is None:
                os.environ.pop("LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS", None)
            else:
                os.environ["LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS"] = old
        self.assertEqual(out["args"][0], "anna")


if __name__ == "__main__":
    unittest.main()
