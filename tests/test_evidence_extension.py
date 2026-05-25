"""Evidence-driven bounded extension for JSON IR compile loop."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from pipeline.kb.evidence_extension import (
    EvidenceExtensionConfig,
    PendingEvidenceState,
    fingerprint_validation_evidence,
    repair_hints_carry_validation_evidence,
    should_grant_evidence_extension,
)
from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.json_ir import JSONIRCompilationError
from pipeline.kb.json_ir_compile_loop import CompileLoopLimits, _build_repair_hints, compile_json_ir_structured
from pipeline.kb.json_ir_repair import JsonIRErrorKind, normalize_error_code
from pipeline.kb.validation_evidence import (
    MissingHelperEvidence,
    ValidationRepairEvidence,
    collect_validation_repair_evidence,
)

_COMPUTED_ERR = (
    "JSON_IR_SCHEMA_DESIGN_ERROR: Predicate 'exceeds_employee_threshold' (kind=observable) "
    "looks computed/composite."
)

_EFFECT_SCOPE = {"contains_effect_language": True, "question_asks_legal_effect": True}


def test_grant_extension_when_symbol_budget_and_unconsumed_evidence():
    evidence = ValidationRepairEvidence(
        computed_observable_predicate="exceeds_employee_threshold",
        computed_observable_helper_kind_hint="threshold",
        secondary_missing_helpers=[
            MissingHelperEvidence(
                helper_name="exceeds_two_consecutive",
                helper_kind_hint="consecutive",
                derives_legal_output=True,
                legal_output_predicates_in_then=["legal_effect"],
                legal_effect_context=True,
                is_secondary=True,
            )
        ],
    )
    state = PendingEvidenceState()
    state.register_evidence(
        path="/tmp/validation_evidence.json",
        evidence=evidence,
        error_code="computed_observable_unsafe",
        repair_route=JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED.value,
    )
    grant, reason = should_grant_evidence_extension(
        config=EvidenceExtensionConfig(enabled=True, max_calls=1),
        extension_calls_used=0,
        evidence_state=state,
        validation_evidence=evidence,
        symbol_version=3,
        max_symbol_versions=3,
        total_llm_calls=4,
        max_total_kb_llm_calls=7,
    )
    assert grant is True
    assert "symbol_version_budget" in reason


def test_no_extension_when_evidence_already_consumed():
    evidence = ValidationRepairEvidence(
        computed_observable_predicate="exceeds_employee_threshold",
        secondary_missing_helpers=[
            MissingHelperEvidence(
                helper_name="h",
                helper_kind_hint="threshold",
                legal_effect_context=True,
                is_secondary=True,
            )
        ],
    )
    state = PendingEvidenceState()
    state.register_evidence(
        path="/tmp/e.json",
        evidence=evidence,
        error_code="computed_observable_unsafe",
        repair_route=JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED.value,
    )
    state.mark_consumed()
    grant, _ = should_grant_evidence_extension(
        config=EvidenceExtensionConfig(enabled=True, max_calls=1),
        extension_calls_used=0,
        evidence_state=state,
        validation_evidence=evidence,
        symbol_version=3,
        max_symbol_versions=3,
        total_llm_calls=4,
        max_total_kb_llm_calls=7,
    )
    assert grant is False


def test_extension_limit_enforced():
    evidence = ValidationRepairEvidence(
        secondary_missing_helpers=[
            MissingHelperEvidence(
                helper_name="h",
                helper_kind_hint="consecutive",
                legal_effect_context=True,
                is_secondary=True,
            )
        ],
    )
    state = PendingEvidenceState()
    state.register_evidence(
        path="/tmp/e.json",
        evidence=evidence,
        error_code="computed_observable_unsafe",
        repair_route=JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED.value,
    )
    grant, reason = should_grant_evidence_extension(
        config=EvidenceExtensionConfig(enabled=True, max_calls=1),
        extension_calls_used=1,
        evidence_state=state,
        validation_evidence=evidence,
        symbol_version=3,
        max_symbol_versions=3,
        total_llm_calls=4,
        max_total_kb_llm_calls=7,
    )
    assert grant is False
    assert reason == "extension_limit_reached"


def test_no_extension_for_threshold_cardinality_without_secondary():
    evidence = ValidationRepairEvidence(cardinality_violations=["rules[0] at-most-one"])
    state = PendingEvidenceState()
    state.register_evidence(
        path="/tmp/e.json",
        evidence=evidence,
        error_code="threshold_cardinality_or_singleton",
        repair_route=JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED.value,
    )
    grant, reason = should_grant_evidence_extension(
        config=EvidenceExtensionConfig(enabled=True, max_calls=1),
        extension_calls_used=0,
        evidence_state=state,
        validation_evidence=evidence,
        symbol_version=3,
        max_symbol_versions=3,
        total_llm_calls=6,
        max_total_kb_llm_calls=7,
    )
    assert grant is False
    assert reason in (
        "threshold_cardinality_without_new_secondary_evidence",
        "no_actionable_evidence_payload",
    )


def test_repair_hints_mark_validation_evidence_carried():
    evidence = ValidationRepairEvidence(
        computed_observable_predicate="exceeds_employee_threshold",
        secondary_missing_helpers=[
            MissingHelperEvidence(
                helper_name="h",
                helper_kind_hint="consecutive",
                legal_effect_context=True,
                is_secondary=True,
            )
        ],
    )
    hints = _build_repair_hints(
        _COMPUTED_ERR,
        "",
        error_code="computed_observable_unsafe",
        layer="symbols",
        scope_metadata=_EFFECT_SCOPE,
        secondary_diagnostics=evidence.format_secondary_diagnostics(),
        validation_evidence=evidence,
    )
    assert repair_hints_carry_validation_evidence(hints, validation_evidence=evidence)


def test_mocked_loop_grants_extra_symbol_repair_for_late_evidence(monkeypatch):
    monkeypatch.setattr(
        "pipeline.kb.json_ir_compile_loop.repair_hints_carry_validation_evidence",
        lambda *args, **kwargs: False,
    )
    symbol_calls: list[int] = []

    def symbols_llm(_src, repair=False, **kwargs):
        symbol_calls.append(1)
        if len(symbol_calls) == 1:
            return {
                "types": ["Company"],
                "predicates": [
                    {
                        "name": "exceeds_employee_threshold",
                        "kind": "observable",
                        "args": ["Company"],
                        "returns": "Bool",
                    },
                    {
                        "name": "legal_effect",
                        "kind": "derived",
                        "args": ["Company"],
                        "returns": "Bool",
                        "legal_output": True,
                        "output_category": "legal_effect",
                    },
                    {
                        "name": "exceeds_two_consecutive",
                        "kind": "helper",
                        "args": ["Company"],
                        "returns": "Bool",
                    },
                ],
                "functions": [],
            }, "{}"
        return {
            "types": ["Company"],
            "predicates": [
                {
                    "name": "exceeds_employee_threshold",
                    "kind": "helper",
                    "args": ["Company"],
                    "returns": "Bool",
                },
                    {
                        "name": "legal_effect",
                        "kind": "derived",
                        "args": ["Company"],
                        "returns": "Bool",
                        "legal_output": True,
                        "output_category": "legal_effect",
                    },
                    {
                        "name": "exceeds_two_consecutive",
                        "kind": "helper",
                        "args": ["Company"],
                        "returns": "Bool",
                    },
                ],
                "functions": [],
            }, "{}"

    limits = CompileLoopLimits(
        max_symbol_versions=1,
        max_rules_attempts_per_symbol_version=1,
        max_total_kb_llm_calls=5,
        repeated_error_limit=3,
        max_rules_before_symbol_escalation=2,
    )

    def rules_llm(_src, _st, **kwargs):
        return {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}],
                    "if": [
                        {"pred": "exceeds_employee_threshold", "args": ["c"]},
                        {"pred": "exceeds_two_consecutive", "args": ["c"]},
                    ],
                    "then": [{"pred": "legal_effect", "args": ["c"]}],
                    "operator": "implies",
                }
            ]
        }, "[]"

    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(LawCompilationError):
            compile_json_ir_structured(
                "The legal consequences apply from the following financial year.",
                symbols_llm=symbols_llm,
                rules_llm=rules_llm,
                repair_context_fn=lambda **kw: "",
                limits=limits,
                scope_metadata=_EFFECT_SCOPE,
                question_text="When do consequences apply?",
                artifact_dir=tmp,
            )
        hist = json.loads((Path(tmp) / "repair_history.json").read_text(encoding="utf-8"))
        summary = hist["summary"]

    assert len(symbol_calls) >= 2
    assert summary.get("evidence_extension_used") is True
    assert (summary.get("evidence_extension_calls") or 0) >= 1
    assert any(e.get("action") == "evidence_extension_granted" for e in hist["events"])


def test_repair_history_records_extension_metadata(monkeypatch):
    monkeypatch.setattr(
        "pipeline.kb.json_ir_compile_loop.repair_hints_carry_validation_evidence",
        lambda *args, **kwargs: False,
    )
    symbol_calls: list[int] = []

    def symbols_llm(_src, repair=False, **kwargs):
        symbol_calls.append(1)
        if len(symbol_calls) == 1:
            return {
                "types": ["Company"],
                "predicates": [
                    {
                        "name": "exceeds_employee_threshold",
                        "kind": "observable",
                        "args": ["Company"],
                        "returns": "Bool",
                    },
                    {
                        "name": "legal_effect",
                        "kind": "derived",
                        "args": ["Company"],
                        "returns": "Bool",
                        "legal_output": True,
                        "output_category": "legal_effect",
                    },
                    {
                        "name": "exceeds_two_consecutive",
                        "kind": "helper",
                        "args": ["Company"],
                        "returns": "Bool",
                    },
                ],
                "functions": [],
            }, "{}"
        return {
            "types": ["Company"],
            "predicates": [
                {
                    "name": "exceeds_employee_threshold",
                    "kind": "helper",
                    "args": ["Company"],
                    "returns": "Bool",
                },
                {
                    "name": "legal_effect",
                    "kind": "derived",
                    "args": ["Company"],
                    "returns": "Bool",
                    "legal_output": True,
                    "output_category": "legal_effect",
                },
                {
                    "name": "exceeds_two_consecutive",
                    "kind": "helper",
                    "args": ["Company"],
                    "returns": "Bool",
                },
            ],
            "functions": [],
        }, "{}"

    def rules_llm(_src, _st, **kwargs):
        return {
            "rules": [
                {
                    "forall": [{"var": "c", "type": "Company"}],
                    "if": [
                        {"pred": "exceeds_employee_threshold", "args": ["c"]},
                        {"pred": "exceeds_two_consecutive", "args": ["c"]},
                    ],
                    "then": [{"pred": "legal_effect", "args": ["c"]}],
                    "operator": "implies",
                }
            ]
        }, "[]"

    limits = CompileLoopLimits(
        max_symbol_versions=1,
        max_rules_attempts_per_symbol_version=1,
        max_total_kb_llm_calls=5,
        repeated_error_limit=3,
        max_rules_before_symbol_escalation=2,
    )

    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(LawCompilationError):
            compile_json_ir_structured(
                "The legal consequences apply from the following financial year.",
                symbols_llm=symbols_llm,
                rules_llm=rules_llm,
                repair_context_fn=lambda **kw: "",
                limits=limits,
                scope_metadata=_EFFECT_SCOPE,
                question_text="When do consequences apply?",
                artifact_dir=tmp,
            )
        summary = json.loads((Path(tmp) / "repair_summary.json").read_text(encoding="utf-8"))

    assert summary.get("evidence_extension_used") is True
    assert summary.get("evidence_consumed_by_repair") is False
    assert len(symbol_calls) >= 2


def test_fingerprint_stable():
    ev = ValidationRepairEvidence(
        computed_observable_predicate="x",
        secondary_missing_helpers=[
            MissingHelperEvidence(helper_name="h", helper_kind_hint="threshold")
        ],
    )
    assert fingerprint_validation_evidence(ev) == fingerprint_validation_evidence(ev)
