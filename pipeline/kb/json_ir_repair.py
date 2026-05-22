"""JSON-IR validation error classification and repair-loop helpers."""

from __future__ import annotations

import re
from enum import Enum


SCHEMA_DESIGN_TAG = "JSON_IR_SCHEMA_DESIGN_ERROR"
RULE_DESIGN_TAG = "JSON_IR_RULE_DESIGN_ERROR"


class JsonIRErrorKind(Enum):
    SYMBOLS_REPAIR_REQUIRED = "symbols_repair_required"
    RULES_REPAIR_ONLY = "rules_repair_only"
    CASE_REPAIR_ONLY = "case_repair_only"
    QUERY_REPAIR_ONLY = "query_repair_only"
    FATAL_RENDERER_BUG = "fatal_renderer_bug"


_RE_PRED_TYPE_MISMATCH = re.compile(
    r"argument\s+(\d+)\s+to\s+predicate\s+'([^']+)'\s+expects\s+type\s+([^,]+),\s+got\s+([^.\s]+)",
    re.IGNORECASE,
)
_RE_FN_TYPE_MISMATCH = re.compile(
    r"argument\s+(\d+)\s+to\s+'([^']+)'\s+expects\s+type\s+([^,]+),\s+got\s+([^.\s]+)",
    re.IGNORECASE,
)
_RE_UNBOUND = re.compile(r"unbound identifier\s+'([^']+)'", re.IGNORECASE)
_RE_RULE_IDX = re.compile(r"rules\[(\d+)\]")


def normalize_error_signature(msg: str) -> str:
    """Stable key for repeated-error escalation (drops indices where useful)."""
    s = (msg or "").strip()
    sl = s.lower()
    if SCHEMA_DESIGN_TAG.lower() in sl:
        if "observable predicate" in sl and "consequent" in sl:
            m = re.search(r"observable predicate\s+'([^']+)'", s, re.I)
            return "schema::observable_in_then::" + (m.group(1) if m else "?")
        if "no derived legal outputs" in sl:
            return "schema::no_derived"
        if "no observable case-input" in sl:
            return "schema::no_observable"
        if "boolean predicate atom" in sl:
            m = re.search(r"function\s+'([^']+)'", s, re.I)
            return "schema::fn_as_pred::" + (m.group(1) if m else "?")
        if "predicate" in sl and "function term" in sl:
            m = re.search(r"predicate\s+'([^']+)'", s, re.I)
            return "schema::pred_as_fn::" + (m.group(1) if m else "?")
        if "helper predicate" in sl and "never defined" in sl:
            m = re.search(r"helper predicate\s+'([^']+)'", s, re.I)
            return "schema::floating_helper_pred::" + (m.group(1) if m else "?")
        if "helper function" in sl and "never defined" in sl:
            m = re.search(r"helper function\s+'([^']+)'", s, re.I)
            return "schema::floating_helper_fun::" + (m.group(1) if m else "?")
        return "schema::" + sl[:120]
    if RULE_DESIGN_TAG.lower() in sl:
        m = re.search(r"derived predicate\s+'([^']+)'", s, re.I)
        return "rule::circular::" + (m.group(1) if m else "?")
    m = _RE_PRED_TYPE_MISMATCH.search(s)
    if m:
        return "type_mismatch::%s::arg%s::%s::%s" % (
            m.group(2),
            m.group(1),
            m.group(3).strip(),
            m.group(4).strip(),
        )
    m = _RE_FN_TYPE_MISMATCH.search(s)
    if m:
        return "type_mismatch::%s::arg%s::%s::%s" % (
            m.group(2),
            m.group(1),
            m.group(3).strip(),
            m.group(4).strip(),
        )
    m = _RE_UNBOUND.search(s)
    if m:
        return "unbound::" + m.group(1)
    if "unknown predicate" in sl or "undeclared symbol" in sl:
        return "unknown_symbol::" + sl[:100]
    if "non-empty consequent" in sl or "empty then" in sl:
        return "rule_shape::empty_then"
    if "unsupported expression" in sl:
        return "rule_shape::bad_expr"
    if "arity mismatch" in sl or "expects " in sl and " got " in sl:
        return "arity::" + sl[:100]
    return "other::" + re.sub(r"rules\[\d+\]", "rules[N]", sl)[:120]


def repeated_or_similar_type_error(msg: str, previous_errors: list[str]) -> bool:
    sig = normalize_error_signature(msg)
    if not sig.startswith("type_mismatch::"):
        return False
    for prev in previous_errors:
        if normalize_error_signature(prev) == sig:
            return True
    return False


def repeated_or_similar_unknown_symbol(msg: str, previous_errors: list[str]) -> bool:
    sig = normalize_error_signature(msg)
    if not sig.startswith("unknown_symbol::") and "undeclared" not in (msg or "").lower():
        return False
    for prev in previous_errors:
        ps = normalize_error_signature(prev)
        if ps == sig or (sig.startswith("unknown") and ps.startswith("unknown")):
            return True
    return False


def count_signature(msg: str, counts: dict[str, int]) -> str:
    sig = normalize_error_signature(msg)
    counts[sig] = counts.get(sig, 0) + 1
    return sig


def classify_json_ir_validation_error(
    error_message: str,
    previous_errors: list[str] | None = None,
    *,
    rules_repair_count: int = 0,
    max_rules_before_symbol_escalation: int = 2,
) -> JsonIRErrorKind:
    """Route validation failures to symbol repair vs rules-only repair."""
    msg = (error_message or "").strip()
    ml = msg.lower()
    prev = previous_errors or []

    if SCHEMA_DESIGN_TAG.lower() in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if RULE_DESIGN_TAG.lower() in ml:
        if "circular" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        if "incompatible unary subject roles" in ml:
            return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "observable predicate" in ml and ("consequent" in ml or "then" in ml):
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "used as a boolean predicate atom" in ml or "bool predicate atom" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "used as a function term" in ml and "predicate" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "no derived legal outputs" in ml or "no observable case-input" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "helper predicate" in ml and "never defined" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
    if "helper function" in ml and "never defined" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "conflicting signatures for symbol" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if rules_repair_count >= max_rules_before_symbol_escalation:
        if any(
            x in ml
            for x in (
                "expects type",
                "unknown predicate",
                "undeclared symbol",
                "arity mismatch",
                "lists it only under functions",
            )
        ):
            return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    sig_counts: dict[str, int] = {}
    for p in prev:
        count_signature(p, sig_counts)
    cur_sig = count_signature(msg, sig_counts)
    if sig_counts.get(cur_sig, 0) >= 2:
        if cur_sig.startswith("type_mismatch::") or cur_sig.startswith("schema::"):
            return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
        if cur_sig.startswith("unknown_symbol::") or cur_sig.startswith("unknown"):
            return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if repeated_or_similar_type_error(msg, prev):
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if repeated_or_similar_unknown_symbol(msg, prev):
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "expects type" in ml and "got" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    if "unknown predicate" in ml or "unknown function" in ml or "unknown type" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    if "undeclared symbol" in ml or "arity mismatch" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    if "unbound identifier" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    if "types cannot be empty" in ml or "predicates must be" in ml or "functions must be" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "non-empty consequent" in ml or "empty then" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    if "unsupported expression" in ml or "unsupported term" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    if "tautological" in ml or "circular" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    if "raw string expressions are not allowed" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    return JsonIRErrorKind.RULES_REPAIR_ONLY


def format_symbol_repair_error(validation_error: str) -> str:
    """Rich feedback for symbol repair after a combined IR failure."""
    em = (validation_error or "").strip()
    el = em.lower()
    extra = ""
    if "helper predicate" in el or "helper function" in el:
        if "never defined" in el:
            extra = (
                "\n\nSymbol-kind contract:\n"
                "- observable = supplied by case extraction.\n"
                "- derived = final legal conclusion/output.\n"
                "- helper = intermediate symbol that must be defined by rules.\n\n"
                "Every helper used in a rule condition must be defined by some rule, or it must be "
                "reclassified as observable. Do not leave helper predicates/functions open.\n\n"
                "Either reclassify this helper as observable if the case should provide it directly, "
                "or keep it as helper and ensure rules are generated to derive it from observable "
                "facts/functions. Rules-only repair cannot fix a floating helper without symbol changes."
            )
    return (
        "The rules phase exposed a symbol-table / schema design problem.\n\n"
        + em
        + extra
        + "\n\nRepair the symbol table (kinds, signatures, missing derived/observable symbols). "
        "Rules will be regenerated from your repaired symbols — do not assume the previous rules remain valid."
    )
