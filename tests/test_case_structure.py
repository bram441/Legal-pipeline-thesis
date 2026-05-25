"""
Regression tests for IDP structure generation (empty domain placeholders).

Run: python -m unittest discover -s tests -p "test_*.py" -v
"""
import unittest

from idp_z3.case_structure import build_structure_block_from_facts


class TestEmptyTypePlaceholders(unittest.TestCase):
    def test_injects_empty_domains_for_unused_types(self):
        """Unused KB types get explicit empty interpretations (no synthetic symbols)."""
        facts = ["survivingSpouse(anna).", "hasDescendants(bert)."]
        case = {"facts": facts, "entities": {"Person": ["anna", "bert"]}}
        s = build_structure_block_from_facts(
            facts,
            entities=case.get("entities"),
            kb_primary_type="Person",
            kb_types=["Person", "Good", "Estate"],
            kb_predicate_names=["survivingSpouse", "hasDescendants"],
        )
        self.assertIn("Good := {}.", s)
        self.assertIn("Estate := {}.", s)


class TestFunctionAssignments(unittest.TestCase):
    def test_supports_unary_and_binary_function_assignments(self):
        facts = [
            "deceasedSpouse(bert) = anna.",
            "annualNetTurnover(nv_delta, fy1) = 12000000.",
        ]
        s = build_structure_block_from_facts(
            facts,
            entities={"Person": ["anna", "bert"], "Company": ["nv_delta"], "FinancialYear": ["fy1"]},
            kb_primary_type="Person",
            kb_types=["Person", "Company", "FinancialYear"],
            kb_predicate_names=[],
        )
        self.assertIn("deceasedSpouse := {'bert' -> 'anna'}.", s)
        self.assertIn("annualNetTurnover := {('nv_delta','fy1') -> 12000000}.", s)


class TestTypedDomainSeeding(unittest.TestCase):
    def test_uses_entity_type_domain_when_primary_type_differs(self):
        facts = ["heeftIllegaalVerblijf(ahmed)."]
        s = build_structure_block_from_facts(
            facts,
            entities={"Persoon": ["ahmed"]},
            kb_primary_type="Vreemdeling",
            kb_types=["Vreemdeling", "Persoon"],
            kb_predicate_names=["heeftIllegaalVerblijf"],
        )
        self.assertIn("Persoon := {'ahmed'}.", s)
        self.assertIn("heeftIllegaalVerblijf := {'ahmed'}.", s)


if __name__ == "__main__":
    unittest.main()
