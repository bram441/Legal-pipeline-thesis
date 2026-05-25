"""Tests for pre-IDP KB static lint."""
import unittest

from pipeline.kb.kb_lint import KBLintError, lint_kb_fo_text


class TestKBLint(unittest.TestCase):
    def test_minimal_kb_passes(self):
        kb = """vocabulary V {
  type Thing
  P: Thing -> Bool
}
theory T:V {
  ! x in Thing: P(x).
}
"""
        lint_kb_fo_text(kb)

    def test_rejects_let_in_theory(self):
        kb = """vocabulary V {
  type Thing
  P: Thing -> Bool
}
theory T:V {
  let x = 1 in P(x).
}
"""
        with self.assertRaises(KBLintError) as ctx:
            lint_kb_fo_text(kb)
        self.assertIn("let", str(ctx.exception).lower())

    def test_rejects_undeclared_predicate_call(self):
        kb = """vocabulary V {
  type Thing
  P: Thing -> Bool
}
theory T:V {
  ! x in Thing: P(x) & Q(x).
}
"""
        with self.assertRaises(KBLintError) as ctx:
            lint_kb_fo_text(kb)
        self.assertIn("undeclared", str(ctx.exception).lower())

    def test_rejects_malformed_vocab_declarations(self):
        kb = """vocabulary V {
  Person
  deceased: Person
}
theory T:V {
  ! x in Person: deceased(x).
}
"""
        with self.assertRaises(KBLintError) as ctx:
            lint_kb_fo_text(kb)
        msg = str(ctx.exception)
        self.assertIn("bare type/symbol", msg)
        self.assertIn("undeclared", msg)


if __name__ == "__main__":
    unittest.main()
