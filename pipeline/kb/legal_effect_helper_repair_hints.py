"""Rules-repair supplement when helpers block legal-effect predicate definitions."""

from __future__ import annotations

import re
from typing import Any

from pipeline.kb.legal_effect import predicate_represents_legal_effect_output

_HELPER_NAME_RE = re.compile(
    r"Helper predicate '([^']+)'",
    re.IGNORECASE,
)

_COMPUTED_OBSERVABLE_RE = re.compile(
    r"Predicate '([^']+)'\s+\(kind=observable\)\s+looks computed",
    re.IGNORECASE,
)

_THRESHOLD_MARKERS = (
    "threshold",
    "exceed",
    "exceeded",
    "criterion",
    "criteria",
    "more_than",
    "less_than",
    "at_least",
    "balance_sheet",
    "turnover",
    "employee",
)

_TEMPORAL_MARKERS = (
    "following",
    "next",
    "subsequent",
    "period",
    "year",
    "financial_year",
    "from_year",
    "timing",
    "commence",
    "apply_from",
)

_CONSECUTIVE_MARKERS = (
    "consecutive",
    "two_year",
    "successive",
    "again",
    "second",
)

_CLASSIFICATION_MARKERS = (
    "is_",
    "classification",
    "small_company",
    "micro_company",
    "category",
    "status",
)


def extract_missing_helper_name(error_message: str | None) -> str | None:
    m = _HELPER_NAME_RE.search(error_message or "")
    return m.group(1).strip() if m else None


def extract_computed_observable_predicate(error_message: str | None) -> str | None:
    m = _COMPUTED_OBSERVABLE_RE.search(error_message or "")
    return m.group(1).strip() if m else None


def find_rules_using_helper(ir: dict, helper_name: str) -> list[dict[str, Any]]:
    """Rules where helper_name appears in IF, with THEN predicates on the same rule."""
    from pipeline.kb.json_ir import _collect_pred_atom_usages

    helper = (helper_name or "").strip()
    if not helper:
        return []
    then_by_rule: dict[int, list[str]] = {}
    usages: list[dict[str, Any]] = []
    rules = ir.get("rules") or []
    for u in _collect_pred_atom_usages(rules):
        if u.side == "then":
            then_by_rule.setdefault(u.rule_index, []).append(u.name)
    seen: set[tuple[int, str, bool]] = set()
    for u in _collect_pred_atom_usages(rules):
        if u.name != helper or u.side != "if":
            continue
        key = (u.rule_index, u.side, u.negated)
        if key in seen:
            continue
        seen.add(key)
        usages.append(
            {
                "rule_index": u.rule_index,
                "side": u.side,
                "negated": u.negated,
                "then_predicates": then_by_rule.get(u.rule_index, []),
                "then_legal_output_predicates": [],
            }
        )
    return usages


def classify_helper_kind_hint(name: str, description: str = "") -> str:
    """Primary kind tag; see composite_temporal_threshold_repair_hints for full hint list."""
    from pipeline.kb.composite_temporal_threshold_repair_hints import (
        classify_helper_kind_hints,
        primary_helper_kind_hint,
    )

    hints = classify_helper_kind_hints(name, description)
    if hints != ["unknown"]:
        return primary_helper_kind_hint(hints)
    blob = ((name or "") + " " + (description or "")).lower().replace("-", "_")
    if any(m in blob for m in _CLASSIFICATION_MARKERS):
        return "classification"
    if "helper" in blob or "condition" in blob:
        return "condition"
    return "unknown"


def _sym_meta(sym: dict) -> dict[str, Any]:
    return {
        "name": str(sym.get("name") or ""),
        "kind": str(sym.get("kind") or ""),
        "description": str(sym.get("description") or ""),
        "legal_output": sym.get("legal_output"),
        "output_category": str(sym.get("output_category") or ""),
    }


def symbol_table_has_legal_output_predicate(symbol_table: dict | None) -> bool:
    if not symbol_table:
        return False
    preds = list(symbol_table.get("predicates") or [])
    return any(
        predicate_represents_legal_effect_output(
            _sym_meta(p)["name"],
            description=_sym_meta(p)["description"],
            kind=_sym_meta(p)["kind"],
            legal_output=p.get("legal_output") if isinstance(p.get("legal_output"), bool) else None,
            output_category=_sym_meta(p)["output_category"],
        )
        for p in preds
        if isinstance(p, dict)
    )


def legal_effect_rules_repair_context(
    *,
    scope_metadata: dict | None,
    symbol_table: dict | None,
    error_message: str | None = None,
    merged_ir: dict | None = None,
    missing_helper_name: str | None = None,
) -> bool:
    if scope_metadata and scope_metadata.get("question_asks_legal_effect") is True:
        return True
    if symbol_table_has_legal_output_predicate(symbol_table):
        return True
    helper = missing_helper_name or extract_missing_helper_name(error_message)
    if helper and merged_ir and _helper_used_in_legal_output_rule(helper, merged_ir, symbol_table):
        return True
    return False


def _helper_used_in_legal_output_rule(
    helper_name: str,
    ir: dict,
    symbol_table: dict | None,
) -> bool:
    usages = find_rules_using_helper(ir, helper_name)
    if not usages:
        return False
    legal_preds = _legal_output_predicate_names(symbol_table)
    if not legal_preds:
        return False
    for u in usages:
        if u.get("then_legal_output_predicates"):
            return True
    return False


def _legal_output_predicate_names(symbol_table: dict | None) -> set[str]:
    out: set[str] = set()
    if not symbol_table:
        return out
    for p in symbol_table.get("predicates") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        meta = _sym_meta(p)
        if predicate_represents_legal_effect_output(
            meta["name"],
            description=meta["description"],
            kind=meta["kind"],
            legal_output=p.get("legal_output") if isinstance(p.get("legal_output"), bool) else None,
            output_category=meta["output_category"],
        ):
            out.add(meta["name"])
    return out


def _kind_specific_guidance(kind_hint: str) -> list[str]:
    if kind_hint == "threshold":
        return [
            "This helper looks threshold/exceedance-related.",
            "Define it with numeric compare literals on observable functions already in the symbol table.",
            "Preserve exact thresholds from scoped law text; do not invent numbers.",
            "Or inline the lower-level exceeded/within conditions directly in the legal-effect rule IF.",
        ]
    if kind_hint in {"temporal", "consecutive"}:
        return [
            "This helper looks temporal/consecutive-period-related.",
            "Define it from FinancialYear/period variables and lower-level facts for the current and prior period.",
            "For two consecutive years: relate fy to a predecessor year via existing symbols, or express both years explicitly.",
            "If no year predecessor function exists, define an intermediate helper for the prior year condition first.",
            "Or inline consecutive conditions using existing per-year helpers (e.g. exceeds_* for fy and prior fy).",
        ]
    if kind_hint == "classification":
        return [
            "This helper looks classification-related; keep it as support, not as the legal-effect answer.",
            "Define it from observables or lower helpers; do not replace the legal-effect predicate in THEN.",
        ]
    return [
        "Define the helper from observables/functions or lower-level helpers already declared.",
        "If it cannot be defined, remove the helper and inline lower-level conditions in the legal-effect rule.",
    ]


def build_missing_legal_effect_helper_supplement(
    *,
    error_message: str,
    symbol_table: dict | None,
    evidence: Any | None = None,
    law_text: str | None = None,
) -> str:
    """Mandatory rules-repair supplement for undefined helpers blocking legal-effect rules."""
    helper = (
        getattr(evidence, "helper_name", None)
        or extract_missing_helper_name(error_message)
        or "?"
    )
    kind_hint = getattr(evidence, "helper_kind_hint", None) or classify_helper_kind_hint(helper)
    legal_preds = getattr(evidence, "legal_output_predicates_in_then", None) or sorted(
        _legal_output_predicate_names(symbol_table)
    )
    used_rules = getattr(evidence, "used_in_rules", None) or []
    candidates = getattr(evidence, "candidate_lower_level_symbols", None) or []

    lines = [
        "You are repairing rules only.",
        "The legal-effect output predicate already exists in the symbol table.",
        "You must define all helper predicates used to derive it.",
        "",
        "Missing helper: %s (kind hint: %s)" % (helper, kind_hint),
    ]
    if legal_preds:
        lines.append(
            "Legal-effect predicate(s) to keep in THEN: " + ", ".join(legal_preds[:4])
        )
    if used_rules:
        lines.append("Helper used in rules:")
        for u in used_rules[:6]:
            idx = u.get("rule_index", "?")
            side = u.get("side", "if")
            neg = " (negated)" if u.get("negated") else ""
            then_preds = u.get("then_legal_output_predicates") or []
            tail = (
                " -> THEN legal output: " + ", ".join(then_preds)
                if then_preds
                else ""
            )
            lines.append("  - rules[%s].%s%s%s" % (idx, side, neg, tail))

    lines.extend(["", "Do:"])
    lines.extend(
        [
            "- Keep the legal-effect predicate in THEN of at least one rule.",
            "- Define every helper used in IF conditions (including nested helpers).",
            "- Add defining rules with the helper in THEN, built from lower-level symbols.",
        ]
    )
    lines.extend(_kind_specific_guidance(kind_hint))

    if candidates:
        lines.append("")
        lines.append("Candidate lower-level symbols (use these in definitions):")
        for c in candidates[:10]:
            lines.append(
                "  - %s  kind=%s  %s"
                % (
                    c.get("name", "?"),
                    c.get("kind", "?"),
                    (c.get("description") or "")[:80],
                )
            )

    lines.extend(
        [
            "",
            "Do not:",
            "- Create new symbols (rules repair only).",
            "- Delete the legal-effect rule or remove its THEN conclusion.",
            "- Turn the legal-effect predicate into a classification predicate.",
            "- Leave the helper undefined while keeping it in the legal-effect rule IF.",
        ]
    )
    if (law_text or "").strip():
        lines.append("- Preserve exact legal thresholds and timing wording from scoped law text.")
    return "\n".join(lines)


def build_legal_effect_computed_helper_supplement(
    *,
    error_message: str,
    symbol_table: dict | None,
    computed_predicate: str | None = None,
    computed_kind_hint: str | None = None,
    secondary_helpers: list[Any] | None = None,
) -> str:
    """Symbols-repair supplement when computed threshold helpers block a legal-effect KB."""
    subject = computed_predicate or extract_computed_observable_predicate(error_message) or "?"
    kind_hint = computed_kind_hint or classify_helper_kind_hint(subject)
    legal_preds = sorted(_legal_output_predicate_names(symbol_table))

    lines = [
        "This KB is trying to derive a legal effect.",
        "Threshold/consecutive helpers must be helper or derived symbols with defining rules — not observables.",
        "",
        "Computed observable flagged: %s (kind_hint=%s)" % (subject, kind_hint),
    ]
    if legal_preds:
        lines.append(
            "Preserve legal-effect predicate(s): " + ", ".join(legal_preds[:4])
        )
    lines.extend(
        [
            "",
            "Symbols repair (now):",
            "- Change computed threshold/exceedance/criteria predicates from observable to helper (or derived).",
            "- Do not use directly_observable=true for threshold compares unless a case may state them verbatim.",
            "- Keep numeric observable functions (amounts, counts) as observable.",
            "",
            "Rules repair (next, after symbols validate):",
            "- Define every helper used in IF, especially in the legal-effect rule.",
            "- Build threshold helpers from numeric compare literals on observable functions.",
            "- Build consecutive/temporal helpers from per-year conditions or period relations.",
            "- Inline lower-level conditions if a helper cannot be defined from existing symbols.",
        ]
    )
    if secondary_helpers:
        lines.append("")
        lines.append("Also undefined helpers already used in rules (fix after symbol kinds):")
        for ev in secondary_helpers[:6]:
            name = getattr(ev, "helper_name", None) or (ev.get("name") if isinstance(ev, dict) else "?")
            hint = getattr(ev, "helper_kind_hint", None) or (
                ev.get("helper_kind_hint") if isinstance(ev, dict) else "unknown"
            )
            legal = getattr(ev, "legal_output_predicates_in_then", None) or (
                ev.get("legal_output_predicates_in_then") if isinstance(ev, dict) else []
            )
            tail = " -> legal-effect rule" if legal else ""
            lines.append("  - %s (%s)%s" % (name, hint, tail))

    lines.extend(
        [
            "",
            "Do not:",
            "- Delete the legal-effect predicate or its rule.",
            "- Replace the legal-effect answer with classification predicates only.",
            "- Leave threshold helpers as observables.",
        ]
    )
    return "\n".join(lines)
