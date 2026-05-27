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


# Symbol-table validation errors that warrant another symbol version when budget allows.
SYMBOL_STAGE_REPAIRABLE_CODES: frozenset[str] = frozenset(
    {
        "missing_legal_effect_output",
        "missing_temporal_support_symbol",
        "status_as_type",
        "computed_observable_unsafe",
        "invalid_signature",
        "unknown_symbol",
        "type_mismatch",
        "json_parse_error",
    }
)


def is_symbol_stage_repairable_error(error_code: str | None) -> bool:
    """True when a failed symbol validation should allow another symbol version."""
    return bool(error_code) and error_code in SYMBOL_STAGE_REPAIRABLE_CODES


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


def normalize_error_code(msg: str) -> str:
    """Stable error code for repair cards and repair history grouping."""
    s = (msg or "").strip()
    sl = s.lower()
    if "json ir validation failed" in sl or "expected" in sl and "json" in sl:
        if "parse" in sl or "json.loads" in sl or "invalid json" in sl:
            return "json_parse_error"
    if "openai call failed" in sl and "json" in sl:
        return "json_parse_error"
    if "helper predicate" in sl and ("defining rule" in sl or "never defined" in sl or "no defining rule" in sl):
        return "missing_helper_definition"
    if "derived predicate" in sl and ("without a defining rule" in sl or "no defining rule" in sl):
        return "missing_helper_definition"
    if "helper function" in sl and ("defining rule" in sl or "never defined" in sl):
        return "missing_helper_definition"
    if "computed-looking observable" in sl or "looks computed/composite" in sl:
        return "computed_observable_unsafe"
    if "does not appear in the scoped law text" in sl or "do not invent or alter legal thresholds" in sl:
        return "numeric_threshold_not_in_law_text"
    if "cannot prove disqualification" in sl or "exclusion rule such as" in sl:
        return "missing_threshold_classification_exclusion"
    if "inverse/de morgan negative rules" in sl or "negating observable/background prerequisites" in sl:
        return "unsafe_inverse_negative_legal_output"
    if "uses predicate" in sl and "as a function term" in sl:
        return "predicate_used_as_function"
    if "as a bool predicate atom" in sl and "only under functions" in sl:
        return "function_used_as_predicate"
    if "numeric_threshold_ambiguous" in sl:
        return "numeric_threshold_ambiguous"
    if "suspicious self-relation" in sl or (
        "same variable twice" in sl and "between-entities" in sl
    ):
        return "suspicious_self_relation"
    if "no_helper_definition_progress" in sl:
        return "no_helper_definition_progress"
    if "repeated_missing_helper_definition" in sl:
        return "repeated_missing_helper_definition"
    if "repeated_missing_numeric_helper_definition" in sl:
        return "repeated_missing_numeric_helper_definition"
    if "at-most-one" in sl or "more-than-one criteria" in sl or "simple or over individual" in sl:
        return "threshold_cardinality_or_singleton"
    if "semantically identical to the status" in sl or "classification encoded as a primitive type" in sl:
        return "status_as_type"
    if (
        "legal-effect or timing language" in sl
        or "no derived legal-output predicate" in sl
        or "no derived legal outputs" in sl
        or "symbol table contains no derived legal outputs" in sl
    ):
        return "missing_legal_effect_output"
    if (
        "no temporal support relation" in sl
        or "temporal support relation/function" in sl
        or "do not count as temporal support" in sl
    ):
        return "missing_temporal_support_symbol"
    if "never appear in any rule then" in sl:
        return "derived_predicate_not_defined"
    if "unconstrained consequent variable" in sl:
        return "ungrounded_variable"
    if "conflicting signatures" in sl or "unknown return type" in sl or "unknown argument type" in sl:
        return "invalid_signature"
    if "unknown predicate" in sl or "undeclared symbol" in sl or "not declared" in sl:
        return "unknown_symbol"
    if "expects type" in sl and "got" in sl:
        return "type_mismatch"
    if "idp failed to parse" in sl or "failed to parse compiled kb" in sl:
        return "idp_render_error"
    return "unknown_validation_error"


def normalize_error_signature(msg: str) -> str:
    """Stable key for repeated-error escalation (drops indices where useful)."""
    s = (msg or "").strip()
    sl = s.lower()
    if SCHEMA_DESIGN_TAG.lower() in sl:
        if "observable predicate" in sl and "consequent" in sl:
            m = re.search(r"observable predicate\s+'([^']+)'", s, re.I)
            return "schema::observable_in_then::" + (m.group(1) if m else "?")
        if "no derived legal outputs" in sl:
            return "schema::missing_legal_effect"
        if "no observable case-input" in sl:
            return "schema::no_observable"
        if "boolean predicate atom" in sl:
            m = re.search(r"function\s+'([^']+)'", s, re.I)
            return "schema::fn_as_pred::" + (m.group(1) if m else "?")
        if "predicate" in sl and "function term" in sl:
            m = re.search(r"predicate\s+'([^']+)'", s, re.I)
            return "schema::pred_as_fn::" + (m.group(1) if m else "?")
        if "computed-looking observable" in sl:
            m = re.search(r"observable predicate\s+'([^']+)'", s, re.I)
            return "schema::computed_observable::" + (m.group(1) if m else "?")
        if "looks computed/composite" in sl:
            m = re.search(r"predicate\s+'([^']+)'", s, re.I)
            return "schema::computed_observable_decl::" + (m.group(1) if m else "?")
        if "as a bool predicate atom" in sl and "only under functions" in sl:
            m = re.search(r"Rules use '([^']+)'", s, re.I)
            return "schema::predicate_used_as_function::" + (m.group(1) if m else "?")
        if "as a bool predicate atom" in sl and "lists it only under predicates" in sl:
            m = re.search(r"Rules use '([^']+)'", s, re.I)
            return "schema::function_used_as_predicate::" + (m.group(1) if m else "?")
        if "legal-effect or timing language" in sl or "no derived legal-output" in sl:
            return "schema::missing_legal_effect"
        if "semantically identical to the status" in sl:
            return "schema::status_as_type"
        if "at-most-one" in sl or "simple or over individual" in sl:
            return "schema::threshold_cardinality"
        if "inverse/de morgan negative rules" in sl:
            return "rule::unsafe_inverse_negative"
        if "helper predicate" in sl and "never defined" in sl:
            m = re.search(r"helper predicate\s+'([^']+)'", s, re.I)
            return "schema::floating_helper_pred::" + (m.group(1) if m else "?")
        if "helper function" in sl and "never defined" in sl:
            m = re.search(r"helper function\s+'([^']+)'", s, re.I)
            return "schema::floating_helper_fun::" + (m.group(1) if m else "?")
        return "schema::" + sl[:120]
    if RULE_DESIGN_TAG.lower() in sl:
        if "at-most-one" in sl or "simple or over individual" in sl:
            return "rule::threshold_cardinality"
        if "defining rule" in sl or "no defining rule" in sl:
            m = re.search(r"helper predicate\s+'([^']+)'", s, re.I)
            return "rule::missing_helper::" + (m.group(1) if m else "?")
        if "never appear in any rule then" in sl:
            m = re.search(r"derived predicate\(s\)\s+([^\s]+)", s, re.I)
            return "rule::derived_undefined::" + (m.group(1) if m else "?")
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
        if "never appear in any rule then" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if RULE_DESIGN_TAG.lower() in ml:
        if "circular" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        if "incompatible unary subject roles" in ml:
            return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
        if "does not appear in the scoped law text" in ml or "do not invent or alter legal thresholds" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        if "cannot prove disqualification" in ml or "exclusion rule such as" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        if "at-most-one" in ml or "more-than-one criteria" in ml or "simple or over individual" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        if "threshold comparisons" in ml and "favorable derived" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        if "repair layer: rules" in ml or "has no defining rule" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        if "helper predicate" in ml and "defining rule" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "observable predicate" in ml and ("consequent" in ml or "then" in ml):
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "used as a boolean predicate atom" in ml or "bool predicate atom" in ml:
        if "only under functions" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        if "lists it only under predicates" in ml:
            return JsonIRErrorKind.RULES_REPAIR_ONLY
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "used as a function term" in ml and "predicate" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

    if "no derived legal outputs" in ml or "no observable case-input" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

    if "computed-looking observable" in ml or "looks computed/composite" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
    if "repair layer: symbols" in ml:
        return JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
    if "helper predicate" in ml and ("never defined" in ml or "defining rule" in ml):
        return JsonIRErrorKind.RULES_REPAIR_ONLY
    if "helper function" in ml and "never defined" in ml:
        return JsonIRErrorKind.RULES_REPAIR_ONLY

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
    if "computed-looking observable" in el or "looks computed/composite" in el:
        extra = (
            "\n\nComputed/composite conditions (exceeds/meets/threshold/criteria-style) must not stay "
            "observable unless directly_observable=true and cases may state the composite fact verbatim. "
            "Otherwise use kind=helper with defining rules from numeric functions/comparisons, or encode "
            "thresholds directly in rule if-conditions. Do not rely on negating an undefined atom."
        )
    if "semantically identical to the status" in el or "status or classification encoded as a primitive type" in el:
        extra = (
            "\n\nDo not create primitive types for legal statuses/classifications unless the law introduces "
            "a separate object domain. Model statuses as derived predicates over broader entity types "
            "(Person, Company, LegalEntity, etc.). For roles between entities, prefer relational predicates "
            "(e.g. is_spouse_of(a, b)) over unary status types."
        )
    if (
        "legal-effect or timing language" in el
        or "no derived legal-output predicate" in el
        or "no derived legal outputs" in el
    ):
        extra = (
            "\n\nThe symbol table must include at least one derived predicate/function representing "
            "legal classifications, consequences, rights, obligations, permissions, prohibitions, "
            "exceptions, sanctions, validity results, entitlements, or exclusions. "
            "When the law states a legal consequence, effect, or timing, add an explicit derived "
            "legal-output predicate for that effect (not only is_* classifications or threshold helpers). "
            "Set legal_output=true or output_category=legal_effect when helpful. "
            "Preserve existing classification/support predicates. Rules repair cannot invent the query target."
        )
    if "helper predicate" in el or "helper function" in el:
        if "defining rule" in el or "never defined" in el:
            extra = (
                "\n\nEvery helper used in a rule (especially under negation) must have defining rules "
                "in THEN from observable facts/functions. Prefer numeric function comparisons over "
                "undefined threshold predicates. Do not rename the predicate or delete the negated "
                "condition without adding a proper definition."
            )
    return (
        "The rules phase exposed a symbol-table / schema design problem.\n\n"
        + em
        + extra
        + "\n\nRepair the symbol table (kinds, signatures, missing derived/observable symbols). "
        "Rules will be regenerated from your repaired symbols — do not assume the previous rules remain valid."
    )
