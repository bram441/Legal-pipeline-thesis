"""Audit: computed_observable_unsafe false-positive reduction."""

from __future__ import annotations

import pytest

from pipeline.kb.composite_predicate_heuristics import (
    classify_computed_observable_subject,
    looks_computed_composite,
    looks_directly_observable_factual,
    looks_threshold_counting_composite,
)
from pipeline.kb.json_ir import JSONIRCompilationError, SymbolDecl, compile_validate_json_ir
from pipeline.kb.json_ir import _validate_observable_composite_symbol_declarations


def _company_kb(*, predicates, rules):
    return {
        "types": ["Person"],
        "predicates": predicates,
        "functions": [],
        "rules": rules,
    }


def _rule_not(pred: str):
    return {
        "forall": [{"var": "p", "type": "Person"}],
        "if": [{"not": {"pred": pred, "args": ["p"]}}],
        "then": [{"pred": "some_effect", "args": ["p"]}],
        "operator": "implies",
    }


class TestComputedObservableHeuristics:
    def test_has_valid_passport_not_computed(self):
        assert looks_directly_observable_factual("has_valid_passport")
        assert not looks_computed_composite("has_valid_passport")

    def test_possesses_valid_travel_document_not_computed(self):
        assert looks_directly_observable_factual("possesses_valid_travel_document")
        assert not looks_computed_composite("possesses_valid_travel_document")

    def test_failed_to_comply_can_be_factual(self):
        assert looks_directly_observable_factual("failed_to_comply_with_measure")
        assert not looks_computed_composite("failed_to_comply_with_measure")

    def test_stated_unwillingness_factual(self):
        assert looks_directly_observable_factual("stated_unwillingness_to_comply_with_measure")
        assert not looks_computed_composite("stated_unwillingness_to_comply_with_measure")

    def test_threshold_still_computed(self):
        assert looks_threshold_counting_composite("exceeds_employee_threshold")
        assert looks_computed_composite("exceeds_employee_threshold")

    def test_consolidation_eliminations_still_computed(self):
        assert looks_computed_composite("consolidation_eliminations_carried_out")

    def test_legal_output_still_computed(self):
        assert looks_computed_composite("legal_consequence_applies")
        assert classify_computed_observable_subject("legal_consequence_applies") == "legal_conclusion_computed"


class TestComputedObservableValidation:
    def test_passport_observable_declaration_allowed(self):
        decl = SymbolDecl(
            name="has_valid_passport",
            args=["Person"],
            returns="Bool",
            kind="observable",
            directly_observable=True,
        )
        _validate_observable_composite_symbol_declarations([decl])

    def test_passport_negated_in_rule_allowed(self):
        ir = _company_kb(
            predicates=[
                {
                    "name": "has_valid_passport",
                    "kind": "observable",
                    "args": ["Person"],
                    "returns": "Bool",
                    "directly_observable": True,
                },
                {
                    "name": "some_effect",
                    "kind": "derived",
                    "args": ["Person"],
                    "returns": "Bool",
                },
            ],
            rules=[_rule_not("has_valid_passport")],
        )
        compile_validate_json_ir(ir)

    def test_consolidation_eliminations_still_rejected(self):
        decl = SymbolDecl(
            name="consolidation_eliminations_carried_out",
            args=["Person"],
            returns="Bool",
            kind="observable",
        )
        with pytest.raises(JSONIRCompilationError):
            _validate_observable_composite_symbol_declarations([decl])

    def test_legal_consequence_observable_still_rejected(self):
        decl = SymbolDecl(
            name="legal_consequence_applies",
            args=["Person"],
            returns="Bool",
            kind="observable",
        )
        with pytest.raises(JSONIRCompilationError):
            _validate_observable_composite_symbol_declarations([decl])

    def test_exceeds_threshold_still_rejected(self):
        decl = SymbolDecl(
            name="exceeds_employee_threshold",
            args=["Person"],
            returns="Bool",
            kind="observable",
        )
        with pytest.raises(JSONIRCompilationError):
            _validate_observable_composite_symbol_declarations([decl])
