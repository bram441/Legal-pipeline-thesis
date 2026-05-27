"""Validation for unsafe inverse/De Morgan negative legal-output rules."""

from __future__ import annotations

import pytest

from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir


def _ir(predicates: list[dict], rules: list[dict]) -> dict:
    return {
        "types": ["Entity"],
        "predicates": predicates,
        "functions": [],
        "rules": rules,
    }


def test_positive_rule_with_negated_helper_is_valid() -> None:
    ir = _ir(
        predicates=[
            {"name": "base_fact", "args": ["Entity"], "returns": "Bool", "kind": "observable"},
            {"name": "is_disqualified", "args": ["Entity"], "returns": "Bool", "kind": "helper"},
            {
                "name": "is_classification",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "derived",
                "output_category": "classification",
            },
        ],
        rules=[
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"pred": "base_fact", "args": ["x"]}],
                "then": [{"pred": "is_disqualified", "args": ["x"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [
                    {"pred": "base_fact", "args": ["x"]},
                    {"not": {"pred": "is_disqualified", "args": ["x"]}},
                ],
                "then": [{"pred": "is_classification", "args": ["x"]}],
                "operator": "implies",
            }
        ],
    )
    compile_validate_json_ir(ir)


def test_negative_rule_from_positive_disqualifier_is_valid() -> None:
    ir = _ir(
        predicates=[
            {"name": "base_fact", "args": ["Entity"], "returns": "Bool", "kind": "observable"},
            {"name": "is_disqualifier", "args": ["Entity"], "returns": "Bool", "kind": "helper"},
            {
                "name": "is_classification",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "derived",
                "output_category": "classification",
            },
        ],
        rules=[
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"pred": "base_fact", "args": ["x"]}],
                "then": [{"pred": "is_disqualifier", "args": ["x"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"pred": "is_disqualifier", "args": ["x"]}],
                "then": [{"pred": "is_classification", "args": ["x"], "negated": True}],
                "operator": "implies",
            }
        ],
    )
    compile_validate_json_ir(ir)


def test_negative_rule_from_not_observable_prerequisite_is_rejected() -> None:
    ir = _ir(
        predicates=[
            {
                "name": "is_prerequisite_status",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
            },
            {
                "name": "is_classification",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "derived",
                "output_category": "classification",
            },
        ],
        rules=[
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"not": {"pred": "is_prerequisite_status", "args": ["x"]}}],
                "then": [{"pred": "is_classification", "args": ["x"], "negated": True}],
                "operator": "implies",
            }
        ],
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir)
    msg = str(exc.value).lower()
    assert "inverse/de morgan" in msg
    assert "open-world semantics" in msg


def test_or_negative_rule_with_missing_prerequisite_branch_is_rejected() -> None:
    ir = _ir(
        predicates=[
            {
                "name": "is_prerequisite_status",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
            },
            {"name": "is_explicit_disqualifier", "args": ["Entity"], "returns": "Bool", "kind": "helper"},
            {
                "name": "is_classification",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "derived",
                "output_category": "classification",
            },
        ],
        rules=[
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"pred": "is_prerequisite_status", "args": ["x"]}],
                "then": [{"pred": "is_explicit_disqualifier", "args": ["x"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": {
                    "or": [
                        {"not": {"pred": "is_prerequisite_status", "args": ["x"]}},
                        {"pred": "is_explicit_disqualifier", "args": ["x"]},
                    ]
                },
                "then": [{"pred": "is_classification", "args": ["x"], "negated": True}],
                "operator": "implies",
            }
        ],
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir)
    assert "negating observable/background/case-input/directly-observable prerequisite" in str(
        exc.value
    )


def test_negative_rule_from_not_directly_observable_prerequisite_is_rejected() -> None:
    ir = _ir(
        predicates=[
            {
                "name": "prerequisite_fact",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
            },
            {"name": "disqualifying_condition", "args": ["Entity"], "returns": "Bool", "kind": "helper"},
            {
                "name": "legal_output",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "derived",
                "output_category": "classification",
            },
        ],
        rules=[
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"pred": "prerequisite_fact", "args": ["x"]}],
                "then": [{"pred": "disqualifying_condition", "args": ["x"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"not": {"pred": "prerequisite_fact", "args": ["x"]}}],
                "then": [{"pred": "legal_output", "args": ["x"], "negated": True}],
                "operator": "implies",
            },
        ],
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir)
    assert "open-world semantics" in str(exc.value).lower()


def test_and_negative_rule_with_negated_directly_observable_branch_is_rejected() -> None:
    ir = _ir(
        predicates=[
            {
                "name": "prerequisite_fact",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
            },
            {"name": "other_condition", "args": ["Entity"], "returns": "Bool", "kind": "helper"},
            {"name": "seed_fact", "args": ["Entity"], "returns": "Bool", "kind": "observable"},
            {
                "name": "legal_output",
                "args": ["Entity"],
                "returns": "Bool",
                "kind": "derived",
                "output_category": "classification",
            },
        ],
        rules=[
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": [{"pred": "seed_fact", "args": ["x"]}],
                "then": [{"pred": "other_condition", "args": ["x"]}],
                "operator": "implies",
            },
            {
                "forall": [{"var": "x", "type": "Entity"}],
                "if": {
                    "and": [
                        {"not": {"pred": "prerequisite_fact", "args": ["x"]}},
                        {"pred": "other_condition", "args": ["x"]},
                    ]
                },
                "then": [{"pred": "legal_output", "args": ["x"], "negated": True}],
                "operator": "implies",
            },
        ],
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir)
    assert "negating observable/background/case-input/directly-observable" in str(exc.value)
