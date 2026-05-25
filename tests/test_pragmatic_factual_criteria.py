"""Pragmatic factual-criteria evaluation mode (configurable safety/coverage trade-off)."""

from __future__ import annotations

import pytest

from pipeline.config import reload_config
from pipeline.extraction.case_fact_validation import (
    case_predicate_may_be_asserted,
    case_predicate_may_be_asserted_as_factual_criteria,
)
from pipeline.kb.factual_criteria import (
    apply_pragmatic_factual_criteria_to_ir,
    is_factual_criteria_input_candidate,
    is_threshold_counting_helper_only,
    pragmatic_factual_criteria_mode_enabled,
    try_apply_pragmatic_factual_criteria_symbol_fixup,
)
from pipeline.kb.json_ir import JSONIRCompilationError, compile_validate_json_ir
from pipeline.kb.schema_environment import build_schema_environment


def _enable_pragmatic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALUATION_PRAGMATIC_FACTUAL_CRITERIA_MODE", "true")
    reload_config()


def _disable_pragmatic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVALUATION_PRAGMATIC_FACTUAL_CRITERIA_MODE", "false")
    reload_config()


def _person_kb(*, predicates, rules):
    return {
        "types": ["Person"],
        "predicates": predicates,
        "functions": [],
        "rules": rules,
    }


def _rule_if(pred: str, *, then_pred: str = "some_effect"):
    return {
        "forall": [{"var": "p", "type": "Person"}],
        "if": [{"pred": pred, "args": ["p"]}],
        "then": [{"pred": then_pred, "args": ["p"]}],
        "operator": "implies",
    }


@pytest.fixture(autouse=True)
def _reset_config(monkeypatch: pytest.MonkeyPatch):
    _disable_pragmatic(monkeypatch)
    yield
    _disable_pragmatic(monkeypatch)


class TestFactualCriteriaClassifier:
    def test_meets_entry_conditions_is_candidate(self):
        assert is_factual_criteria_input_candidate({"name": "meets_entry_conditions", "kind": "helper"})

    def test_criterion_false_documents_is_candidate(self):
        assert is_factual_criteria_input_candidate(
            {"name": "criterion_used_false_information_or_documents", "kind": "helper"}
        )

    def test_has_valid_passport_is_candidate(self):
        assert is_factual_criteria_input_candidate({"name": "has_valid_passport", "kind": "observable"})

    def test_legal_consequence_blocked(self):
        assert not is_factual_criteria_input_candidate(
            {
                "name": "legal_consequence_applies",
                "kind": "derived",
                "legal_output": True,
                "output_category": "legal_effect",
            }
        )

    def test_query_predicate_blocked(self):
        assert not is_factual_criteria_input_candidate(
            {"name": "meets_entry_conditions", "kind": "helper"},
            query_predicate="meets_entry_conditions",
        )

    def test_micro_company_classification_blocked(self):
        assert not is_factual_criteria_input_candidate(
            {
                "name": "micro_company",
                "kind": "derived",
                "output_category": "classification",
            },
            query_predicate="micro_company",
        )

    def test_threshold_counting_not_pragmatic_allowlist(self):
        assert is_threshold_counting_helper_only("exceeds_more_than_one_criterion")
        assert not is_factual_criteria_input_candidate({"name": "exceeds_more_than_one_criterion", "kind": "helper"})


class TestFloatingHelperValidation:
    def test_meets_entry_conditions_allowed_in_pragmatic_mode(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        ir = _person_kb(
            predicates=[
                {
                    "name": "meets_entry_conditions",
                    "kind": "helper",
                    "args": ["Person"],
                    "returns": "Bool",
                },
                {
                    "name": "some_effect",
                    "kind": "derived",
                    "args": ["Person"],
                    "returns": "Bool",
                },
            ],
            rules=[_rule_if("meets_entry_conditions")],
        )
        apply_pragmatic_factual_criteria_to_ir(ir)
        compile_validate_json_ir(ir)

    def test_meets_entry_conditions_blocked_in_strict_mode(self, monkeypatch: pytest.MonkeyPatch):
        assert not pragmatic_factual_criteria_mode_enabled()
        ir = _person_kb(
            predicates=[
                {
                    "name": "meets_entry_conditions",
                    "kind": "helper",
                    "args": ["Person"],
                    "returns": "Bool",
                },
                {
                    "name": "some_effect",
                    "kind": "derived",
                    "args": ["Person"],
                    "returns": "Bool",
                },
            ],
            rules=[_rule_if("meets_entry_conditions")],
        )
        with pytest.raises(JSONIRCompilationError):
            compile_validate_json_ir(ir)

    def test_ordinary_undefined_helper_still_fails_in_pragmatic_mode(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        ir = _person_kb(
            predicates=[
                {
                    "name": "internal_aggregate_flag",
                    "kind": "helper",
                    "args": ["Person"],
                    "returns": "Bool",
                },
                {
                    "name": "some_effect",
                    "kind": "derived",
                    "args": ["Person"],
                    "returns": "Bool",
                },
            ],
            rules=[_rule_if("internal_aggregate_flag")],
        )
        with pytest.raises(JSONIRCompilationError):
            compile_validate_json_ir(ir)

    def test_missing_helper_fixup_reclassifies_symbol(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        st = {
            "types": ["Person"],
            "predicates": [
                {
                    "name": "meets_entry_conditions",
                    "kind": "helper",
                    "args": ["Person"],
                    "returns": "Bool",
                },
            ],
            "functions": [],
        }
        assert try_apply_pragmatic_factual_criteria_symbol_fixup(st, "meets_entry_conditions")
        pred = st["predicates"][0]
        assert pred["kind"] == "observable"
        assert pred["factual_criteria_input"] is True


class TestCaseAssertionPolicy:
    def test_criterion_allowed_with_matching_evidence(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        case_text = "The applicant used false information or documents in the request."
        sig = {
            "name": "criterion_used_false_information_or_documents",
            "kind": "observable",
            "factual_criteria_input": True,
            "args": ["Person"],
            "returns": "Bool",
        }
        allowed, code, _ = case_predicate_may_be_asserted_as_factual_criteria(
            sig,
            case_text=case_text,
            evidence_text="used false information or documents",
        )
        assert allowed and code is None

    def test_has_valid_passport_case_input(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        case_text = "Anna has a valid passport."
        sig = {
            "name": "has_valid_passport",
            "kind": "observable",
            "directly_observable": True,
            "factual_criteria_input": True,
            "args": ["Person"],
            "returns": "Bool",
        }
        allowed, _ = case_predicate_may_be_asserted(sig, case_text=case_text)
        assert allowed

    def test_legal_consequence_blocked_as_case_fact(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        sig = {
            "name": "legal_consequence_applies",
            "kind": "derived",
            "legal_output": True,
            "output_category": "legal_effect",
            "args": ["Person"],
            "returns": "Bool",
        }
        allowed, code = case_predicate_may_be_asserted(sig, case_text="legal consequence applies")
        assert not allowed
        assert code == "legal_output"

    def test_query_predicate_blocked(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        sig = {
            "name": "meets_stay_conditions",
            "kind": "observable",
            "factual_criteria_input": True,
            "args": ["Person"],
            "returns": "Bool",
        }
        allowed, code = case_predicate_may_be_asserted(
            sig,
            case_text="meets stay conditions",
            query_predicate="meets_stay_conditions",
        )
        assert not allowed
        assert code == "query_predicate"

    def test_evidence_must_match_case_text(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        sig = {
            "name": "criterion_used_false_information_or_documents",
            "kind": "observable",
            "factual_criteria_input": True,
            "args": ["Person"],
            "returns": "Bool",
        }
        allowed, code, _ = case_predicate_may_be_asserted_as_factual_criteria(
            sig,
            case_text="Nothing relevant here.",
            evidence_text="invented phrase not in case",
        )
        assert not allowed
        assert code == "unsupported_by_case_text"

    def test_no_invented_numeric_values_in_case(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        from pipeline.extraction.json_ir import ExtractionIRValidationError, normalize_case_ir

        kb = {
            "types": ["Company"],
            "predicates": [],
            "functions": [
                {
                    "name": "annual_average_employees",
                    "kind": "observable",
                    "args": ["Company"],
                    "returns": "Int",
                },
            ],
        }
        case_ir = {
            "entities": {"Company": ["c1"]},
            "value_assertions": [
                {
                    "function": "annual_average_employees",
                    "args": ["c1"],
                    "value": 999,
                },
            ],
        }
        with pytest.raises(ExtractionIRValidationError, match="cannot invent numeric"):
            normalize_case_ir(
                case_ir,
                kb,
                case_text="No employee numbers mentioned.",
            )


class TestSchemaEnvironment:
    def test_factual_criteria_in_assertable_symbols(self, monkeypatch: pytest.MonkeyPatch):
        _enable_pragmatic(monkeypatch)
        kb = {
            "types": ["Person"],
            "predicates": [
                {
                    "name": "has_valid_passport",
                    "kind": "observable",
                    "directly_observable": True,
                    "factual_criteria_input": True,
                    "args": ["Person"],
                    "returns": "Bool",
                },
            ],
            "functions": [],
        }
        env = build_schema_environment(kb)
        assert "has_valid_passport" in (env.get("assertable_case_symbols") or {}).get("predicates", [])
        assert "has_valid_passport" in env.get("factual_criteria_input_predicates", [])
