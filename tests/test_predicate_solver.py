import unittest

from idp_z3.predicate_solver import _build_selection_constraint, _parse_predicate_arg_types_from_kb


class TestPredicateSolverWildcard(unittest.TestCase):
    def test_wildcard_arg_skips_selector_constraint(self):
        extra_vocab, extra_struct, constraint, atom = _build_selection_constraint(
            predicate="P",
            arg_types=["Person", "Estate"],
            args=["anna", "?"],
        )
        self.assertEqual(atom, "P(x0,x1)")
        self.assertEqual(extra_vocab, ["__sel0: Person -> Bool"])
        self.assertEqual(extra_struct, ["__sel0 := {'anna'}."])
        self.assertIn("__sel0(x0)", constraint)
        self.assertNotIn("__sel1(x1)", constraint)

    def test_parse_vocab_tolerates_bool_closing_brace_glued(self):
        fo = (
            "vocabulary V {\n"
            "  type Person\n"
            "  type Estate\n"
            "  P: Person * Estate -> Bool}\n"
            "theory T:V {\n"
            "  true.\n"
            "}\n"
        )
        self.assertEqual(_parse_predicate_arg_types_from_kb(fo, "P"), ["Person", "Estate"])


if __name__ == "__main__":
    unittest.main()
