"""JSON_IR validation: unsafe negation over undefined composite/helper predicates."""

from __future__ import annotations

import pytest

from pipeline.kb.composite_predicate_heuristics import looks_computed_composite
from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir
from pipeline.kb.json_ir_repair import (
    JsonIRErrorKind,
    RULE_DESIGN_TAG,
    SCHEMA_DESIGN_TAG,
    classify_json_ir_validation_error,
)


def _company_kb(*, predicates, functions=None, rules):
    return {
        "types": ["Company"],
        "predicates": predicates,
        "functions": functions or [],
        "rules": rules,
    }


def _implies_rule(*, if_expr, then_pred: str):
    return {
        "forall": [{"var": "c", "type": "Company"}],
        "if": if_expr if isinstance(if_expr, list) else [if_expr],
        "then": [{"pred": then_pred, "args": ["c"], "negated": False}],
        "operator": "implies",
    }


def test_heuristic_flags_exceeds_style_names() -> None:
    assert looks_computed_composite("exceeds_more_than_one_criterion", "")
    assert looks_computed_composite("meets_conditions", "threshold check")
    assert not looks_computed_composite("is_company", "entity is a company")


def test_safe_kb_with_numeric_comparison_passes() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "is_small_company",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
                "description": "Small company",
            },
        ],
        functions=[
            {
                "name": "annual_average_number_of_employees",
                "args": ["Company"],
                "returns": "Int",
                "kind": "observable",
                "description": "Headcount",
            },
        ],
        rules=[
            _implies_rule(
                if_expr={
                    "compare": {
                        "left": {"func": "annual_average_number_of_employees", "args": ["c"]},
                        "op": "=<",
                        "right": 50,
                    }
                },
                then_pred="is_small_company",
            )
        ],
    )
    compile_validate_json_ir(ir)


def test_observable_exceeds_used_negated_without_definition_fails_symbols() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "exceeds_more_than_one_criterion",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
                "description": "Exceeds more than one criterion",
            },
            {
                "name": "is_small_company",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
                "description": "Small company",
            },
        ],
        rules=[
            _implies_rule(
                if_expr={"not": {"pred": "exceeds_more_than_one_criterion", "args": ["c"]}},
                then_pred="is_small_company",
            )
        ],
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir)
    msg = str(exc.value)
    assert SCHEMA_DESIGN_TAG in msg
    assert "exceeds_more_than_one_criterion" in msg
    assert classify_json_ir_validation_error(msg) == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED


def test_helper_exceeds_threshold_negated_undefined_routes_rules() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "exceeds_threshold",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "helper",
                "description": "Exceeds numeric threshold",
            },
            {
                "name": "is_small_company",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
                "description": "Small company",
            },
        ],
        functions=[
            {
                "name": "annual_net_turnover",
                "args": ["Company"],
                "returns": "Int",
                "kind": "observable",
                "description": "Turnover value",
            },
        ],
        rules=[
            _implies_rule(
                if_expr={"not": {"pred": "exceeds_threshold", "args": ["c"]}},
                then_pred="is_small_company",
            )
        ],
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir)
    msg = str(exc.value)
    assert RULE_DESIGN_TAG in msg
    assert "exceeds_threshold" in msg
    assert "defining rule" in msg
    assert classify_json_ir_validation_error(msg) == JsonIRErrorKind.RULES_REPAIR_ONLY


def test_helper_with_defining_rule_passes() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "exceeds_threshold",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "helper",
                "description": "Exceeds threshold",
            },
            {
                "name": "is_small_company",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
                "description": "Small company",
            },
        ],
        functions=[
            {
                "name": "annual_net_turnover",
                "args": ["Company"],
                "returns": "Int",
                "kind": "observable",
                "description": "Turnover",
            },
        ],
        rules=[
            {
                "forall": [{"var": "c", "type": "Company"}],
                "if": [
                    {
                        "compare": {
                            "left": {"func": "annual_net_turnover", "args": ["c"]},
                            "op": ">",
                            "right": 1000000,
                        }
                    }
                ],
                "then": [{"pred": "exceeds_threshold", "args": ["c"]}],
                "operator": "implies",
            },
            _implies_rule(
                if_expr={"not": {"pred": "exceeds_threshold", "args": ["c"]}},
                then_pred="is_small_company",
            ),
        ],
    )
    compile_validate_json_ir(ir)


def test_directly_observable_composite_used_negated_passes() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "directly_stated_condition",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
                "description": "Case may state this composite condition directly",
                "directly_observable": True,
            },
            {
                "name": "is_small_company",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
                "description": "Small company",
            },
        ],
        rules=[
            _implies_rule(
                if_expr={"not": {"pred": "directly_stated_condition", "args": ["c"]}},
                then_pred="is_small_company",
            )
        ],
    )
    compile_validate_json_ir(ir)


def test_observable_composite_without_directly_observable_rejected() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "meets_entry_or_stay_conditions",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
                "description": "Meets entry or stay conditions",
            },
            {
                "name": "is_eligible",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
            },
        ],
        rules=[
            _implies_rule(
                if_expr={"pred": "meets_entry_or_stay_conditions", "args": ["c"]},
                then_pred="is_eligible",
            )
        ],
    )
    with pytest.raises(JSONIRCompilationError) as exc:
        compile_validate_json_ir(ir)
    assert "meets_entry_or_stay_conditions" in str(exc.value)
    assert "computed/composite" in str(exc.value).lower()


def test_directly_observable_immigration_style_predicate_accepted() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "no_residence_application_filed",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
                "directly_observable": True,
                "description": "No residence application filed",
            },
            {
                "name": "is_eligible",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
            },
        ],
        rules=[
            _implies_rule(
                if_expr={"pred": "no_residence_application_filed", "args": ["c"]},
                then_pred="is_eligible",
            )
        ],
    )
    compile_validate_json_ir(ir)


def test_directly_observable_with_legal_output_rejected() -> None:
    from pipeline.kb.json_ir import validate_json_ir_symbols

    with pytest.raises(JSONIRCompilationError) as exc:
        validate_json_ir_symbols(
            {
                "types": ["Company"],
                "predicates": [
                    {
                        "name": "meets_residence_conditions",
                        "args": ["Company"],
                        "returns": "Bool",
                        "kind": "observable",
                        "directly_observable": True,
                        "legal_output": True,
                        "output_category": "classification",
                    },
                    {
                        "name": "is_eligible",
                        "args": ["Company"],
                        "returns": "Bool",
                        "kind": "derived",
                        "legal_output": True,
                    },
                ],
                "functions": [],
            }
        )
    assert "directly_observable" in str(exc.value)
    assert "legal_output" in str(exc.value)


def test_exceeds_employee_threshold_still_rejected_without_directly_observable() -> None:
    ir = _company_kb(
        predicates=[
            {
                "name": "exceeds_employee_threshold",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
                "description": "Exceeds employee threshold",
            },
        ],
        rules=[],
    )
    with pytest.raises(JSONIRCompilationError):
        compile_validate_json_ir(ir)


def test_absent_threshold_helpers_cannot_prove_status_via_negation_pattern() -> None:
    """Validator blocks KB that would derive status solely from negating undefined threshold helper."""
    ir = _company_kb(
        predicates=[
            {
                "name": "exceeds_employee_threshold",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "observable",
                "description": "Exceeds employee threshold",
            },
            {
                "name": "is_micro_company",
                "args": ["Company"],
                "returns": "Bool",
                "kind": "derived",
                "description": "Micro company status",
            },
        ],
        functions=[
            {
                "name": "annual_average_number_of_employees",
                "args": ["Company"],
                "returns": "Int",
                "kind": "observable",
                "description": "Employees",
            },
        ],
        rules=[
            _implies_rule(
                if_expr={"not": {"pred": "exceeds_employee_threshold", "args": ["c"]}},
                then_pred="is_micro_company",
            )
        ],
    )
    with pytest.raises(JSONIRCompilationError):
        compile_validate_json_ir(ir)
