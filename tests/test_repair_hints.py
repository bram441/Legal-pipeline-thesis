"""Tests for KB repair hint classification."""
import unittest

from pipeline.kb.compiler import _kb_repair_prompt_path
from pipeline.kb.repair_hints import build_machine_repair_hints


class TestRepairPromptPath(unittest.TestCase):
    def test_semantic_unsat(self):
        self.assertIn(
            "semantic",
            _kb_repair_prompt_path("KB theory is unsatisfiable: no model"),
        )

    def test_semantic_ordinal(self):
        self.assertIn("semantic", _kb_repair_prompt_path("IDP semantic check failed: ordinal must be >= 1"))

    def test_symbolic_parse(self):
        self.assertIn("syntax", _kb_repair_prompt_path("IDP failed to parse compiled KB: Expected"))


class TestMachineHints(unittest.TestCase):
    def test_detects_bool_star(self):
        prev = "vocabulary V {\n  type Person\n  foo: Bool*bar\n}\n"
        h = build_machine_repair_hints("parse error", prev)
        self.assertIn("AUTOCHECK", h)
        self.assertIn("Bool", h)

    def test_empty_when_clean(self):
        h = build_machine_repair_hints("some other error", "vocabulary V {\n  type Person\n}\n")
        self.assertIn("ERROR REPORT", h)

    def test_detects_shorthand_vocab(self):
        prev = "vocabulary V {\n  Person\n  deceased: Person\n}\n"
        h = build_machine_repair_hints("KB lint: bare type/symbol", prev)
        self.assertIn("shorthand", h.lower())


if __name__ == "__main__":
    unittest.main()
