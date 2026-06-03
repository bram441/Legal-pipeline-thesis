import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from idp_z3.case_structure import build_structure_block_from_facts


class TestCaseStructureDomains(unittest.TestCase):
    def test_function_domain_excludes_unused_entity_seeds(self):
        kb_schema = {
            "types": ["Company"],
            "predicates": [
                {"name": "is_subsidiary", "args": ["Company"], "returns": "Bool", "kind": "observable"},
            ],
            "functions": [
                {
                    "name": "annual_average_number_of_employees",
                    "args": ["Company"],
                    "returns": "Int",
                    "kind": "observable",
                },
            ],
        }
        facts = [
            "not is_subsidiary(nv_delta).",
            "annual_average_number_of_employees(nv_delta) = 9.",
        ]
        entities = {"Company": ["nv_delta"]}
        s = build_structure_block_from_facts(
            facts,
            entities=entities,
            kb_primary_type="Company",
            kb_types=["Company"],
            kb_schema=kb_schema,
        )
        self.assertIn("nv_delta", s)
        self.assertIn("Company := {'nv_delta'}.", s)
        self.assertNotIn("'nv'", s)


if __name__ == "__main__":
    unittest.main()
