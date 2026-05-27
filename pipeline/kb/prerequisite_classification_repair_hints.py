"""Generic repair hints for undefined prerequisite status/classification predicates."""

from __future__ import annotations

import re
from typing import Any

from pipeline.kb.composite_predicate_heuristics import looks_status_classification_name

_DERIVED_NOT_DEFINED_RE = re.compile(
    r"(?i)derived predicate\(s\)\s+([a-z0-9_,\s]+)\s+never appear"
)
_MISSING_HELPER_RE = re.compile(
    r"(?i)(?:helper predicate|helper function)\s+'([^']+)'"
)
_DERIVED_IF_UNDEFINED_RE = re.compile(
    r"(?i)derived predicate '([^']+)' is used"
)


def _predicates_used_in_if(rules: list[Any]) -> dict[str, list[int]]:
    from pipeline.kb.json_ir import _collect_pred_atom_usages

    out: dict[str, list[int]] = {}
    for u in _collect_pred_atom_usages(rules):
        if u.side == "if":
            out.setdefault(u.name, []).append(u.rule_index)
    return out


def _if_prerequisites_for(rules: list[Any], target: str) -> set[str]:
    """Predicates referenced in IF of rules that also mention target in IF."""
    from pipeline.kb.json_ir import _collect_pred_atom_usages

    prereqs: set[str] = set()
    for u in _collect_pred_atom_usages(rules):
        if u.side != "if" or u.name == target:
            continue
        for u2 in _collect_pred_atom_usages(rules):
            if u2.side == "if" and u2.name == target and u2.rule_index == u.rule_index:
                prereqs.add(u.name)
                break
    return prereqs


def _missing_predicate_names(error_message: str | None) -> list[str]:
    if not error_message:
        return []
    m = _DERIVED_NOT_DEFINED_RE.search(error_message)
    if m:
        blob = m.group(1)
        return [x.strip() for x in blob.split(",") if x.strip()]
    m2 = _MISSING_HELPER_RE.search(error_message)
    if m2:
        return [m2.group(1).strip()]
    m3 = _DERIVED_IF_UNDEFINED_RE.search(error_message)
    if m3:
        return [m3.group(1).strip()]
    return []


def _symbol_meta(symbol_table: dict | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for p in (symbol_table or {}).get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            out[str(p["name"])] = p
    return out


def _circular_missing_prerequisites(
    missing: list[str],
    rules: list[Any],
) -> list[tuple[str, str]]:
    missing_set = set(missing)
    cycles: list[tuple[str, str]] = []
    for a in missing:
        for b in _if_prerequisites_for(rules, a):
            if b in missing_set and a in _if_prerequisites_for(rules, b):
                pair = tuple(sorted((a, b)))
                if pair not in cycles:
                    cycles.append(pair)  # type: ignore[arg-type]
    return cycles


def build_prerequisite_classification_supplement(
    *,
    error_message: str | None,
    symbol_table: dict | None,
    merged_ir: dict | None = None,
) -> str:
    """Repair supplement for undefined derived/helper predicates used as prerequisites."""
    names = _missing_predicate_names(error_message)
    if not names:
        return ""
    rules: list[Any] = []
    if merged_ir and isinstance(merged_ir.get("rules"), list):
        rules = merged_ir["rules"]
    if_usages = _predicates_used_in_if(rules)
    meta = _symbol_meta(symbol_table)
    status_like = [n for n in names if looks_status_classification_name(n)]

    lines = [
        "=== PREREQUISITE STATUS / CLASSIFICATION CLOSURE ===",
        "Missing predicate(s): " + ", ".join(names) + ".",
    ]
    for n in names:
        idxs = if_usages.get(n)
        if idxs is not None:
            lines.append(
                "- '%s' appears in IF of rule(s) %s but has no defining THEN rule."
                % (n, ", ".join(str(i) for i in sorted(set(idxs))))
            )
        sym = meta.get(n) or {}
        kind = str(sym.get("kind") or "")
        legal_out = bool(sym.get("legal_output"))
        directly_obs = bool(sym.get("directly_observable"))
        if kind in ("observable", "background"):
            lines.append(
                "- '%s' is kind=%s in SYMBOL_TABLE; it should not require a derived THEN "
                "definition unless misclassified."
                % (n, kind)
            )
        elif looks_status_classification_name(n) and not legal_out:
            lines.append(
                "- '%s' looks like a prerequisite/background status (not the final legal output). "
                "If a case can directly assert it and the scoped law does not define it further, "
                "reclassify as kind=observable with directly_observable=true (returns=Bool, not legal_output). "
                "Otherwise define it in THEN from observable subconditions available in the scoped law, "
                "or remove it from IF and fold only locally available conditions into the target rule."
                % n
            )
        else:
            lines.append(
                "- '%s': if the scoped law defines this predicate, add rules with it in THEN from "
                "observable facts/functions. If the law does not define it and it is not a "
                "case-supplied background fact, remove it from IF."
                % n
            )
    lines.append(
        "If a positive legal-output rule already contains local operational criteria, do not block it "
        "on an unsupported broader observable status prerequisite. Remove that unsupported prerequisite "
        "instead of introducing inverse negative exclusions from not broader_status."
    )

    if status_like:
        lines.append(
            "Status/classification-style prerequisites: distinguish final legal conclusions (derived, "
            "defined from subconditions or queried as the answer) from background facts the case may "
            "assert directly (observable with directly_observable=true when status-like)."
        )

    cycles = _circular_missing_prerequisites(names, rules)
    if cycles:
        for a, b in cycles:
            lines.append(
                "- Circular dependency risk between '%s' and '%s': do not define each from the other. "
                "Break the cycle by using observable subconditions, reclassifying a background status "
                "as observable/directly_observable, or removing an unsupported prerequisite from IF."
                % (a, b)
            )
    else:
        lines.append(
            "Do not create circular definitions between prerequisite statuses (A defined only from B "
            "while B is also undefined in IF)."
        )

    return "\n".join(lines)
