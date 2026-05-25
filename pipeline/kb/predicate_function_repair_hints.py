"""Repair hints when predicates and functions are misused (Task D)."""

from __future__ import annotations

import re

_RE_FN_AS_PRED = re.compile(
    r"Rules use '([^']+)' as a Bool predicate atom, but the symbol table lists it only under functions",
    re.IGNORECASE,
)
_RE_PRED_AS_FN = re.compile(
    r"rules\[\d+\] uses predicate '([^']+)' as a function term",
    re.IGNORECASE,
)


def extract_misused_function_name(error_message: str) -> str | None:
    m = _RE_FN_AS_PRED.search(error_message or "")
    return m.group(1).strip() if m else None


def extract_misused_predicate_name(error_message: str) -> str | None:
    m = _RE_PRED_AS_FN.search(error_message or "")
    return m.group(1).strip() if m else None


def build_predicate_function_misuse_supplement(
    error_message: str,
    *,
    symbol_table: dict | None = None,
) -> str:
    fn_name = extract_misused_function_name(error_message)
    pred_name = extract_misused_predicate_name(error_message)
    if fn_name:
        return _function_used_as_predicate_hint(fn_name, symbol_table=symbol_table)
    if pred_name:
        return _predicate_used_as_function_hint(pred_name, symbol_table=symbol_table)
    return _function_used_as_predicate_hint("F", symbol_table=symbol_table)


def _function_used_as_predicate_hint(name: str, *, symbol_table: dict | None) -> str:
    lines = [
        "FUNCTION / PREDICATE MISUSE — REQUIRED FIX",
        "",
        "Symbol '%s' is declared as a FUNCTION (returns a value), but rules use it as a Bool predicate atom."
        % name,
        "",
        "Do:",
        '- Use compare with the function on left/right only, e.g. '
        '{"compare": {"left": {"func": "%s", "args": ["c", "fy"]}, "op": ">", "right": N}}' % name,
        "- For a legal NO conclusion on a predicate C, use THEN: "
        '{"pred": "C", "args": ["c", "fy"], "negated": true}',
        "",
        "Do NOT:",
        '- Write {"pred": "%s", ...} when %s is only in functions.' % (name, name),
        "- Write %s(c,fy) = false or assign false to a predicate." % name,
        "- Reclassify a numeric function as predicate unless the case truly states a yes/no fact with that name.",
    ]
    if symbol_table:
        for p in symbol_table.get("predicates") or []:
            if not isinstance(p, dict):
                continue
            pn = str(p.get("name") or "")
            if name.lower() in pn.lower() and str(p.get("returns") or "").lower() == "bool":
                lines.append(
                    "- Related predicate already exists: %s (%s) — use that for Bool conditions."
                    % (pn, " * ".join(p.get("args") or []))
                )
                break
    return "\n".join(lines)


def _predicate_used_as_function_hint(name: str, *, symbol_table: dict | None) -> str:
    lines = [
        "PREDICATE / FUNCTION MISUSE — REQUIRED FIX",
        "",
        "Symbol '%s' is declared as a PREDICATE (Bool), but rules use it as a function term."
        % name,
        "",
        "Do:",
        '- Use P(args) or negated P(args) in IF/THEN: {"pred": "%s", "args": ["c"], "negated": false}' % name,
        "- For numeric thresholds, use a function from SYMBOL_TABLE inside compare left/right.",
        "",
        "Do NOT:",
        '- Write {"func": "%s", ...} when %s is a predicate.' % (name, name),
        "- Write %s(args) = value — predicates are not functions." % name,
    ]
    if symbol_table:
        for f in symbol_table.get("functions") or []:
            if not isinstance(f, dict):
                continue
            fn = str(f.get("name") or "")
            if name.lower() in fn.lower():
                lines.append(
                    "- Related function exists: %s -> %s — use inside compare only."
                    % (fn, f.get("returns") or "Real")
                )
                break
    return "\n".join(lines)
