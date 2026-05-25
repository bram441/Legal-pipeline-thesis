"""Structural progress detection for missing helper predicate/function repair stalls."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from pipeline.kb.json_ir import (
    _helper_functions_defined_in_then,
    _predicates_defined_in_then,
)


@dataclass
class HelperRepairSnapshot:
    helper_name: str
    helper_kind: str = "predicate"
    defined_in_then: bool = False
    definition_rule_indices: list[int] | None = None
    rules_fingerprint: str = ""
    primary_error_path: str | None = None


@dataclass(frozen=True)
class HelperProgressVerdict:
    progress_detected: bool
    progress_reason: str
    previous_error_path: str | None
    current_error_path: str | None
    helper_defined_in_then: bool
    helper_kind: str = "predicate"


def rules_fingerprint(rules: list | None) -> str:
    if not rules:
        return ""
    payload = json.dumps(rules, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _helper_defined(
    rules: list,
    helper_name: str,
    *,
    helper_kind: str,
    fun_kinds: dict[str, str] | None = None,
) -> tuple[bool, list[int]]:
    if helper_kind == "function":
        defined, by_rule = _helper_functions_defined_in_then(rules, fun_kinds or {})
        return helper_name in defined, list(by_rule.get(helper_name, []))
    return helper_name in _predicates_defined_in_then(rules), []


def build_helper_repair_snapshot(
    ir: dict,
    *,
    helper_name: str,
    helper_kind: str = "predicate",
    fun_kinds: dict[str, str] | None = None,
    primary_error_path: str | None = None,
) -> HelperRepairSnapshot:
    rules = ir.get("rules") or []
    defined, rule_idxs = _helper_defined(
        rules, helper_name, helper_kind=helper_kind, fun_kinds=fun_kinds
    )
    return HelperRepairSnapshot(
        helper_name=helper_name,
        helper_kind=helper_kind,
        defined_in_then=defined,
        definition_rule_indices=rule_idxs,
        rules_fingerprint=rules_fingerprint(rules),
        primary_error_path=primary_error_path,
    )


def detect_helper_definition_progress(
    previous: HelperRepairSnapshot | None,
    current: HelperRepairSnapshot,
) -> HelperProgressVerdict:
    prev_path = previous.primary_error_path if previous else None
    cur_path = current.primary_error_path
    kind = current.helper_kind

    if previous is None:
        return HelperProgressVerdict(
            progress_detected=True,
            progress_reason="initial_helper_snapshot",
            previous_error_path=prev_path,
            current_error_path=cur_path,
            helper_defined_in_then=current.defined_in_then,
            helper_kind=kind,
        )

    if current.defined_in_then and not previous.defined_in_then:
        reason = (
            "helper_function_equality_in_then"
            if kind == "function"
            else "helper_now_defined_in_then"
        )
        return HelperProgressVerdict(
            progress_detected=True,
            progress_reason=reason,
            previous_error_path=prev_path,
            current_error_path=cur_path,
            helper_defined_in_then=True,
            helper_kind=kind,
        )

    if previous.rules_fingerprint and current.rules_fingerprint == previous.rules_fingerprint:
        return HelperProgressVerdict(
            progress_detected=False,
            progress_reason="no_helper_definition_progress",
            previous_error_path=prev_path,
            current_error_path=cur_path,
            helper_defined_in_then=current.defined_in_then,
            helper_kind=kind,
        )

    if not current.defined_in_then:
        return HelperProgressVerdict(
            progress_detected=False,
            progress_reason="no_helper_definition_progress",
            previous_error_path=prev_path,
            current_error_path=cur_path,
            helper_defined_in_then=False,
            helper_kind=kind,
        )

    return HelperProgressVerdict(
        progress_detected=True,
        progress_reason="rules_changed_while_helper_pending",
        previous_error_path=prev_path,
        current_error_path=cur_path,
        helper_defined_in_then=current.defined_in_then,
        helper_kind=kind,
    )


def should_stall_helper_definition_repeat(
    *,
    signature_repeat_count: int,
    repeated_error_limit: int,
    progress: HelperProgressVerdict,
    rules_attempt: int,
    max_rules_attempts: int,
) -> bool:
    if signature_repeat_count < repeated_error_limit:
        return False
    if progress.progress_detected and rules_attempt < max_rules_attempts:
        return False
    return True
