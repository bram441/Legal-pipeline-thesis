"""Regression: curried vocabulary domains must become IDP product types."""
import unittest

from pipeline.kb.cache import _sanitize_common_llm_syntax


class TestVocabCurriedNormalize(unittest.TestCase):
    def test_binary_predicate_curried_to_product(self):
        kb = """vocabulary V {
  type Person
  type Goods
  holds: Person -> Goods -> Bool
}
theory T:V {
  ! a in Person: ! g in Goods: holds(a, g) => true.
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("holds: Person * Goods -> Bool", out)
        self.assertNotIn("Person -> Goods -> Bool", out)

    def test_ternary_function_curried(self):
        kb = """vocabulary V {
  type Person
  type Goods
  type Estate
  score: Person -> Goods -> Estate -> Int
}
theory T:V {
  ! a in Person: ! g in Goods: ! e in Estate: score(a, g, e) = 0 => true.
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("score: Person * Goods * Estate -> Int", out)

    def test_unary_unchanged(self):
        kb = """vocabulary V {
  type Person
  p: Person -> Bool
}
theory T:V {
  ! x in Person: p(x) => true.
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("p: Person -> Bool", out)

    def test_repairs_bare_type_and_shorthand_predicate(self):
        kb = """vocabulary V {
  Person
  deceased: Person
}
theory T:V {
  ! x in Person: deceased(x).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("type Person", out)
        self.assertIn("deceased: Person -> Bool", out)

    def test_rewrites_lte_to_idp_token(self):
        kb = """vocabulary V {
  type Person
  age: Person -> Int
}
theory T:V {
  ! x in Person: (age(x) <= 18) => true.
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("age(x) =< 18", out)

    def test_collapses_self_comparison_to_true(self):
        kb = """vocabulary V {
  type Person
  type Date
  filingDate: Person -> Date
  flagged: Person -> Bool
}
theory T:V {
  ! x in Person: (filingDate(x) <= filingDate(x)) => flagged(x).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("! x in Person: true => flagged(x).", out)

    def test_auto_declares_undeclared_theory_call(self):
        kb = """vocabulary V {
  type Person
  known: Person -> Bool
}
theory T:V {
  ! x in Person: missingPred(x) => known(x).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("missingPred: Person -> Bool", out)

    def test_rewrites_forall_cstyle_operators(self):
        kb = """vocabulary V {
  type Person
  p: Person -> Bool
  q: Person -> Bool
}
theory T:V {
  forall x:Person ( p(x) && !q(x) ).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("! x in Person:", out)
        self.assertIn("p(x)  &  ~q(x)", out)

    def test_rewrites_exists_keyword_variant(self):
        kb = """vocabulary V {
  type Person
  p: Person * Person -> Bool
}
theory T:V {
  ! x in Person: (Exists y in Person: p(x,y)).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("? y in Person: p(x,y)", out)

    def test_expands_grouped_quantifier_head(self):
        kb = """vocabulary V {
  type Person
  q: Person * Person -> Bool
}
theory T:V {
  !x,y in Person: q(x,y).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("! x in Person, y in Person: q(x,y).", out)

    def test_rewrites_corrupted_exists_token(self):
        kb = """vocabulary V {
  type Person
  p: Person -> Bool
}
theory T:V {
  ! x in Person: (exists(d *in Person: p(d)) => p(x)).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("? d in Person: p(d)", out)

    def test_drops_builtin_type_declarations(self):
        kb = """vocabulary V {
  type Person
  type Bool
  p: Person -> Bool
}
theory T:V {
  ! x in Person: p(x).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertNotIn("type Bool", out)

    def test_dedupes_symbol_name_colliding_with_type(self):
        kb = """vocabulary V {
  type Judgment
  type LegalAction
  Judgment: LegalAction -> Bool
}
theory T:V {
  ! l in LegalAction: Judgment(l).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("JudgmentPred: LegalAction -> Bool", out)
        self.assertIn("JudgmentPred(l)", out)

    def test_coerces_numeric_function_in_boolean_condition(self):
        kb = """vocabulary V {
  type Company
  yearsExceeded: Company -> Int
  small: Company -> Bool
}
theory T:V {
  ! c in Company: (small(c) & yearsExceeded(c)) => small(c).
}
"""
        out = _sanitize_common_llm_syntax(kb)
        self.assertIn("(small(c) & (yearsExceeded(c) ~= 0))", out)


if __name__ == "__main__":
    unittest.main()
