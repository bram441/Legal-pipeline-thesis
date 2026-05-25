"""Collect validation diagnostics for repair prompts (primary error may block later validators)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pipeline.kb.law_numeric_literals import format_law_numbers_for_message
from pipeline.kb.legal_effect import predicate_represents_legal_effect_output
from pipeline.kb.composite_temporal_threshold_repair_hints import (
    classify_helper_kind_hints,
    collect_legal_output_candidates,
    collect_threshold_helper_candidates,
    primary_helper_kind_hint,
)
from pipeline.kb.temporal_support import (
    assess_temporal_support,
    diagnose_missing_temporal_support,
    find_temporal_support_symbols,
    undeclared_temporal_funcs_in_rules,
)
from pipeline.kb.legal_effect_helper_repair_hints import (
    classify_helper_kind_hint,
    extract_computed_observable_predicate,
    extract_missing_helper_kind,
    extract_missing_helper_name,
    find_rules_using_helper,
    legal_effect_rules_repair_context,
)
from pipeline.kb.numeric_threshold_provenance import collect_numeric_threshold_provenance_issues
from pipeline.kb.threshold_cardinality import collect_threshold_cardinality_violations


@dataclass
class MissingHelperEvidence:
    helper_name: str
    helper_kind_hint: str
    helper_kind_hints: list[str] = field(default_factory=list)
    used_in_rules: list[dict[str, Any]] = field(default_factory=list)
    derives_legal_output: bool = False
    used_in_legal_output_rule: bool = False
    legal_output_predicates_in_then: list[str] = field(default_factory=list)
    candidate_lower_level_symbols: list[dict[str, str]] = field(default_factory=list)
    threshold_helper_candidates: list[dict[str, str]] = field(default_factory=list)
    temporal_relation_candidates: list[dict[str, str]] = field(default_factory=list)
    legal_output_candidates: list[dict[str, str]] = field(default_factory=list)
    missing_temporal_support_symbol: bool = False
    undeclared_temporal_funcs_in_rules: list[str] = field(default_factory=list)
    legal_effect_context: bool = False
    is_secondary: bool = False
    helper_signature: str = ""
    helper_kind: str = "predicate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "helper_name": self.helper_name,
            "helper_signature": self.helper_signature,
            "helper_kind": self.helper_kind,
            "helper_kind_hint": self.helper_kind_hint,
            "helper_kind_hints": self.helper_kind_hints,
            "used_in_rules": self.used_in_rules,
            "derives_legal_output": self.derives_legal_output,
            "used_in_legal_output_rule": self.used_in_legal_output_rule,
            "legal_output_predicates_in_then": self.legal_output_predicates_in_then,
            "candidate_lower_level_symbols": self.candidate_lower_level_symbols,
            "threshold_helper_candidates": self.threshold_helper_candidates,
            "temporal_relation_candidates": self.temporal_relation_candidates,
            "legal_output_candidates": self.legal_output_candidates,
            "missing_temporal_support_symbol": self.missing_temporal_support_symbol,
            "undeclared_temporal_funcs_in_rules": self.undeclared_temporal_funcs_in_rules,
            "legal_effect_context": self.legal_effect_context,
            "is_secondary": self.is_secondary,
        }

    def format_diagnostics(self) -> str:
        prefix = "secondary missing_helper_definition" if self.is_secondary else "missing_helper_definition"
        lines = [
            "%s (legal-effect context=%s):"
            % (prefix, self.legal_effect_context),
            "  helper: %s (signature=%s; kind=%s; hints=%s)"
            % (
                self.helper_name,
                self.helper_signature or "?",
                self.helper_kind_hint,
                ", ".join(self.helper_kind_hints) if self.helper_kind_hints else self.helper_kind_hint,
            ),
        ]
        lines.append(
            "  repair: define '%s' in THEN with rules, or reclassify as case_input/background only if safe; "
            "do not rename without defining."
            % self.helper_name
        )
        if "threshold" in self.helper_kind_hints or "counting" in self.helper_kind_hints:
            lines.append(
                "  threshold hint: prefer pairwise/conjunctive THEN definitions "
                "((A&B) OR (A&C) OR (B&C)) for more-than-one helpers."
            )
        if self.missing_temporal_support_symbol:
            lines.append(
                "  missing_temporal_support_symbol: true (escalate to symbols repair)"
            )
        if self.legal_output_predicates_in_then:
            lines.append(
                "  legal-output THEN predicate(s): "
                + ", ".join(self.legal_output_predicates_in_then)
            )
        for u in self.used_in_rules[:6]:
            lines.append(
                "  - rules[%s].%s%s%s"
                % (
                    u.get("rule_index", "?"),
                    u.get("side", "if"),
                    " negated" if u.get("negated") else "",
                    (
                        " -> THEN: " + ", ".join(u.get("then_legal_output_predicates") or [])
                        if u.get("then_legal_output_predicates")
                        else ""
                    ),
                )
            )
        if self.threshold_helper_candidates:
            lines.append("  threshold helper candidates:")
            for c in self.threshold_helper_candidates[:6]:
                lines.append("    - %s (%s)" % (c.get("name"), c.get("kind")))
        if self.temporal_relation_candidates:
            lines.append("  temporal relation candidates:")
            for c in self.temporal_relation_candidates[:6]:
                lines.append("    - %s (%s)" % (c.get("name"), c.get("kind")))
        elif self.missing_temporal_support_symbol:
            lines.append("  temporal relation candidates: (none in symbol table)")
        if self.candidate_lower_level_symbols:
            lines.append("  other lower-level symbols:")
            for c in self.candidate_lower_level_symbols[:8]:
                lines.append("    - %s (%s)" % (c.get("name"), c.get("kind")))
        return "\n".join(lines)


@dataclass
class ValidationRepairEvidence:
    cardinality_violations: list[str] = field(default_factory=list)
    numeric_provenance_issues: list[dict[str, Any]] = field(default_factory=list)
    law_thresholds: list[float] = field(default_factory=list)
    missing_helper: MissingHelperEvidence | None = None
    secondary_missing_helpers: list[MissingHelperEvidence] = field(default_factory=list)
    computed_observable_predicate: str | None = None
    computed_observable_helper_kind_hint: str | None = None
    temporal_support: dict[str, Any] | None = None
    missing_temporal_support_symbol: bool = False
    repair_route: str | None = None

    @property
    def threshold_cardinality_violation_count(self) -> int:
        return len(self.cardinality_violations)

    def primary_error_path(self) -> str | None:
        if not self.cardinality_violations:
            return None
        return _extract_rule_path(self.cardinality_violations[0])

    def format_secondary_diagnostics(self) -> str:
        lines: list[str] = []
        if self.numeric_provenance_issues:
            lines.append("numeric_threshold_not_in_law_text (secondary — fix even if cardinality is primary):")
            for issue in self.numeric_provenance_issues:
                val = issue.get("threshold")
                path = issue.get("path", "?")
                lines.append(
                    "  - Rule %s uses numeric threshold %s, not in scoped law text."
                    % (path, val)
                )
            if self.law_thresholds:
                lines.append(
                    "  Allowed law-text thresholds: %s"
                    % format_law_numbers_for_message(set(self.law_thresholds))
                )
            lines.append("Also fix these numeric threshold provenance issues.")
        if len(self.cardinality_violations) > 1:
            lines.append(
                "Additional threshold_cardinality violations (%d total):"
                % len(self.cardinality_violations)
            )
            for v in self.cardinality_violations[1:4]:
                lines.append("  - " + v[:200])
        if self.computed_observable_predicate:
            lines.append(
                "computed_observable_unsafe subject: %s (helper_kind_hint=%s)"
                % (
                    self.computed_observable_predicate,
                    self.computed_observable_helper_kind_hint or "unknown",
                )
            )
        if self.secondary_missing_helpers:
            lines.append(
                "secondary missing_helper_definition (%d helper(s) used in IF, not in THEN):"
                % len(self.secondary_missing_helpers)
            )
            for h in self.secondary_missing_helpers:
                lines.append(h.format_diagnostics())
        elif self.missing_helper is not None:
            lines.append(self.missing_helper.format_diagnostics())
        if self.missing_temporal_support_symbol:
            lines.append("missing_temporal_support_symbol: true")
            if self.repair_route:
                lines.append("repair_route: %s" % self.repair_route)
            if self.temporal_support:
                terms = self.temporal_support.get("detected_temporal_terms") or []
                if terms:
                    lines.append("detected_temporal_terms: " + ", ".join(terms[:6]))
        return "\n".join(lines)


def _extract_rule_path(message: str) -> str | None:
    m = re.search(r"(rules\[\d+\](?:\.[a-zA-Z0-9_\[\]]+)*)", message or "")
    return m.group(1) if m else None


def _legal_output_names_from_symbol_table(symbol_table: dict | None) -> set[str]:
    out: set[str] = set()
    if not symbol_table:
        return out
    for p in symbol_table.get("predicates") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        name = str(p["name"])
        desc = str(p.get("description") or "")
        kind = str(p.get("kind") or "")
        lo = p.get("legal_output")
        cat = str(p.get("output_category") or "")
        if predicate_represents_legal_effect_output(
            name,
            description=desc,
            kind=kind,
            legal_output=lo if isinstance(lo, bool) else None,
            output_category=cat,
        ):
            out.add(name)
    return out


def _candidate_lower_level_symbols(
    helper_name: str,
    symbol_table: dict | None,
    pred_kinds: dict[str, str],
    defined_in_then: set[str],
) -> list[dict[str, str]]:
    helper_tokens = {
        t
        for t in re.split(r"[^a-z0-9]+", (helper_name or "").lower())
        if len(t) >= 4
    }
    stop = {
        "more",
        "than",
        "one",
        "two",
        "from",
        "year",
        "years",
        "helper",
        "criterion",
        "criteria",
    }
    helper_tokens -= stop
    candidates: list[dict[str, str]] = []
    if not symbol_table:
        return candidates

    def _consider(sym: dict) -> None:
        if not isinstance(sym, dict) or not sym.get("name"):
            return
        name = str(sym["name"])
        if name == helper_name:
            return
        kind = str(sym.get("kind") or pred_kinds.get(name, ""))
        desc = str(sym.get("description") or "")
        name_l = name.lower()
        score = 0
        if kind in {"observable", "input"}:
            score += 2
        if kind == "helper" and name in defined_in_then:
            score += 3
        if kind in {"derived", "conclusion"}:
            score += 1
        for tok in helper_tokens:
            if tok in name_l:
                score += 2
        if score <= 0:
            return
        candidates.append(
            {"name": name, "kind": kind, "description": desc[:120], "_score": str(score)}
        )

    for p in symbol_table.get("predicates") or []:
        _consider(p)
    for f in symbol_table.get("functions") or []:
        _consider(f)
    candidates.sort(key=lambda c: int(c.get("_score", "0")), reverse=True)
    for c in candidates:
        c.pop("_score", None)
    return candidates[:12]


def _helper_signature_from_symbol_table(helper: str, symbol_table: dict | None) -> str:
    if not symbol_table:
        return ""
    for section in ("predicates", "functions"):
        for sym in symbol_table.get(section) or []:
            if not isinstance(sym, dict) or sym.get("name") != helper:
                continue
            args = sym.get("args") or []
            returns = str(sym.get("returns") or "Bool").strip()
            if args:
                return "%s -> %s" % (" * ".join(str(a) for a in args), returns)
            return "() -> %s" % returns
    return ""


def _infer_helper_kind(
    helper: str,
    symbol_table: dict | None,
    error_message: str | None = None,
) -> str:
    if error_message and extract_missing_helper_kind(error_message) == "function":
        return "function"
    for f in (symbol_table or {}).get("functions") or []:
        if isinstance(f, dict) and f.get("name") == helper:
            return "function"
    return "predicate"


def _missing_helper_evidence_for_name(
    ir: dict,
    pred_kinds: dict[str, str],
    helper: str,
    *,
    symbol_table: dict | None = None,
    scope_metadata: dict | None = None,
    law_text: str | None = None,
    question_text: str | None = None,
    is_secondary: bool = False,
    error_message: str | None = None,
) -> MissingHelperEvidence:
    from pipeline.kb.json_ir import _collect_helper_symbol_usage

    rules = ir.get("rules") or []
    fun_kinds = {
        str(f.get("name")): str(f.get("kind") or "")
        for f in (symbol_table or {}).get("functions") or []
        if isinstance(f, dict) and f.get("name")
    }
    _, _, def_then_p, _ = _collect_helper_symbol_usage(rules, pred_kinds, fun_kinds)
    legal_output_names = _legal_output_names_from_symbol_table(symbol_table)

    sym_desc = ""
    for p in (symbol_table or {}).get("predicates") or []:
        if isinstance(p, dict) and p.get("name") == helper:
            sym_desc = str(p.get("description") or "")
            break

    usages = find_rules_using_helper(ir, helper)
    legal_then_all: list[str] = []
    derives = False
    for u in usages:
        then_preds = u.get("then_predicates") or []
        legal_in_rule = [p for p in then_preds if p in legal_output_names]
        u["then_legal_output_predicates"] = legal_in_rule
        if legal_in_rule:
            derives = True
            legal_then_all.extend(legal_in_rule)

    legal_effect_ctx = legal_effect_rules_repair_context(
        scope_metadata=scope_metadata,
        symbol_table=symbol_table,
        merged_ir=ir,
        missing_helper_name=helper,
    )

    kind_hints = classify_helper_kind_hints(helper, sym_desc)
    undeclared_temporal = undeclared_temporal_funcs_in_rules(ir, symbol_table)
    missing_temporal = diagnose_missing_temporal_support(
        helper,
        symbol_table=symbol_table,
        description=sym_desc,
        merged_ir=ir,
        law_text=law_text,
        question_text=question_text,
        scope_metadata=scope_metadata,
    )

    return MissingHelperEvidence(
        helper_name=helper,
        helper_signature=_helper_signature_from_symbol_table(helper, symbol_table),
        helper_kind=_infer_helper_kind(helper, symbol_table, error_message),
        helper_kind_hint=primary_helper_kind_hint(kind_hints),
        helper_kind_hints=kind_hints,
        used_in_rules=usages,
        derives_legal_output=derives,
        used_in_legal_output_rule=derives,
        legal_output_predicates_in_then=sorted(set(legal_then_all)),
        candidate_lower_level_symbols=_candidate_lower_level_symbols(
            helper, symbol_table, pred_kinds, def_then_p
        ),
        threshold_helper_candidates=collect_threshold_helper_candidates(
            symbol_table, defined_in_then=def_then_p
        ),
        temporal_relation_candidates=find_temporal_support_symbols(symbol_table),
        legal_output_candidates=collect_legal_output_candidates(symbol_table),
        missing_temporal_support_symbol=missing_temporal,
        undeclared_temporal_funcs_in_rules=undeclared_temporal,
        legal_effect_context=legal_effect_ctx,
        is_secondary=is_secondary,
    )


def collect_missing_helper_evidence(
    ir: dict,
    pred_kinds: dict[str, str],
    *,
    error_message: str | None,
    symbol_table: dict | None = None,
    scope_metadata: dict | None = None,
    law_text: str | None = None,
    question_text: str | None = None,
) -> MissingHelperEvidence | None:
    helper = extract_missing_helper_name(error_message)
    if not helper:
        return None
    return _missing_helper_evidence_for_name(
        ir,
        pred_kinds,
        helper,
        symbol_table=symbol_table,
        scope_metadata=scope_metadata,
        law_text=law_text,
        question_text=question_text,
        is_secondary=False,
        error_message=error_message,
    )


def collect_floating_helper_evidence(
    ir: dict,
    pred_kinds: dict[str, str],
    *,
    symbol_table: dict | None = None,
    scope_metadata: dict | None = None,
    is_secondary: bool = True,
) -> list[MissingHelperEvidence]:
    """Helpers used in IF but never defined in THEN (non-blocking scan)."""
    from pipeline.kb.json_ir import _collect_helper_symbol_usage

    rules = ir.get("rules") or []
    if not rules:
        return []
    fun_kinds = {
        str(f.get("name")): str(f.get("kind") or "")
        for f in (symbol_table or {}).get("functions") or []
        if isinstance(f, dict) and f.get("name")
    }
    in_if_p, _, def_then_p, _ = _collect_helper_symbol_usage(rules, pred_kinds, fun_kinds)
    floating = sorted(in_if_p - def_then_p)
    if not floating:
        return []

    out: list[MissingHelperEvidence] = []
    for name in floating:
        out.append(
            _missing_helper_evidence_for_name(
                ir,
                pred_kinds,
                name,
                symbol_table=symbol_table,
                scope_metadata=scope_metadata,
                is_secondary=is_secondary,
            )
        )
    out.sort(
        key=lambda e: (
            0 if e.derives_legal_output else 1,
            0 if e.legal_effect_context else 1,
            e.helper_name,
        )
    )
    return out


def collect_validation_repair_evidence(
    ir: dict,
    pred_kinds: dict[str, str],
    *,
    law_text_for_lints: str | None,
    error_message: str | None = None,
    symbol_table: dict | None = None,
    scope_metadata: dict | None = None,
    question_text: str | None = None,
) -> ValidationRepairEvidence:
    """Non-blocking collection of cardinality + numeric provenance + helper issues."""
    from pipeline.kb.law_numeric_literals import extract_numeric_values_from_law_text
    from pipeline.kb.json_ir_repair import normalize_error_code

    law_text = (law_text_for_lints or "").strip()
    law_vals = sorted(extract_numeric_values_from_law_text(law_text)) if law_text else []
    cardinality = collect_threshold_cardinality_violations(
        ir, pred_kinds, law_text_for_lints=law_text_for_lints
    )
    numeric = collect_numeric_threshold_provenance_issues(
        ir, law_text_for_lints=law_text_for_lints
    )
    code = normalize_error_code(error_message or "")
    missing_helper = None
    secondary_missing_helpers: list[MissingHelperEvidence] = []
    computed_observable_predicate = None
    computed_observable_helper_kind_hint = None

    helper_for_temporal = None
    if code == "missing_helper_definition":
        missing_helper = collect_missing_helper_evidence(
            ir,
            pred_kinds,
            error_message=error_message,
            symbol_table=symbol_table,
            scope_metadata=scope_metadata,
            law_text=law_text_for_lints,
            question_text=question_text,
        )
        if missing_helper:
            helper_for_temporal = missing_helper.helper_name
    elif code == "computed_observable_unsafe" and (ir.get("rules") or []):
        computed_observable_predicate = extract_computed_observable_predicate(error_message)
        if computed_observable_predicate:
            computed_observable_helper_kind_hint = classify_helper_kind_hint(
                computed_observable_predicate
            )
        legal_ctx = legal_effect_rules_repair_context(
            scope_metadata=scope_metadata,
            symbol_table=symbol_table,
            merged_ir=ir,
        )
        if legal_ctx:
            secondary_missing_helpers = collect_floating_helper_evidence(
                ir,
                pred_kinds,
                symbol_table=symbol_table,
                scope_metadata=scope_metadata,
                is_secondary=True,
            )

    temporal_det = assess_temporal_support(
        symbol_table,
        law_text=law_text_for_lints,
        question_text=question_text,
        scope_metadata=scope_metadata,
        merged_ir=ir,
        helper_name=helper_for_temporal or (missing_helper.helper_name if missing_helper else None),
        helper_description="",
    )
    missing_temporal = temporal_det.requires_temporal_support or (
        missing_helper is not None and missing_helper.missing_temporal_support_symbol
    )
    repair_route = "symbols_repair_required" if missing_temporal else None

    return ValidationRepairEvidence(
        cardinality_violations=cardinality,
        numeric_provenance_issues=numeric,
        law_thresholds=law_vals,
        missing_helper=missing_helper,
        secondary_missing_helpers=secondary_missing_helpers,
        computed_observable_predicate=computed_observable_predicate,
        computed_observable_helper_kind_hint=computed_observable_helper_kind_hint,
        temporal_support=temporal_det.to_dict(),
        missing_temporal_support_symbol=missing_temporal,
        repair_route=repair_route,
    )


def extract_error_path_from_message(message: str) -> str | None:
    return _extract_rule_path(message)
