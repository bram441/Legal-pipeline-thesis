"""Bounded evidence-driven extension for JSON IR structured compile loop."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field

from pipeline.kb.json_ir_repair import JsonIRErrorKind, normalize_error_code
from pipeline.kb.validation_evidence import ValidationRepairEvidence

_EVIDENCE_EXTENSION_ERROR_CODES: frozenset[str] = frozenset(
    {
        "computed_observable_unsafe",
        "missing_legal_effect_output",
        "status_as_type",
        "invalid_signature",
        "unknown_symbol",
    }
)


@dataclass(frozen=True)
class EvidenceExtensionConfig:
    enabled: bool = True
    max_calls: int = 1


def evidence_extension_config_from_env() -> EvidenceExtensionConfig:
    from pipeline.config import json_ir_config

    cfg = json_ir_config()
    return EvidenceExtensionConfig(
        enabled=bool(cfg.allow_evidence_extension),
        max_calls=max(0, int(cfg.max_evidence_extension_calls)),
    )


@dataclass
class PendingEvidenceState:
    validation_evidence_path: str | None = None
    validation_evidence_fingerprint: str | None = None
    evidence_consumed_by_repair: bool = False
    last_error_code: str | None = None
    last_repair_route: str | None = None

    def register_evidence(
        self,
        *,
        path: str | None,
        evidence: ValidationRepairEvidence | None,
        error_code: str | None,
        repair_route: str | None,
    ) -> None:
        new_fp = fingerprint_validation_evidence(evidence)
        if new_fp != self.validation_evidence_fingerprint:
            self.evidence_consumed_by_repair = False
        self.validation_evidence_path = path
        self.validation_evidence_fingerprint = new_fp
        self.last_error_code = error_code
        self.last_repair_route = repair_route

    def mark_consumed(self) -> None:
        self.evidence_consumed_by_repair = True


def fingerprint_validation_evidence(evidence: ValidationRepairEvidence | None) -> str | None:
    if evidence is None:
        return None
    payload = {
        "missing_helper": evidence.missing_helper.to_dict() if evidence.missing_helper else None,
        "secondary_missing_helpers": [h.to_dict() for h in evidence.secondary_missing_helpers],
        "computed_observable_predicate": evidence.computed_observable_predicate,
        "computed_observable_helper_kind_hint": evidence.computed_observable_helper_kind_hint,
        "cardinality_violations": evidence.cardinality_violations,
        "numeric_provenance_issues": evidence.numeric_provenance_issues,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def repair_hints_carry_validation_evidence(
    hints: str,
    *,
    validation_evidence: ValidationRepairEvidence | None,
) -> bool:
    if not hints.strip() or validation_evidence is None:
        return False
    if "SECONDARY VALIDATION DIAGNOSTICS" in hints:
        return True
    if validation_evidence.secondary_missing_helpers and (
        "LEGAL-EFFECT COMPUTED HELPER" in hints
        or "MISSING HELPER FOR LEGAL-EFFECT RULE" in hints
    ):
        return True
    if validation_evidence.computed_observable_predicate and "LEGAL-EFFECT COMPUTED HELPER" in hints:
        return True
    return False


def _has_actionable_secondary_evidence(evidence: ValidationRepairEvidence | None) -> bool:
    if evidence is None:
        return False
    if evidence.secondary_missing_helpers:
        return True
    if evidence.missing_helper is not None:
        return True
    if evidence.computed_observable_predicate:
        return True
    return False


def should_grant_evidence_extension(
    *,
    config: EvidenceExtensionConfig,
    extension_calls_used: int,
    evidence_state: PendingEvidenceState,
    validation_evidence: ValidationRepairEvidence | None,
    symbol_version: int,
    max_symbol_versions: int,
    total_llm_calls: int,
    max_total_kb_llm_calls: int,
) -> tuple[bool, str]:
    """Return (grant, reason)."""
    if not config.enabled:
        return False, "extension_disabled"
    if extension_calls_used >= config.max_calls:
        return False, "extension_limit_reached"
    if not evidence_state.validation_evidence_fingerprint:
        return False, "no_validation_evidence"
    if evidence_state.evidence_consumed_by_repair:
        return False, "evidence_already_consumed"
    if evidence_state.last_repair_route != JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED.value:
        return False, "not_symbols_repair_route"
    if not _has_actionable_secondary_evidence(validation_evidence):
        return False, "no_actionable_evidence_payload"

    code = evidence_state.last_error_code or ""
    if code == "threshold_cardinality_or_singleton":
        if not (validation_evidence and validation_evidence.secondary_missing_helpers):
            return False, "threshold_cardinality_without_new_secondary_evidence"
    elif code not in _EVIDENCE_EXTENSION_ERROR_CODES:
        if not (validation_evidence and validation_evidence.secondary_missing_helpers):
            return False, "error_code_not_eligible"

    symbol_budget_exhausted = symbol_version >= max_symbol_versions and max_symbol_versions > 0
    llm_near_limit = total_llm_calls >= max(0, max_total_kb_llm_calls - 1)
    if not symbol_budget_exhausted and not llm_near_limit:
        return False, "not_near_loop_end"

    if symbol_budget_exhausted:
        return True, "symbol_version_budget_with_unconsumed_evidence"
    if llm_near_limit:
        return True, "llm_budget_within_one_call_with_unconsumed_evidence"
    return False, "not_eligible"
