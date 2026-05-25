"""
Deterministic threshold-classification repair scaffolds and gap analysis (law-agnostic).
"""

from __future__ import annotations

import json
import re
from typing import Any

from pipeline.kb.json_ir import (
    _collect_pred_atom_usages,
    _predicates_defined_in_then,
    _rule_expr_sides,
)
from pipeline.kb.law_numeric_literals import extract_numeric_values_from_law_text
from pipeline.kb.threshold_cardinality import _AT_LEAST_TWO_PRED_RE, _is_pairwise_or_of_thresholds
from pipeline.kb.threshold_classification_negative import (
    _if_has_non_negated_at_least_two_helper,
    _if_has_non_negated_pairwise_exceeded,
    _rule_has_exclusion_disqualification,
)

_CRITERION_EXCEEDED_RE = re.compile(
    r"(?i)(criterion|criteria|threshold).*(exceed|exceeded)|"
    r"(exceed|exceeded).*(criterion|criteria|threshold|employee|turnover|balance)"
)
_MORE_THAN_ONE_RE = re.compile(
    r"(?i)(more_than_one|at_least_two|two_or_more|meer_dan_een|minstens_twee)"
)
_CLASSIFICATION_RE = re.compile(
    r"(?i)^(is_)?(small|micro|medium|large)_company$|^(small|micro)_company$"
)
_PRED_AS_FN_RE = re.compile(
    r"Rules use '([^']+)' as a Bool predicate atom, but the symbol table lists it only under functions",
    re.IGNORECASE,
)


def _sym_list(symbol_table: dict | None, key: str) -> list[dict]:
    if not symbol_table:
        return []
    out = []
    for item in symbol_table.get(key) or []:
        if isinstance(item, dict) and item.get("name"):
            out.append(item)
    return out


def _signature(sym: dict) -> str:
    args = sym.get("args") or []
    returns = str(sym.get("returns") or "Bool").strip()
    if args:
        return "%s -> %s" % (" * ".join(str(a) for a in args), returns)
    return "() -> %s" % returns


def _is_classification_predicate(name: str, sym: dict) -> bool:
    if str(sym.get("kind") or "").lower() != "derived":
        return False
    if sym.get("legal_output") is True:
        return True
    cat = str(sym.get("output_category") or "").lower()
    if cat in {"classification", "status", "legal_classification"}:
        return True
    return bool(_CLASSIFICATION_RE.search(name or ""))


def collect_criterion_exceeded_helpers(
    symbol_table: dict | None,
    *,
    classification_predicate: str | None = None,
) -> list[dict[str, str]]:
    """Per-criterion exceeded helpers (employee/turnover/balance style)."""
    out: list[dict[str, str]] = []
    blob_hint = (classification_predicate or "").lower()
    for p in _sym_list(symbol_table, "predicates"):
        name = str(p.get("name") or "")
        kind = str(p.get("kind") or "")
        if kind != "helper":
            continue
        desc = str(p.get("description") or "")
        if _CRITERION_EXCEEDED_RE.search(name + " " + desc):
            if classification_predicate:
                blob = blob_hint
                if "micro" in blob and "small" in name and "micro" not in name:
                    continue
                if "small" in blob and "micro" in name and "small" not in name:
                    continue
            out.append({"name": name, "signature": _signature(p), "kind": kind})
    return out


def collect_counting_helpers(symbol_table: dict | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for p in _sym_list(symbol_table, "predicates"):
        name = str(p.get("name") or "")
        if str(p.get("kind") or "") != "helper":
            continue
        if _MORE_THAN_ONE_RE.search(name) or _AT_LEAST_TWO_PRED_RE.search(name):
            out.append({"name": name, "signature": _signature(p), "kind": "helper"})
    return out


def collect_numeric_functions(symbol_table: dict | None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for f in _sym_list(symbol_table, "functions"):
        name = str(f.get("name") or "")
        kind = str(f.get("kind") or "observable")
        if kind not in {"observable", "helper"}:
            continue
        desc = str(f.get("description") or "").lower()
        if any(
            tok in (name + " " + desc).lower()
            for tok in ("employee", "turnover", "balance", "fte", "omzet", "balans")
        ):
            out.append({"name": name, "signature": _signature(f), "kind": kind})
    return out


def pick_classification_predicate(
    symbol_table: dict | None,
    *,
    query_predicate: str | None = None,
    error_message: str | None = None,
) -> str | None:
    if query_predicate:
        return query_predicate
    from pipeline.kb.exclusion_repair_hints import extract_classification_predicates

    preds = extract_classification_predicates(error_message or "")
    if preds:
        return preds[0]
    for p in _sym_list(symbol_table, "predicates"):
        if _is_classification_predicate(str(p.get("name") or ""), p):
            return str(p["name"])
    return None


def _analyze_rules_for_classification(
    rules: list,
    classification: str,
    pred_kinds: dict[str, str],
) -> dict[str, Any]:
    positive_present = False
    negative_present = False
    negative_usable = False
    for raw_rule in rules:
        if not isinstance(raw_rule, dict):
            continue
        if_side, then_side = _rule_expr_sides(raw_rule)
        for u in _collect_pred_atom_usages([raw_rule]):
            if u.side == "then" and u.name == classification:
                if u.negated:
                    negative_present = True
                    if _if_has_non_negated_at_least_two_helper(if_side) or _if_has_non_negated_pairwise_exceeded(
                        if_side
                    ):
                        negative_usable = True
                else:
                    positive_present = True
        if classification and _rule_has_exclusion_disqualification(raw_rule, {classification}):
            negative_present = True
            negative_usable = True
    return {
        "positive_rule_present": positive_present,
        "negative_rule_present": negative_present,
        "negative_rule_usable": negative_usable,
    }


def find_pred_used_as_function_errors(symbol_table: dict | None, rules: list) -> list[dict[str, str]]:
    fun_names = {str(f.get("name") or "") for f in _sym_list(symbol_table, "functions")}
    pred_names = {str(p.get("name") or "") for p in _sym_list(symbol_table, "predicates")}
    errors: list[dict[str, str]] = []
    for name in sorted(fun_names):
        if name in pred_names:
            continue
        for rule in rules or []:
            if not isinstance(rule, dict):
                continue
            blob = json.dumps(rule, ensure_ascii=False)
            if re.search(r'"(?:pred|symbol)"\s*:\s*"%s"' % re.escape(name), blob):
                errors.append(
                    {
                        "symbol": name,
                        "issue": "predicate_used_as_function",
                        "hint": (
                            "Declare '%s' as predicate with returns Bool, or use {%s(...)} only inside "
                            "compare left/right — never as a Bool atom."
                        )
                        % (name, name),
                    }
                )
                break
    return errors


def build_threshold_exclusion_gap_report(
    merged_ir: dict,
    symbol_table: dict | None,
    *,
    query_predicate: str | None = None,
    error_message: str | None = None,
    law_text: str | None = None,
) -> dict[str, Any]:
    """Structured gap report for threshold classification / exclusion (Task A)."""
    rules = merged_ir.get("rules") or []
    pred_kinds: dict[str, str] = {}
    for p in _sym_list(symbol_table, "predicates"):
        pred_kinds[str(p["name"])] = str(p.get("kind") or "helper")
    for f in _sym_list(symbol_table, "functions"):
        pred_kinds[str(f["name"])] = str(f.get("kind") or "observable")

    classification = pick_classification_predicate(
        symbol_table, query_predicate=query_predicate, error_message=error_message
    )
    threshold_helpers = collect_criterion_exceeded_helpers(
        symbol_table, classification_predicate=classification
    )
    counting = collect_counting_helpers(symbol_table)
    counting_helper = counting[0]["name"] if counting else None
    if classification and counting:
        for c in counting:
            if classification.replace("_company", "") in c["name"] or classification.split("_")[0] in c["name"]:
                counting_helper = c["name"]
                break

    rule_info = _analyze_rules_for_classification(rules, classification or "", pred_kinds)
    defined_then = _predicates_defined_in_then(rules)
    missing_defs = []
    for u in _collect_pred_atom_usages(rules):
        if u.side != "if":
            continue
        kind = pred_kinds.get(u.name, "")
        if kind == "helper" and u.name not in defined_then:
            if u.name not in missing_defs:
                missing_defs.append(u.name)

    numeric_fns = collect_numeric_functions(symbol_table)
    law_nums = sorted(extract_numeric_values_from_law_text(law_text or ""))
    case_facts = []
    if threshold_helpers:
        case_facts.append(
            "Numeric function assignments for: "
            + ", ".join(t["name"] for t in threshold_helpers[:3])
            + " (to derive exceeded helpers)."
        )
    if counting_helper:
        case_facts.append(
            "After exceeded helpers are known, %s must be derivable or asserted for false classification."
            % counting_helper
        )
    if classification and rule_info.get("negative_rule_usable"):
        case_facts.append(
            "Exclusion rule should prove NOT %s when %s holds."
            % (classification, counting_helper or "at_least_two_exceeded")
        )
    elif classification:
        case_facts.append(
            "Missing usable exclusion: need %s => NOT %s with negated predicate in THEN."
            % (counting_helper or "pairwise_exceeded", classification)
        )

    repair_pattern = "pairwise_counting_plus_exclusion"
    if not threshold_helpers and not numeric_fns:
        repair_pattern = "symbols_repair_needed"
    elif not threshold_helpers and numeric_fns:
        repair_pattern = "define_exceeded_from_numeric_then_counting_then_exclusion"

    return {
        "classification_predicate": classification,
        "threshold_helpers": [t["name"] for t in threshold_helpers],
        "threshold_helper_signatures": threshold_helpers,
        "counting_helper": counting_helper,
        "counting_helpers": [c["name"] for c in counting],
        "numeric_functions": [f["name"] for f in numeric_fns[:12]],
        "law_numeric_literals": law_nums[:20],
        "positive_rule_present": rule_info["positive_rule_present"],
        "negative_rule_present": rule_info["negative_rule_present"],
        "negative_rule_usable": rule_info["negative_rule_usable"],
        "missing_definitions": missing_defs,
        "pred_used_as_function_errors": find_pred_used_as_function_errors(symbol_table, rules),
        "case_facts_needed_for_false": case_facts,
        "recommended_repair_pattern": repair_pattern,
    }


def _pairwise_or_template(t_names: list[str], var_company: str = "c", var_period: str = "y") -> dict:
    pairs = []
    for i in range(len(t_names)):
        for j in range(i + 1, len(t_names)):
            pairs.append(
                {
                    "and": [
                        {"pred": t_names[i], "args": [var_company, var_period], "negated": False},
                        {"pred": t_names[j], "args": [var_company, var_period], "negated": False},
                    ]
                }
            )
    return {"or": pairs} if pairs else {}


def build_threshold_exclusion_repair_scaffold(
    symbol_table: dict | None,
    merged_ir: dict | None = None,
    *,
    error_message: str | None = None,
    law_text: str | None = None,
    query_predicate: str | None = None,
    missing_helper_name: str | None = None,
) -> str:
    """
    Concrete rules-repair scaffold using exact symbol names from the symbol table (Task B).
    """
    gap = build_threshold_exclusion_gap_report(
        merged_ir or {"rules": []},
        symbol_table,
        query_predicate=query_predicate,
        error_message=error_message,
        law_text=law_text,
    )
    classification = gap.get("classification_predicate") or "classification"
    t_helpers = gap.get("threshold_helper_signatures") or []
    t_names = [t["name"] for t in t_helpers]
    counting = gap.get("counting_helper") or "at_least_two_criteria_exceeded"
    counting_sig = ""
    for c in _sym_list(symbol_table, "predicates"):
        if str(c.get("name")) == counting:
            counting_sig = _signature(c)
            break
    law_nums = gap.get("law_numeric_literals") or []
    numeric_fns = gap.get("numeric_functions") or []

    lines = [
        "THRESHOLD EXCLUSION REPAIR SCAFFOLD (use exact symbol names below)",
        "",
        "Classification predicate C: %s" % classification,
        "Counting helper H: %s (%s)" % (counting, counting_sig or "helper"),
        "Per-criterion exceeded helpers:",
    ]
    if t_names:
        for t in t_helpers:
            lines.append("  - %s (%s)" % (t["name"], t.get("signature", "")))
    else:
        lines.append("  (none declared — define from numeric functions first)")
    if law_nums:
        lines.append("Law-text numeric literals (preserve exactly): %s" % ", ".join(str(n) for n in law_nums[:12]))
    if numeric_fns:
        lines.append("Observable numeric functions: %s" % ", ".join(numeric_fns[:8]))

    if not t_names and not numeric_fns:
        lines.extend(
            [
                "",
                "STOP: symbol table lacks threshold-exceeded helpers and numeric functions.",
                "Escalate to SYMBOLS repair — add observable numeric functions and helper exceeded predicates.",
            ]
        )
        return "\n".join(lines)

    if not t_names and numeric_fns:
        lines.extend(
            [
                "",
                "Step 1 — Define per-criterion exceeded helpers in THEN from compares, e.g.:",
                "  employee_criterion_exceeded(c,y) :- compare(annual_average_employees_fte(c,y), >, THRESHOLD_FROM_LAW).",
                "Use only thresholds present in scoped law text.",
            ]
        )

    if len(t_names) >= 2:
        lines.extend(
            [
                "",
                "Step 2 — Define counting helper H in THEN with pairwise conjunctions (required):",
                "  IF: (T1 & T2) OR (T1 & T3) OR (T2 & T3)  [use exact helper names above]",
                "  THEN: H(c, y)",
                "JSON_IR IF shape:",
                json.dumps(_pairwise_or_template(t_names), indent=2),
            ]
        )
    elif missing_helper_name and _MORE_THAN_ONE_RE.search(missing_helper_name or ""):
        lines.extend(
            [
                "",
                "Step 2 — Define missing counting helper '%s' in THEN using pairwise exceeded helpers."
                % missing_helper_name,
            ]
        )

    lines.extend(
        [
            "",
            "Step 3 — Add EXCLUSION rule (mandatory for false-case proofs):",
            "  IF: H(c, y)   [non-negated counting helper in IF]",
            "  THEN: { pred: \"%s\", args: [\"c\", \"y\"], negated: true }" % classification,
            "Do NOT write: H => %s with negated false (predicates are Bool, not functions)." % classification,
            "Do NOT use: A OR B OR C => NOT %s (simple OR is invalid for at-most-one laws)." % classification,
            "Do NOT mix parent/subsidiary observables into the same OR as threshold exclusion unless the law requires it.",
            "",
            "Step 4 — Positive qualification (only if not already present):",
            "  IF: has_legal_personality(c) AND NOT H(c,y) [and other legal conditions]",
            "  THEN: %s(c, y)  [non-negated]" % classification,
            "",
            "Open-world note: absence of H must NOT be used to prove NOT %s; the exclusion rule must derive it."
            % classification,
        ]
    )

    if missing_helper_name and missing_helper_name in t_names:
        lines.extend(
            [
                "",
                "Missing helper '%s': add a THEN rule with compare(...) from a numeric function."
                % missing_helper_name,
            ]
        )

    return "\n".join(lines)


def build_threshold_helper_pairwise_scaffold(
    symbol_table: dict | None,
    *,
    helper_name: str,
    law_text: str | None = None,
) -> str:
    """Pairwise scaffold when missing_helper_definition targets a counting helper (Task D)."""
    return build_threshold_exclusion_repair_scaffold(
        symbol_table,
        merged_ir={"rules": []},
        law_text=law_text,
        missing_helper_name=helper_name,
    )
