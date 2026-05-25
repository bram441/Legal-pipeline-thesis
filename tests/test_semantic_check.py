import unittest

from pipeline.kb.semantic_check import _build_minimal_structure


class TestSemanticMinimalStructure(unittest.TestCase):
    def test_dummy_elements_are_quoted(self):
        kb = """vocabulary V {
  type Person
  type Date
}
theory T:V {
  true.
}
"""
        struct = _build_minimal_structure(kb)
        self.assertIn("Person := {'elem_Person'}.", struct)
        self.assertIn("Date := {'elem_Date'}.", struct)
        self.assertNotIn("Date := {elem_Date}.", struct)


if __name__ == "__main__":
    unittest.main()
