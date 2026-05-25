"""
Structured two-level JSON IR KB compile loop (symbol versions × rules attempts).
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.json_ir import JSONIRCompilationError, render_json_ir_to_fo_and_schema, validate_json_ir_symbols
from pipeline.kb.json_ir_repair import (
    JsonIRErrorKind,
    classify_json_ir_validation_error,
    format_symbol_repair_error,
    is_symbol_stage_repairable_error,
    normalize_error_code,
    normalize_error_signature,
)
from pipeline.kb.repair_cards import format_repair_card
from pipeline.kb.repair_history import RepairEvent, RepairHistory
from pipeline.kb.exclusion_repair_hints import build_missing_exclusion_repair_supplement
from pipeline.kb.threshold_exclusion_scaffold import (
    build_threshold_exclusion_repair_scaffold,
    build_threshold_helper_pairwise_scaffold,
)
from pipeline.kb.predicate_function_repair_hints import build_predicate_function_misuse_supplement
from pipeline.kb.threshold_numeric_helper_scaffold import (
    build_numeric_threshold_helper_scaffold,
    looks_like_case_value_function,
    looks_like_threshold_helper_function,
)
from pipeline.kb.composite_temporal_threshold_repair_hints import (
    build_composite_temporal_threshold_supplement,
    qualifies_for_composite_temporal_threshold_card,
)
from pipeline.kb.temporal_support_repair_hints import (
    build_missing_temporal_support_symbol_supplement,
)
from pipeline.kb.legal_effect_helper_repair_hints import (
    build_legal_effect_computed_helper_supplement,
    build_missing_legal_effect_helper_supplement,
    legal_effect_rules_repair_context,
)
from pipeline.kb.legal_effect_repair_hints import (
    build_missing_legal_effect_repair_supplement,
    parse_symbol_table_from_repair_context,
)
from pipeline.kb.validation_evidence import MissingHelperEvidence, ValidationRepairEvidence
from pipeline.kb.repair_hints import build_json_ir_compile_hints, build_machine_repair_hints
from pipeline.kb.threshold_repair_progress import (
    ThresholdRepairSnapshot,
    build_threshold_repair_snapshot,
    detect_threshold_cardinality_progress,
    should_stall_threshold_cardinality_repeat,
)
from pipeline.kb.helper_repair_progress import (
    HelperRepairSnapshot,
    build_helper_repair_snapshot,
    detect_helper_definition_progress,
    should_stall_helper_definition_repeat,
)
from pipeline.kb.evidence_extension import (
    evidence_extension_config_from_env,
    repair_hints_carry_validation_evidence,
    should_grant_evidence_extension,
)
from pipeline.kb.evidence_extension import PendingEvidenceState as EvidenceTrackingState
from pipeline.kb.validation_evidence import (
    collect_validation_repair_evidence,
    extract_error_path_from_message,
)


@dataclass(frozen=True)
class CompileLoopLimits:
    max_symbol_versions: int
    max_rules_attempts_per_symbol_version: int
    max_total_kb_llm_calls: int
    repeated_error_limit: int
    max_rules_before_symbol_escalation: int


def compile_loop_limits_from_env() -> CompileLoopLimits:
    from pipeline.config import json_ir_config

    cfg = json_ir_config()
    return CompileLoopLimits(
        max_symbol_versions=cfg.max_symbol_versions,
        max_rules_attempts_per_symbol_version=cfg.max_rules_attempts_per_symbol_version,
        max_total_kb_llm_calls=cfg.max_kb_llm_calls,
        repeated_error_limit=cfg.repeated_error_limit,
        max_rules_before_symbol_escalation=cfg.max_rules_before_symbol_escalation,
    )


SymbolsLLM = Callable[..., tuple[dict, str]]
RulesLLM = Callable[..., tuple[dict, str]]
ArtifactWriter = Callable[[Path | None, int, int, int, str, str], None]


def _artifact_subdir(artifact_dir: Path | None, symbol_version: int, rules_attempt: int) -> Path | None:
    if artifact_dir is None:
        return None
    if rules_attempt > 0:
        sub = artifact_dir / ("symbol_v%02d" % symbol_version) / ("rules_a%02d" % rules_attempt)
    else:
        sub = artifact_dir / ("symbol_v%02d" % symbol_version)
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def write_structured_artifact(
    artifact_dir: Path | None,
    symbol_version: int,
    rules_attempt: int,
    _legacy_attempt: int,
    name: str,
    content: str,
) -> str | None:
    sub = _artifact_subdir(artifact_dir, symbol_version, rules_attempt)
    if sub is None:
        return None
    (sub / name).write_text(content, encoding="utf-8")
    return str(sub / name)


def _fun_kinds_from_symbol_table(symbol_table: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for f in symbol_table.get("functions") or []:
        if isinstance(f, dict) and f.get("name"):
            out[str(f["name"])] = str(f.get("kind") or "")
    return out


def _pred_kinds_from_symbol_table(symbol_table: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in symbol_table.get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            out[str(p["name"])] = str(p.get("kind") or "")
    for f in symbol_table.get("functions") or []:
        if isinstance(f, dict) and f.get("name"):
            out[str(f["name"])] = str(f.get("kind") or "")
    return out


def _build_repair_hints(
    error_message: str,
    previous_output: str,
    *,
    error_code: str,
    layer: str,
    secondary_diagnostics: str = "",
    progress_note: str = "",
    law_text: str | None = None,
    question_text: str | None = None,
    scope_metadata: dict | None = None,
    symbol_table: dict | None = None,
    missing_helper_evidence: MissingHelperEvidence | None = None,
    validation_evidence: ValidationRepairEvidence | None = None,
    merged_ir: dict | None = None,
    query_predicate: str | None = None,
) -> str:
    parts: list[str] = []
    st = symbol_table or parse_symbol_table_from_repair_context(previous_output)
    legal_effect_ctx = legal_effect_rules_repair_context(
        scope_metadata=scope_metadata,
        symbol_table=st,
    )
    card_id = error_code
    composite_card = False
    temporal_escalation = (
        error_code == "missing_temporal_support_symbol"
        or (
            missing_helper_evidence is not None
            and missing_helper_evidence.missing_temporal_support_symbol
        )
    )
    if temporal_escalation:
        card_id = "missing_temporal_support_symbol"
    elif (
        error_code == "missing_helper_definition"
        and missing_helper_evidence
        and qualifies_for_composite_temporal_threshold_card(
            helper_name=missing_helper_evidence.helper_name,
            description="",
            scope_metadata=scope_metadata,
            symbol_table=st,
            derives_legal_output=missing_helper_evidence.derives_legal_output,
        )
    ):
        card_id = "missing_helper_definition_for_composite_temporal_threshold"
        composite_card = True
    elif (
        error_code == "missing_helper_definition"
        and missing_helper_evidence
        and missing_helper_evidence.legal_effect_context
    ):
        card_id = "missing_helper_definition_for_legal_effect"
    if error_code == "computed_observable_unsafe" and legal_effect_ctx:
        card_id = "computed_observable_unsafe_for_legal_effect"
    card = format_repair_card(card_id)
    parts.append("=== ERROR-SPECIFIC REPAIR CARD ===\n" + card)
    if error_code == "missing_legal_effect_output":
        parts.append(
            "=== MISSING LEGAL-EFFECT OUTPUT (mandatory) ===\n"
            + build_missing_legal_effect_repair_supplement(
                error_message,
                law_text=law_text,
                question_text=question_text,
                scope_metadata=scope_metadata,
                symbol_table=st,
            )
        )
    if error_code == "missing_threshold_classification_exclusion":
        parts.append(
            "=== MISSING EXCLUSION RULE (mandatory) ===\n"
            + build_missing_exclusion_repair_supplement(
                error_message,
                law_text=law_text,
                secondary_diagnostics=secondary_diagnostics,
                symbol_table=st,
                merged_ir=merged_ir,
                query_predicate=query_predicate,
            )
        )
    if error_code == "predicate_used_as_function":
        parts.append(
            "=== PREDICATE / FUNCTION MISUSE (mandatory) ===\n"
            + build_predicate_function_misuse_supplement(
                error_message,
                symbol_table=st,
            )
        )
    if error_code == "function_used_as_predicate":
        parts.append(
            "=== FUNCTION / PREDICATE MISUSE (mandatory) ===\n"
            + build_predicate_function_misuse_supplement(
                error_message,
                symbol_table=st,
            )
        )
    if temporal_escalation:
        ts_ev = None
        if validation_evidence and getattr(validation_evidence, "temporal_support", None):
            ts_ev = validation_evidence.temporal_support
        parts.append(
            "=== MISSING TEMPORAL SUPPORT SYMBOL (mandatory) ===\n"
            + build_missing_temporal_support_symbol_supplement(
                law_text=law_text,
                question_text=question_text,
                scope_metadata=scope_metadata,
                symbol_table=st,
                evidence=missing_helper_evidence or ts_ev,
                helper_requiring_temporal_support=(
                    getattr(missing_helper_evidence, "helper_name", None)
                    if missing_helper_evidence
                    else None
                ),
            )
        )
    if (
        error_code == "missing_helper_definition"
        and missing_helper_evidence
        and missing_helper_evidence.missing_temporal_support_symbol
    ):
        parts.append(
            "Rules repair cannot define this helper until temporal support symbols exist. "
            "Escalate to symbols repair (previous/next/consecutive period relation)."
        )
    elif error_code == "missing_helper_definition" and missing_helper_evidence and composite_card:
        parts.append(
            "=== COMPOSITE THRESHOLD/TEMPORAL HELPER (mandatory) ===\n"
            + build_composite_temporal_threshold_supplement(
                error_message=error_message,
                symbol_table=st,
                evidence=missing_helper_evidence,
                law_text=law_text,
            )
        )
    elif (
        error_code == "missing_helper_definition"
        and missing_helper_evidence
        and missing_helper_evidence.legal_effect_context
    ):
        parts.append(
            "=== MISSING HELPER FOR LEGAL-EFFECT RULE (mandatory) ===\n"
            + build_missing_legal_effect_helper_supplement(
                error_message=error_message,
                symbol_table=st,
                evidence=missing_helper_evidence,
                law_text=law_text,
            )
        )
    elif error_code == "missing_helper_definition" and missing_helper_evidence:
        import re as _re

        hn = missing_helper_evidence.helper_name or ""
        hk = getattr(missing_helper_evidence, "helper_kind", "predicate") or "predicate"
        sym_desc = ""
        for f in (st or {}).get("functions") or []:
            if isinstance(f, dict) and f.get("name") == hn:
                sym_desc = str(f.get("description") or "")
                break
        if hk == "function" and looks_like_case_value_function(hn, sym_desc):
            parts.append(
                "=== NUMERIC CASE-VALUE HELPER (mandatory) ===\n"
                + build_numeric_threshold_helper_scaffold(
                    st,
                    helper_name=hn,
                    law_text=law_text,
                    merged_ir=merged_ir,
                )
            )
        elif hk == "function" and looks_like_threshold_helper_function(hn, sym_desc):
            parts.append(
                "=== NUMERIC THRESHOLD HELPER SCAFFOLD (mandatory) ===\n"
                + build_numeric_threshold_helper_scaffold(
                    st,
                    helper_name=hn,
                    law_text=law_text,
                    merged_ir=merged_ir,
                )
            )
        elif _re.search(
            r"(?i)(more_than_one|at_least_two|criterion_exceeded|threshold_exceeded)",
            hn,
        ):
            parts.append(
                "=== THRESHOLD HELPER PAIRWISE SCAFFOLD (mandatory) ===\n"
                + build_threshold_helper_pairwise_scaffold(
                    st,
                    helper_name=hn,
                    law_text=law_text,
                )
            )
    if error_code == "computed_observable_unsafe" and legal_effect_ctx:
        sec_helpers = (
            validation_evidence.secondary_missing_helpers
            if validation_evidence
            else []
        )
        parts.append(
            "=== LEGAL-EFFECT COMPUTED HELPER (mandatory) ===\n"
            + build_legal_effect_computed_helper_supplement(
                error_message=error_message,
                symbol_table=st,
                computed_predicate=(
                    validation_evidence.computed_observable_predicate
                    if validation_evidence
                    else None
                ),
                computed_kind_hint=(
                    validation_evidence.computed_observable_helper_kind_hint
                    if validation_evidence
                    else None
                ),
                secondary_helpers=sec_helpers,
            )
        )
    if progress_note.strip():
        parts.append("=== REPAIR PROGRESS (continue improving; do not repeat identical rules) ===\n" + progress_note)
    if secondary_diagnostics.strip() and error_code != "missing_threshold_classification_exclusion":
        parts.append("=== SECONDARY VALIDATION DIAGNOSTICS ===\n" + secondary_diagnostics)
    machine = build_machine_repair_hints(error_message, previous_output)
    if machine.strip() and "(none" not in machine[:40].lower():
        parts.append(machine)
    jh = build_json_ir_compile_hints(error_message)
    if jh.strip():
        parts.append("JSON IR compile hints:\n" + jh)
    parts.append(
        "Repair layer: %s. Do not delete legal conditions to satisfy validation. "
        "Do not rename predicates without preserving semantics. "
        "Rules will be regenerated from repaired symbols when layer=symbols."
        % layer
    )
    return "\n\n".join(parts)


def _format_failure_message(history: RepairHistory, limits: CompileLoopLimits) -> str:
    lines = [
        "JSON IR compilation failed.",
        "symbol_versions=%d, rules_attempts=%d, total_llm_calls=%d, final_route=%s, final_error=%s"
        % (
            history.symbol_version_count,
            history.rules_attempt_count,
            history.total_kb_llm_calls,
            (history.repair_layers_used[-1] if history.repair_layers_used else "none"),
            history.final_normalized_error_code or "unknown",
        ),
    ]
    if history.repair_stalled:
        lines.append("Repair stalled: same normalized error repeated %d times." % limits.repeated_error_limit)
    if history.budget_exhausted:
        lines.append("Budget exhausted: max_total_kb_llm_calls=%d." % limits.max_total_kb_llm_calls)
    if history.distinct_errors:
        lines.append("Last distinct validation errors:")
        for i, err in enumerate(history.distinct_errors[-5:], 1):
            short = err.replace("\n", " ")[:240]
            lines.append("%d. %s" % (i, short))
    return "\n".join(lines)


def compile_json_ir_structured(
    source_text: str,
    *,
    symbols_llm: SymbolsLLM,
    rules_llm: RulesLLM,
    repair_context_fn: Callable[..., str],
    artifact_dir: Path | str | None = None,
    repair_feedback: dict | None = None,
    limits: CompileLoopLimits | None = None,
    artifact_writer: ArtifactWriter | None = None,
    scope_metadata: dict | None = None,
    question_text: str | None = None,
) -> tuple[str, dict]:
    """Run structured symbol×rules compile loop. Returns (fo_text, kb_schema)."""
    limits = limits or compile_loop_limits_from_env()
    art = Path(artifact_dir) if artifact_dir else None
    writer = artifact_writer or write_structured_artifact
    src = (source_text or "").strip()
    history = RepairHistory()
    event_index = 0

    error_messages: list[str] = []
    signature_counts: dict[str, int] = {}
    rules_repair_streak = 0
    pending_validation_evidence: ValidationRepairEvidence | None = None
    evidence_state = EvidenceTrackingState()
    evidence_ext_config = evidence_extension_config_from_env()
    extension_symbol_slots = 0
    extension_llm_slots = 0
    evidence_extension_calls_used = 0
    last_threshold_snapshot: ThresholdRepairSnapshot | None = None
    last_helper_snapshot: HelperRepairSnapshot | None = None
    helper_no_progress_counts: dict[str, int] = {}
    last_secondary_diagnostics = ""
    last_progress_note = ""
    pending_temporal_symbol_repair = False
    pending_symbol_stage_repair = False
    last_symbol_stage_error_code: str | None = None
    symbol_repair_extension_slots = 0
    _MAX_SYMBOL_REPAIR_EXTENSION_SLOTS = 2

    if repair_feedback:
        boot = (repair_feedback.get("error_message") or "").strip()
        if boot:
            error_messages.append(boot)

    symbol_table: dict | None = None
    symbols_obj: dict | None = None
    raw_symbols = ""
    rules: list | None = None
    rules_obj: dict | None = None
    raw_rules = ""
    total_llm_calls = 0

    def _record(
        *,
        phase: str,
        symbol_version: int,
        rules_attempt: int,
        action: str,
        status: str,
        error_msg: str | None = None,
        route: str | None = None,
        artifact_paths: list[str] | None = None,
        progress_detected: bool | None = None,
        progress_reason: str | None = None,
        previous_error_path: str | None = None,
        current_error_path: str | None = None,
        threshold_cardinality_violation_count: int | None = None,
    ) -> None:
        nonlocal event_index
        event_index += 1
        sig = normalize_error_signature(error_msg) if error_msg else None
        code = normalize_error_code(error_msg) if error_msg else None
        history.record(
            RepairEvent(
                event_index=event_index,
                phase=phase,
                symbol_version=symbol_version,
                rules_attempt=rules_attempt,
                total_llm_calls=total_llm_calls,
                action=action,
                status=status,
                error_kind=route,
                normalized_error_signature=sig,
                normalized_error_code=code,
                repair_route=route,
                repair_card_id=code,
                short_error_message=(error_msg or "")[:500] or None,
                artifact_paths=artifact_paths or [],
                progress_detected=progress_detected,
                progress_reason=progress_reason,
                previous_error_path=previous_error_path,
                current_error_path=current_error_path,
                threshold_cardinality_violation_count=threshold_cardinality_violation_count,
            )
        )

    def _check_stall(
        msg: str,
        *,
        rules_attempt: int = 0,
        progress_verdict=None,
    ) -> bool:
        sig = normalize_error_signature(msg)
        signature_counts[sig] = signature_counts.get(sig, 0) + 1
        code = normalize_error_code(msg)
        if code == "threshold_cardinality_or_singleton" and progress_verdict is not None:
            if should_stall_threshold_cardinality_repeat(
                signature_repeat_count=signature_counts[sig],
                repeated_error_limit=limits.repeated_error_limit,
                progress=progress_verdict,
                rules_attempt=rules_attempt,
                max_rules_attempts=limits.max_rules_attempts_per_symbol_version,
            ):
                history.repeated_error_detected = True
                history.repair_stalled = True
                history.final_normalized_error_signature = sig
                history.final_normalized_error_code = code
                return True
            return False
        if code == "missing_helper_definition" and progress_verdict is not None:
            if should_stall_helper_definition_repeat(
                signature_repeat_count=signature_counts[sig],
                repeated_error_limit=limits.repeated_error_limit,
                progress=progress_verdict,
                rules_attempt=rules_attempt,
                max_rules_attempts=limits.max_rules_attempts_per_symbol_version,
            ):
                history.repeated_error_detected = True
                history.repair_stalled = True
                history.final_normalized_error_signature = sig
                history.final_normalized_error_code = (
                    "no_helper_definition_progress"
                    if not progress_verdict.progress_detected
                    else code
                )
                return True
            return False
        if signature_counts[sig] >= limits.repeated_error_limit:
            history.repeated_error_detected = True
            history.repair_stalled = True
            history.final_normalized_error_signature = sig
            history.final_normalized_error_code = code
            return True
        return False

    def _track_distinct(msg: str) -> None:
        if msg and msg not in history.distinct_errors:
            history.distinct_errors.append(msg[:500])
        if len(history.distinct_errors) > 8:
            history.distinct_errors = history.distinct_errors[-8:]

    symbol_version = 0
    while True:
        effective_symbol_cap = (
            limits.max_symbol_versions
            + extension_symbol_slots
            + symbol_repair_extension_slots
        )
        if symbol_version >= effective_symbol_cap:
            can_symbol_extend = (
                pending_symbol_stage_repair
                and is_symbol_stage_repairable_error(last_symbol_stage_error_code)
                and total_llm_calls
                < limits.max_total_kb_llm_calls + extension_llm_slots
                and symbol_repair_extension_slots < _MAX_SYMBOL_REPAIR_EXTENSION_SLOTS
            )
            if can_symbol_extend:
                symbol_repair_extension_slots += 1
                _record(
                    phase="validation",
                    symbol_version=symbol_version,
                    rules_attempt=0,
                    action="symbol_repair_extension_granted",
                    status="ok",
                    route=last_symbol_stage_error_code,
                )
            else:
                grant, reason = should_grant_evidence_extension(
                    config=evidence_ext_config,
                    extension_calls_used=evidence_extension_calls_used,
                    evidence_state=evidence_state,
                    validation_evidence=pending_validation_evidence,
                    symbol_version=symbol_version,
                    max_symbol_versions=limits.max_symbol_versions + extension_symbol_slots,
                    total_llm_calls=total_llm_calls,
                    max_total_kb_llm_calls=limits.max_total_kb_llm_calls,
                )
                if grant:
                    extension_symbol_slots += 1
                    extension_llm_slots += 1
                    evidence_extension_calls_used += 1
                    history.evidence_extension_used = True
                    history.evidence_extension_calls = evidence_extension_calls_used
                    history.evidence_extension_reason = reason
                    _record(
                        phase="validation",
                        symbol_version=symbol_version,
                        rules_attempt=0,
                        action="evidence_extension_granted",
                        status="ok",
                        route=reason,
                    )
                else:
                    if symbol_version >= limits.max_symbol_versions:
                        history.symbol_budget_exhausted = True
                    break

        symbol_version += 1
        if total_llm_calls >= limits.max_total_kb_llm_calls + extension_llm_slots:
            grant, reason = should_grant_evidence_extension(
                config=evidence_ext_config,
                extension_calls_used=evidence_extension_calls_used,
                evidence_state=evidence_state,
                validation_evidence=pending_validation_evidence,
                symbol_version=symbol_version - 1,
                max_symbol_versions=limits.max_symbol_versions + extension_symbol_slots,
                total_llm_calls=total_llm_calls,
                max_total_kb_llm_calls=limits.max_total_kb_llm_calls,
            )
            if grant:
                extension_symbol_slots += 1
                extension_llm_slots += 1
                evidence_extension_calls_used += 1
                history.evidence_extension_used = True
                history.evidence_extension_calls = evidence_extension_calls_used
                history.evidence_extension_reason = reason
                _record(
                    phase="validation",
                    symbol_version=symbol_version - 1,
                    rules_attempt=0,
                    action="evidence_extension_granted",
                    status="ok",
                    route=reason,
                )
            else:
                history.budget_exhausted = True
                break

        sym_repair = symbol_version > 1
        err_msg = error_messages[-1] if error_messages else ""
        prev = repair_context_fn(
            symbol_table=symbol_table,
            symbols_obj=symbols_obj,
            raw_symbols=raw_symbols,
            rules_obj={"rules": rules} if rules is not None else None,
            raw_rules=raw_rules,
        )
        rules_json = json.dumps({"rules": rules}, ensure_ascii=False, indent=2) if rules else ""
        error_code = normalize_error_code(err_msg) if err_msg else "unknown_validation_error"
        hints = (
            _build_repair_hints(
                err_msg,
                prev,
                error_code=error_code,
                layer="symbols",
                law_text=src,
                question_text=question_text,
                scope_metadata=scope_metadata,
                symbol_table=symbol_table,
                missing_helper_evidence=(
                    pending_validation_evidence.missing_helper
                    if pending_validation_evidence
                    else None
                ),
                secondary_diagnostics=(
                    pending_validation_evidence.format_secondary_diagnostics()
                    if pending_validation_evidence
                    else ""
                ),
                validation_evidence=pending_validation_evidence,
            )
            if sym_repair
            else ""
        )
        if sym_repair and repair_hints_carry_validation_evidence(
            hints, validation_evidence=pending_validation_evidence
        ):
            evidence_state.mark_consumed()
            history.evidence_consumed_by_repair = True
            history.validation_evidence_path = evidence_state.validation_evidence_path
            history.validation_evidence_fingerprint = (
                evidence_state.validation_evidence_fingerprint
            )
        err_for_prompt = err_msg
        if sym_repair and rules_json.strip():
            err_for_prompt = format_symbol_repair_error(err_msg)

        try:
            total_llm_calls += 1
            symbols_obj, raw_symbols = symbols_llm(
                src,
                repair=sym_repair,
                error_message=err_for_prompt,
                previous_output=prev,
                rules_json=rules_json,
                machine_hints=hints,
            )
            _record(
                phase="symbols",
                symbol_version=symbol_version,
                rules_attempt=0,
                action="repair_symbols" if sym_repair else "initial_symbols",
                status="ok",
            )
        except LawCompilationError as e:
            msg = str(e)
            if "JSON IR validation failed" in msg:
                msg = msg.split("JSON IR validation failed:", 1)[-1].strip()
            error_messages.append(msg)
            _track_distinct(msg)
            _record(
                phase="symbols",
                symbol_version=symbol_version,
                rules_attempt=0,
                action="repair_symbols" if sym_repair else "initial_symbols",
                status="llm_failed",
                error_msg=msg,
                route="symbols",
            )
            if _check_stall(msg):
                break
            continue

        symbol_table = {
            "types": symbols_obj.get("types", []),
            "predicates": symbols_obj.get("predicates", []),
            "functions": symbols_obj.get("functions", []),
        }
        for key in ("types", "predicates", "functions"):
            if not isinstance(symbol_table[key], list):
                raise LawCompilationError("JSON IR symbols phase returned invalid %r." % key)

        try:
            validate_json_ir_symbols(
                symbol_table,
                law_text_for_lints=src,
                scope_metadata=scope_metadata,
                question_text=question_text,
                following_missing_temporal_support_repair=pending_temporal_symbol_repair,
            )
            pending_temporal_symbol_repair = False
            pending_symbol_stage_repair = False
            last_symbol_stage_error_code = None
            ap = writer(
                art, symbol_version, 0, symbol_version,
                "symbols.normalized.json",
                json.dumps(symbol_table, ensure_ascii=False, indent=2),
            )
            writer(art, symbol_version, 0, symbol_version, "symbols.raw.json", raw_symbols)
            _record(
                phase="validation",
                symbol_version=symbol_version,
                rules_attempt=0,
                action="validate_symbols",
                status="ok",
                artifact_paths=[ap] if ap else [],
            )
        except JSONIRCompilationError as e:
            msg = str(e)
            error_messages.append(msg)
            _track_distinct(msg)
            route = classify_json_ir_validation_error(
                msg, error_messages[:-1], rules_repair_count=0,
                max_rules_before_symbol_escalation=limits.max_rules_before_symbol_escalation,
            )
            code = normalize_error_code(msg)
            if code == "missing_temporal_support_symbol":
                pending_temporal_symbol_repair = True
            if route == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED:
                pending_symbol_stage_repair = True
                last_symbol_stage_error_code = code
            _record(
                phase="validation",
                symbol_version=symbol_version,
                rules_attempt=0,
                action="validate_symbols",
                status="validation_failed",
                error_msg=msg,
                route=route.value,
            )
            writer(
                art, symbol_version, 0, symbol_version,
                "validation_error.txt", msg,
            )
            if _check_stall(msg):
                break
            rules = None
            rules_obj = None
            raw_rules = ""
            symbol_table = None
            symbols_obj = None
            continue

        rules = None
        rules_obj = None
        raw_rules = ""
        rules_repair_streak = 0
        symbol_rules_errors: list[str] = []
        last_threshold_snapshot = None
        last_helper_snapshot = None
        helper_no_progress_counts = {}
        last_secondary_diagnostics = ""
        last_progress_note = ""
        last_missing_helper_evidence: MissingHelperEvidence | None = None

        for rules_attempt in range(1, limits.max_rules_attempts_per_symbol_version + 1):
            if total_llm_calls >= limits.max_total_kb_llm_calls:
                history.budget_exhausted = True
                break

            rules_repair = rules_attempt > 1
            err_msg = symbol_rules_errors[-1] if rules_repair else ""
            prev = repair_context_fn(
                symbol_table=symbol_table,
                raw_symbols=raw_symbols,
                rules_obj=rules_obj,
                raw_rules=raw_rules,
            )
            error_code = normalize_error_code(err_msg) if err_msg else "unknown_validation_error"
            machine_hints = (
                _build_repair_hints(
                    err_msg,
                    prev,
                    error_code=error_code,
                    layer="rules",
                    secondary_diagnostics=last_secondary_diagnostics,
                    progress_note=last_progress_note,
                    law_text=src,
                    question_text=question_text,
                    scope_metadata=scope_metadata,
                    symbol_table=symbol_table,
                    missing_helper_evidence=last_missing_helper_evidence,
                    validation_evidence=pending_validation_evidence,
                    merged_ir={
                        "types": (symbol_table or {}).get("types") or [],
                        "predicates": (symbol_table or {}).get("predicates") or [],
                        "functions": (symbol_table or {}).get("functions") or [],
                        "rules": (rules_obj or {}).get("rules") or rules or [],
                    },
                )
                if rules_repair and err_msg
                else ""
            )

            try:
                total_llm_calls += 1
                rules_obj, raw_rules = rules_llm(
                    src,
                    symbol_table,
                    repair=rules_repair,
                    error_message=err_msg,
                    previous_output=prev,
                    machine_hints=machine_hints,
                )
                _record(
                    phase="rules",
                    symbol_version=symbol_version,
                    rules_attempt=rules_attempt,
                    action="repair_rules" if rules_repair else "initial_rules",
                    status="ok",
                )
            except LawCompilationError as e:
                msg = str(e)
                if "JSON IR validation failed" in msg:
                    msg = msg.split("JSON IR validation failed:", 1)[-1].strip()
                symbol_rules_errors.append(msg)
                error_messages.append(msg)
                _track_distinct(msg)
                _record(
                    phase="rules",
                    symbol_version=symbol_version,
                    rules_attempt=rules_attempt,
                    action="repair_rules" if rules_repair else "initial_rules",
                    status="llm_failed",
                    error_msg=msg,
                    route="rules",
                )
                if _check_stall(msg):
                    break
                continue

            rules = rules_obj.get("rules")
            if not isinstance(rules, list):
                msg = "JSON IR rules phase returned invalid 'rules'."
                error_messages.append(msg)
                continue

            merged_ir = {
                "types": symbol_table["types"],
                "predicates": symbol_table["predicates"],
                "functions": symbol_table["functions"],
                "rules": rules,
            }
            cap = writer(
                art, symbol_version, rules_attempt, symbol_version,
                "combined_ir.json",
                json.dumps(merged_ir, ensure_ascii=False, indent=2),
            )
            writer(art, symbol_version, rules_attempt, symbol_version, "rules.raw.json", raw_rules)

            try:
                fo_text, schema = render_json_ir_to_fo_and_schema(
                    merged_ir,
                    law_text_for_lints=src,
                    scope_metadata=scope_metadata,
                )
                writer(art, symbol_version, rules_attempt, symbol_version, "rendered.fo", fo_text)
                writer(
                    art, symbol_version, rules_attempt, symbol_version,
                    "error_classification.txt", "success",
                )
                _record(
                    phase="render",
                    symbol_version=symbol_version,
                    rules_attempt=rules_attempt,
                    action="success",
                    status="ok",
                    artifact_paths=[cap] if cap else [],
                )
                history.write(art)
                try:
                    from pipeline.kb.schema_environment import save_schema_environment

                    save_schema_environment(art, schema)
                except Exception:
                    pass
                return fo_text, schema
            except JSONIRCompilationError as e:
                msg = str(e)
                symbol_rules_errors.append(msg)
                error_messages.append(msg)
                _track_distinct(msg)
                kind = classify_json_ir_validation_error(
                    msg,
                    symbol_rules_errors[:-1],
                    rules_repair_count=rules_repair_streak,
                    max_rules_before_symbol_escalation=limits.max_rules_before_symbol_escalation,
                )
                sig = normalize_error_signature(msg)
                code = normalize_error_code(msg)
                if signature_counts.get(sig, 0) >= limits.repeated_error_limit - 1:
                    if kind == JsonIRErrorKind.RULES_REPAIR_ONLY:
                        if code != "threshold_cardinality_or_singleton":
                            kind = JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

                pred_kinds = _pred_kinds_from_symbol_table(symbol_table)
                fun_kinds = _fun_kinds_from_symbol_table(symbol_table)
                evidence = collect_validation_repair_evidence(
                    merged_ir,
                    pred_kinds,
                    law_text_for_lints=src,
                    error_message=msg,
                    symbol_table=symbol_table,
                    scope_metadata=scope_metadata,
                    question_text=question_text,
                )
                last_missing_helper_evidence = evidence.missing_helper
                pending_validation_evidence = evidence
                last_secondary_diagnostics = evidence.format_secondary_diagnostics()
                if evidence.missing_temporal_support_symbol or (
                    code == "missing_helper_definition"
                    and evidence.missing_helper
                    and evidence.missing_helper.missing_temporal_support_symbol
                ):
                    kind = JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
                evidence_state.register_evidence(
                    path=None,
                    evidence=evidence,
                    error_code=code,
                    repair_route=kind.value,
                )
                history.validation_evidence_fingerprint = (
                    evidence_state.validation_evidence_fingerprint
                )
                history.evidence_consumed_by_repair = (
                    evidence_state.evidence_consumed_by_repair
                )
                evidence_path = writer(
                    art,
                    symbol_version,
                    rules_attempt,
                    symbol_version,
                    "validation_evidence.json",
                    json.dumps(
                        {
                            "cardinality_violations": evidence.cardinality_violations,
                            "numeric_provenance_issues": evidence.numeric_provenance_issues,
                            "law_thresholds": evidence.law_thresholds,
                            "missing_helper": (
                                evidence.missing_helper.to_dict()
                                if evidence.missing_helper
                                else None
                            ),
                            "secondary_missing_helpers": [
                                h.to_dict() for h in evidence.secondary_missing_helpers
                            ],
                            "computed_observable_predicate": evidence.computed_observable_predicate,
                            "computed_observable_helper_kind_hint": (
                                evidence.computed_observable_helper_kind_hint
                            ),
                            "temporal_support": evidence.temporal_support,
                            "missing_temporal_support_symbol": evidence.missing_temporal_support_symbol,
                            "repair_route": evidence.repair_route,
                            "secondary_diagnostics_text": last_secondary_diagnostics,
                            "validation_evidence_fingerprint": (
                                evidence_state.validation_evidence_fingerprint
                            ),
                            "evidence_consumed_by_repair": evidence_state.evidence_consumed_by_repair,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                )
                evidence_state.validation_evidence_path = evidence_path
                history.validation_evidence_path = evidence_path

                progress_verdict = None
                if code == "threshold_cardinality_or_singleton":
                    current_snapshot = build_threshold_repair_snapshot(
                        merged_ir,
                        pred_kinds,
                        cardinality_violations=evidence.cardinality_violations,
                        numeric_provenance_count=len(evidence.numeric_provenance_issues),
                        primary_error_path=extract_error_path_from_message(msg),
                    )
                    progress_verdict = detect_threshold_cardinality_progress(
                        last_threshold_snapshot, current_snapshot
                    )
                    last_threshold_snapshot = current_snapshot
                    if progress_verdict.progress_detected:
                        last_progress_note = (
                            "Structural progress detected (%s). Continue repairing; "
                            "fix the exclusion rule IF to pairwise exceeded AND combinations "
                            "if THEN is negated, and keep the positive rule."
                            % progress_verdict.progress_reason
                        )
                    else:
                        last_progress_note = (
                            "No structural progress (%s). Change rule structure, "
                            "do not resubmit identical rules."
                            % progress_verdict.progress_reason
                        )
                elif code == "missing_helper_definition" and evidence.missing_helper:
                    helper_name = evidence.missing_helper.helper_name
                    helper_kind = getattr(evidence.missing_helper, "helper_kind", "predicate") or "predicate"
                    mini_snapshot = build_helper_repair_snapshot(
                        merged_ir,
                        helper_name=helper_name,
                        helper_kind=helper_kind,
                        fun_kinds=fun_kinds,
                        primary_error_path=extract_error_path_from_message(msg),
                    )
                    progress_verdict = detect_helper_definition_progress(
                        last_helper_snapshot, mini_snapshot
                    )
                    last_helper_snapshot = mini_snapshot
                    if progress_verdict.progress_detected:
                        last_progress_note = (
                            "Helper-definition progress detected (%s). Continue until '%s' "
                            "appears in THEN."
                            % (progress_verdict.progress_reason, helper_name)
                        )
                    else:
                        last_progress_note = (
                            "No helper-definition progress (%s). Add a rule defining '%s' "
                            "in THEN; do not resubmit identical rules."
                            % (progress_verdict.progress_reason, helper_name)
                        )
                    if progress_verdict and not progress_verdict.progress_detected:
                        helper_no_progress_counts[helper_name] = (
                            helper_no_progress_counts.get(helper_name, 0) + 1
                        )
                    elif progress_verdict and progress_verdict.progress_detected:
                        helper_no_progress_counts.pop(helper_name, None)

                if (
                    code == "missing_helper_definition"
                    and evidence.missing_helper
                    and helper_no_progress_counts.get(evidence.missing_helper.helper_name, 0) >= 2
                ):
                    history.repeated_error_detected = True
                    history.repair_stalled = True
                    hk = getattr(evidence.missing_helper, "helper_kind", "predicate") or "predicate"
                    history.final_normalized_error_code = (
                        "repeated_missing_numeric_helper_definition"
                        if hk == "function"
                        else "repeated_missing_helper_definition"
                    )
                    history.final_normalized_error_signature = normalize_error_signature(msg)
                    break

                writer(
                    art, symbol_version, rules_attempt, symbol_version,
                    "validation_error.txt", msg,
                )
                writer(
                    art, symbol_version, rules_attempt, symbol_version,
                    "error_classification.txt", kind.value,
                )
                _record(
                    phase="validation",
                    symbol_version=symbol_version,
                    rules_attempt=rules_attempt,
                    action="validate_combined",
                    status="validation_failed",
                    error_msg=msg,
                    route=kind.value,
                    progress_detected=(
                        progress_verdict.progress_detected if progress_verdict else None
                    ),
                    progress_reason=(
                        progress_verdict.progress_reason if progress_verdict else None
                    ),
                    previous_error_path=(
                        progress_verdict.previous_error_path if progress_verdict else None
                    ),
                    current_error_path=(
                        progress_verdict.current_error_path if progress_verdict else None
                    ),
                    threshold_cardinality_violation_count=(
                        getattr(progress_verdict, "threshold_cardinality_violation_count", None)
                        if progress_verdict
                        else None
                    ),
                )

                if _check_stall(
                    msg,
                    rules_attempt=rules_attempt,
                    progress_verdict=progress_verdict,
                ):
                    break

                history.final_normalized_error_code = code
                if evidence.missing_temporal_support_symbol:
                    history.final_normalized_error_code = "missing_temporal_support_symbol"
                history.final_normalized_error_signature = sig

                if kind == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED:
                    esc_code = normalize_error_code(msg)
                    if evidence.missing_temporal_support_symbol or (
                        evidence.missing_helper is not None
                        and evidence.missing_helper.missing_temporal_support_symbol
                    ):
                        pending_temporal_symbol_repair = True
                        esc_code = "missing_temporal_support_symbol"
                    if is_symbol_stage_repairable_error(esc_code):
                        pending_symbol_stage_repair = True
                        last_symbol_stage_error_code = esc_code
                    rules_repair_streak = 0
                    rules = None
                    rules_obj = None
                    raw_rules = ""
                    symbol_table = None
                    symbols_obj = None
                    break  # next symbol version

                rules_repair_streak += 1
                rules = None
                rules_obj = None
                raw_rules = ""
                continue

        if history.repair_stalled or history.budget_exhausted:
            break

    history.final_failure_category = (
        "budget_exhausted" if history.budget_exhausted
        else "repair_stalled" if history.repair_stalled
        else "symbol_budget_exhausted" if history.symbol_budget_exhausted
        else "validation_exhausted"
    )
    if error_messages:
        history.final_normalized_error_code = normalize_error_code(error_messages[-1])
        history.final_normalized_error_signature = normalize_error_signature(error_messages[-1])

    history.evidence_consumed_by_repair = evidence_state.evidence_consumed_by_repair
    history.validation_evidence_path = evidence_state.validation_evidence_path
    history.validation_evidence_fingerprint = evidence_state.validation_evidence_fingerprint

    history.write(art)
    ctx = repair_context_fn(
        symbol_table=symbol_table,
        symbols_obj=symbols_obj,
        raw_symbols=raw_symbols,
        raw_rules=raw_rules,
        rules_obj={"rules": rules} if rules else None,
    )
    summary_msg = _format_failure_message(history, limits)
    raise LawCompilationError(
        summary_msg,
        repair_snapshot={
            "previous_output": ctx,
            "error_history": error_messages[-8:],
            **history.to_snapshot(),
        },
        error_kind=history.final_normalized_error_code,
        repair_summary=history.to_snapshot().get("repair_summary"),
    )
