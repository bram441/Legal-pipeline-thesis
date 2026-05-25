"""Tests for computed/composite observable hardening (Task B)."""

from __future__ import annotations

import unittest

from pipeline.kb.json_ir import JSONIRCompilationError, SymbolDecl, _validate_observable_composite_symbol_declarations


class TestCompositeObservableHardening(unittest.TestCase):
    def test_consolidation_eliminations_carried_out_rejected(self):
        decl = SymbolDecl(
            name="consolidation_eliminations_carried_out",
            args=["Company"],
            returns="Bool",
            kind="observable",
        )
        with self.assertRaises(JSONIRCompilationError):
            _validate_observable_composite_symbol_declarations([decl])

    def test_background_temporal_relation_allowed(self):
        decl = SymbolDecl(
            name="next_financial_year",
            args=["FinancialYear", "FinancialYear"],
            returns="Bool",
            kind="observable",
            background=True,
        )
        _validate_observable_composite_symbol_declarations([decl])

    def test_raw_numeric_facts_allowed(self):
        from pipeline.kb.composite_predicate_heuristics import looks_computed_composite

        self.assertFalse(looks_computed_composite("annual_turnover", "Annual turnover in euros"))
        self.assertFalse(looks_computed_composite("balance_sheet_total", "Balance sheet total in euros"))


if __name__ == "__main__":
    unittest.main()
