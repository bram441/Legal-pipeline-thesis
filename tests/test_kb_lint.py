"""Tests for pre-IDP KB static lint."""
import unittest

from pipeline.kb.kb_lint import KBLintError, lint_kb_fo_text
from pipeline.kb.schema import extract_schema_from_kb_fo


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

    def test_zero_arity_function_declared_and_called_passes(self):
        """Regression: `name: () -> Real` must count as declared for `name()` calls."""
        kb = """vocabulary V {
  type Company
  type FinancialYear
  employee_threshold: () -> Real
  turnover_threshold: () -> Real
  balance_sheet_threshold: () -> Real
  annual_average_employees: Company * FinancialYear -> Real
  exceeds_employee_threshold: Company * FinancialYear -> Bool
  P: Company -> Bool
}
theory T:V {
  ! c in Company, fy in FinancialYear:
    exceeds_employee_threshold(c, fy)
    <=> annual_average_employees(c, fy) > employee_threshold().
  ! c in Company: P(c).
}
"""
        lint_kb_fo_text(kb)
        schema = extract_schema_from_kb_fo(kb)
        fn_names = {f["name"] for f in schema["functions"]}
        self.assertEqual(
            {"employee_threshold", "turnover_threshold", "balance_sheet_threshold"},
            {n for n in fn_names if n.endswith("_threshold")},
        )
        for fn in schema["functions"]:
            if fn["name"] == "employee_threshold":
                self.assertEqual([], fn["args"])
                self.assertEqual("Real", fn["returns"])

    def test_undeclared_zero_arity_function_call_fails(self):
        kb = """vocabulary V {
  type Company
  P: Company -> Bool
}
theory T:V {
  ! c in Company: P(c) & unknown_threshold() > 0.
}
"""
        with self.assertRaises(KBLintError) as ctx:
            lint_kb_fo_text(kb)
        self.assertIn("undeclared", str(ctx.exception).lower())
        self.assertIn("unknown_threshold", str(ctx.exception))

    def test_normal_predicate_and_function_still_lint(self):
        kb = """vocabulary V {
  type Company
  type FinancialYear
  f: Company * FinancialYear -> Real
  exceeds: Company * FinancialYear -> Bool
}
theory T:V {
  ! c in Company, fy in FinancialYear:
    exceeds(c, fy) <=> f(c, fy) > 0.
}
"""
        lint_kb_fo_text(kb)
        bad = """vocabulary V {
  type Company
  exceeds: Company -> Bool
}
theory T:V {
  ! c in Company: exceeds(c) & missing(c).
}
"""
        with self.assertRaises(KBLintError) as ctx:
            lint_kb_fo_text(bad)
        self.assertIn("missing", str(ctx.exception))

    def test_run_009_style_micro_threshold_fo_snippet_passes(self):
        """Smoke-style FO pattern from run_009 / run_119 model sweep failures."""
        kb = """vocabulary V {
  type Company
  type FinancialYear
  employee_threshold: () -> Real
  turnover_threshold: () -> Real
  balance_sheet_threshold: () -> Real
  annual_average_employees: Company * FinancialYear -> Real
  annual_turnover: Company * FinancialYear -> Real
  balance_sheet_total: Company * FinancialYear -> Real
  exceeds_employee_threshold: Company * FinancialYear -> Bool
  exceeds_turnover_threshold: Company * FinancialYear -> Bool
  exceeds_balance_sheet_threshold: Company * FinancialYear -> Bool
}
theory T:V {
  ! c in Company, fy in FinancialYear:
    exceeds_employee_threshold(c, fy) <=> annual_average_employees(c, fy) > employee_threshold().
  ! c in Company, fy in FinancialYear:
    exceeds_turnover_threshold(c, fy) <=> annual_turnover(c, fy) > turnover_threshold().
  ! c in Company, fy in FinancialYear:
    exceeds_balance_sheet_threshold(c, fy) <=> balance_sheet_total(c, fy) > balance_sheet_threshold().
}
"""
        lint_kb_fo_text(kb)

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
