"""Tests for suspicious self-relation validation (Task A)."""

from __future__ import annotations

import unittest

from pipeline.kb.json_ir import JSONIRCompilationError, SymbolDecl, validate_combined_json_ir_schema
from pipeline.kb.self_relation_validation import (
    is_suspicious_self_relation,
    self_relation_repair_hint,
)


def _self_relation_ir(pred: str) -> tuple[dict, list[SymbolDecl]]:
    preds = [
        SymbolDecl(name=pred, args=["Company", "Company"], returns="Bool", kind="observable"),
        SymbolDecl(name="legal_person", args=["Company"], returns="Bool", kind="observable"),
        SymbolDecl(name="small_company", args=["Company"], returns="Bool", kind="derived"),
    ]
    ir = {
        "rules": [
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [{"pred": pred, "args": ["c", "c"]}, {"pred": "legal_person", "args": ["c"]}],
                "then": [{"pred": "small_company", "args": ["c"]}],
                "operator": "implies",
            }
        ]
    }
    return ir, preds


class TestSelfRelationValidation(unittest.TestCase):
    def test_affiliated_with_self_rejected(self):
        self.assertTrue(
            is_suspicious_self_relation("affiliated_with", "c", "c", description="Affiliation between companies")
        )

    def test_forms_consortium_with_self_rejected(self):
        self.assertTrue(is_suspicious_self_relation("forms_consortium_with", "c", "c"))

    def test_reflexive_metadata_allowed(self):
        self.assertFalse(
            is_suspicious_self_relation(
                "same_economic_group",
                "c",
                "c",
                reflexive_allowed=True,
            )
        )

    def test_unary_unaffected(self):
        self.assertFalse(is_suspicious_self_relation("legal_person", "c", "c"))

    def test_normal_binary_allowed(self):
        self.assertFalse(is_suspicious_self_relation("affiliated_with", "c", "other"))

    def test_repair_hint_mentions_existential(self):
        hint = self_relation_repair_hint()
        self.assertIn("exists", hint.lower())
        self.assertIn("other", hint.lower())

    def test_schema_rejects_affiliated_with_self(self):
        ir, preds = _self_relation_ir("affiliated_with")
        with self.assertRaises(JSONIRCompilationError) as ctx:
            validate_combined_json_ir_schema(ir, preds, [])
        self.assertIn("suspicious self-relation", str(ctx.exception).lower())

    def test_schema_allows_reflexive_metadata(self):
        ir, preds = _self_relation_ir("same_group")
        preds[0] = SymbolDecl(
            name="same_group",
            args=["Company", "Company"],
            returns="Bool",
            kind="observable",
            reflexive_allowed=True,
        )
        ir["rules"][0]["if"][0]["pred"] = "same_group"
        validate_combined_json_ir_schema(ir, preds, [])


if __name__ == "__main__":
    unittest.main()
