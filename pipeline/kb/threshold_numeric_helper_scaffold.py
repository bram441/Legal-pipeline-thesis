"""
Deterministic repair scaffolds for missing Real/Int threshold helper functions.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pipeline.kb.json_ir import (
    _collect_helper_symbol_usage,
    _helper_functions_defined_in_then,
    _iter_function_refs,
    _iter_rule_compare_nodes,
    _function_name_from_term,
    _normalize_compare_op,
)
from pipeline.kb.law_numeric_literals import (
    extract_numeric_values_from_law_text,
    is_logical_small_constant,
    numeric_value_matches_law,
)

_THRESHOLD_FN_RE = re.compile(
    r"(?i)(threshold|_limit|_cap|adjusted_.*threshold|.*_threshold$|.*_limit$)"
)
_CASE_VALUE_FN_MARKERS = (
    "annual_average",
    "annual_net",
    "net_turnover",
    "balance_sheet_total",
    "number_of_employee",
    "employees_fte",
    "turnover_excluding",
    "effective_",
    "applicable_",
    "for_threshold",
    "for_thresholds",
    "_employees_",
    "_employee_",
    "consolidated_annual",
    "consolidated_net",
    "consolidated_balance",
    "operating_and_financial",
    "income_not_meeting",
    "financial_year_duration",
)


def _sym_functions(symbol_table: dict | None) -> list[dict]:
    if not symbol_table:
        return []
    return [f for f in (symbol_table.get("functions") or []) if isinstance(f, dict) and f.get("name")]


def _sym_by_name(symbol_table: dict | None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for section in ("predicates", "functions"):
        for sym in (symbol_table or {}).get(section) or []:
            if isinstance(sym, dict) and sym.get("name"):
                out[str(sym["name"])] = sym
    return out


def looks_like_threshold_helper_function(name: str, description: str = "") -> bool:
    blob = ((name or "") + " " + (description or "")).lower()
    if _THRESHOLD_FN_RE.search(name or ""):
        return True
    if "threshold" in blob and ("adjusted" in blob or "applicable" in blob or "limit" in blob):
        return True
    return False


def looks_like_case_value_function(name: str, description: str = "") -> bool:
    blob = ((name or "") + " " + (description or "")).lower()
    if looks_like_threshold_helper_function(name, description):
        return False
    if any(m in blob for m in _CASE_VALUE_FN_MARKERS):
        return True
    if "annual_average" in blob and "threshold" not in blob and "limit" not in blob:
        return True
    if re.search(r"(?i)(applicable|effective|estimated|consolidated).*(employee|turnover|balance)", blob):
        if "threshold" not in blob and "limit" not in blob:
            return True
    return False


def _threshold_kind_from_name(name: str) -> str | None:
    n = (name or "").lower()
    if "employee" in n or "fte" in n:
        return "employee"
    if "turnover" in n or "omzet" in n:
        return "turnover"
    if "balance" in n or "balans" in n:
        return "balance_sheet"
    return None


def _size_from_name(name: str) -> str | None:
    n = (name or "").lower()
    if "micro" in n:
        return "micro"
    if "small" in n:
        return "small"
    return None


def _candidate_law_thresholds(law_text: str | None) -> list[float]:
    raw = extract_numeric_values_from_law_text(law_text)
    return sorted(
        v for v in raw if not is_logical_small_constant(v) and (v >= 100 or v in {10.0, 50.0})
    )


def suggest_law_literals_for_function(
    name: str,
    description: str = "",
    *,
    law_text: str | None = None,
) -> tuple[list[float], list[float], bool]:
    """
    Return (likely_literals, all_candidates, ambiguous).
    likely_literals empty when ambiguous among multiple name-matched candidates.
    """
    candidates = _candidate_law_thresholds(law_text)
    kind = _threshold_kind_from_name(name)
    size = _size_from_name(name)
    if not kind or not candidates:
        return [], candidates, bool(candidates) and len(candidates) > 1

    # Name-directed filter (micro/small × employee/turnover/balance)
    name_matched: list[float] = []
    for v in candidates:
        iv = int(v) if v == int(v) else None
        if kind == "employee":
            if size == "micro" and v == 10:
                name_matched.append(v)
            elif size == "small" and v == 50:
                name_matched.append(v)
            elif size is None and iv in {10, 50}:
                name_matched.append(v)
        elif kind == "turnover":
            if size == "micro" and v in {900_000.0, 900000.0}:
                name_matched.append(v)
            elif size == "small" and v in {11_250_000.0, 11250000.0, 6_000_000.0, 6000000.0}:
                name_matched.append(v)
            elif size is None and v >= 900_000:
                name_matched.append(v)
        elif kind == "balance_sheet":
            if size == "micro" and v in {450_000.0, 450000.0}:
                name_matched.append(v)
            elif size == "small" and v in {4_500_000.0, 4500000.0}:
                name_matched.append(v)
            elif size is None and v >= 450_000:
                name_matched.append(v)

    name_matched = sorted(set(name_matched))
    if len(name_matched) == 1:
        return name_matched, candidates, False
    if len(name_matched) > 1:
        return [], candidates, True
    # no name match — ambiguous if multiple candidates
    if len(candidates) > 1:
        return [], candidates, True
    if len(candidates) == 1:
        return candidates, candidates, False
    return [], [], False


def _comparison_usages(rules: list, fn_name: str) -> list[dict[str, Any]]:
    usages: list[dict[str, Any]] = []
    for idx, raw_rule in enumerate(rules or []):
        if not isinstance(raw_rule, dict):
            continue
        if_side, then_side = raw_rule.get("if", []), raw_rule.get("then", [])
        for side_name, side in (("if", if_side), ("then", then_side)):
            for comp in _iter_rule_compare_nodes(side):
                left, right = comp.get("left"), comp.get("right")
                for term in (left, right):
                    if _function_name_from_term(term) == fn_name:
                        usages.append(
                            {
                                "rule_index": idx,
                                "side": side_name,
                                "op": comp.get("op"),
                                "compare": comp,
                            }
                        )
    return usages


def build_threshold_numeric_helper_gap_report(
    merged_ir: dict,
    symbol_table: dict | None,
    *,
    law_text: str | None = None,
) -> dict[str, Any]:
    rules = merged_ir.get("rules") or []
    pred_kinds = {p["name"]: p.get("kind", "") for p in (symbol_table or {}).get("predicates") or [] if isinstance(p, dict)}
    fun_kinds = {f["name"]: f.get("kind", "") for f in _sym_functions(symbol_table)}
    _, in_if_f, _, _ = _collect_helper_symbol_usage(rules, pred_kinds, fun_kinds)
    defined_f, def_rules = _helper_functions_defined_in_then(rules, fun_kinds)
    missing = sorted(in_if_f - defined_f)
    by_name = _sym_by_name(symbol_table)
    law_candidates = _candidate_law_thresholds(law_text)

    missing_entries: list[dict[str, Any]] = []
    non_definable: list[str] = []
    ambiguous_all: list[str] = []

    for name in missing:
        sym = by_name.get(name) or {}
        desc = str(sym.get("description") or "")
        if looks_like_case_value_function(name, desc):
            non_definable.append(name)
            continue
        likely, candidates, ambiguous = suggest_law_literals_for_function(
            name, desc, law_text=law_text
        )
        if ambiguous:
            ambiguous_all.append(name)
        missing_entries.append(
            {
                "name": name,
                "args": sym.get("args") or [],
                "returns": sym.get("returns") or "Real",
                "kind": sym.get("kind") or fun_kinds.get(name, "helper"),
                "description": desc,
                "comparison_usages": _comparison_usages(rules, name),
                "defined_in_then_equality": name in defined_f,
                "definition_rule_indices": def_rules.get(name, []),
                "candidate_law_literals": candidates,
                "likely_definition_literals": likely,
                "ambiguous_threshold": ambiguous,
            }
        )

    pattern = "then_compare_equality_with_law_literal"
    if ambiguous_all:
        pattern = "numeric_threshold_ambiguous"
    elif non_definable and missing_entries:
        pattern = "mixed_numeric_helper_closure"

    return {
        "missing_numeric_helpers": missing_entries,
        "comparison_usages": {e["name"]: e["comparison_usages"] for e in missing_entries},
        "candidate_law_literals": law_candidates,
        "likely_definition_literals": {
            e["name"]: e["likely_definition_literals"] for e in missing_entries
        },
        "ambiguous_thresholds": ambiguous_all,
        "non_definable_case_value_functions": non_definable,
        "recommended_repair_pattern": pattern,
    }


def build_numeric_threshold_helper_scaffold(
    symbol_table: dict | None,
    *,
    helper_name: str,
    law_text: str | None = None,
    merged_ir: dict | None = None,
) -> str:
    by_name = _sym_by_name(symbol_table)
    sym = by_name.get(helper_name) or {}
    desc = str(sym.get("description") or "")
    args = sym.get("args") or ["Company", "FinancialYear"]
    returns = str(sym.get("returns") or "Real")
    arg_vars = ["c", "fy"] if len(args) >= 2 else (["c"] if args else [])

    if looks_like_case_value_function(helper_name, desc):
        return (
            "NUMERIC CASE-VALUE HELPER: '%s' is a computed case metric, NOT a law threshold.\n"
            "Do NOT define it with a law literal in THEN.\n"
            "If it must be closed, define in THEN by equality to an observable metric function, e.g.:\n"
            '  {"compare": {"left": {"func": "%s", "args": ["c", "fy"]}, "op": "=", '
            '"right": {"func": "annual_average_employees_fte", "args": ["c", "fy"]}}}\n'
            "Prefer using the observable metric directly in IF compares when no adjustment is legally required."
            % (helper_name, helper_name)
        )

    likely, candidates, ambiguous = suggest_law_literals_for_function(
        helper_name, desc, law_text=law_text
    )
    lines = [
        "NUMERIC THRESHOLD HELPER SCAFFOLD",
        "",
        "Missing helper function: %s" % helper_name,
        "Signature: %s -> %s" % (" * ".join(str(a) for a in args), returns),
        "Law-text numeric candidates: %s" % ", ".join(str(v) for v in candidates[:12]),
    ]

    if ambiguous:
        lines.extend(
            [
                "",
                "AMBIGUOUS: multiple law literals could match this function name.",
                "Choose the literal that matches the symbol name/description and scoped law article.",
                "Candidates: %s" % ", ".join(str(v) for v in candidates),
                "If still ambiguous after context check, validation may fail with numeric_threshold_ambiguous.",
            ]
        )
    elif likely:
        lit = likely[0]
        lit_json = int(lit) if lit == int(lit) and returns.lower() == "int" else lit
        lines.extend(
            [
                "",
                "Define in THEN using existing compare-in-THEN support (required):",
                json.dumps(
                    {
                        "forall": [{"var": "c", "type": args[0] if args else "Company"}]
                        + ([{"var": "fy", "type": args[1]}] if len(args) > 1 else []),
                        "if": [],
                        "then": [
                            {
                                "compare": {
                                    "left": {"func": helper_name, "args": arg_vars},
                                    "op": "=",
                                    "right": lit_json,
                                }
                            }
                        ],
                        "operator": "implies",
                    },
                    indent=2,
                ),
                "",
                "Use this literal (from scoped law text): %s" % lit_json,
                "Then use in IF compares, e.g.:",
                "  compare({func: annual_average_employees_fte, ...}, <=, {func: %s, ...})"
                % helper_name,
            ]
        )
    else:
        lines.extend(
            [
                "",
                "No unique law literal inferred. Pick a threshold from scoped law text only.",
                "Define with THEN compare equality as above.",
            ]
        )

    if merged_ir:
        for u in _comparison_usages(merged_ir.get("rules") or [], helper_name):
            if u.get("side") != "then" or u.get("op") != "=":
                continue
            comp = u.get("compare") or {}
            if _function_name_from_term(comp.get("right")) or _function_name_from_term(comp.get("left")):
                lines.extend(
                    [
                        "",
                        "NOTE: Existing THEN compare uses another function, not a law literal.",
                        "That does NOT close the helper. Use compare equality to a law-text numeric literal.",
                    ]
                )
                break

    lines.extend(
        [
            "",
            "Do NOT:",
            "- use %s as a Bool predicate atom;" % helper_name,
            "- assign false/true to predicates;",
            "- define case-value functions (annual_average_employees_fte, net_turnover_excluding_vat) from law literals.",
            "- invent thresholds not present in scoped law text.",
        ]
    )
    return "\n".join(lines)
