"""Generic validation for case-fact assertions against KB symbol metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pipeline.kb.composite_predicate_heuristics import (
    looks_computed_composite,
    symbol_background_or_case_input,
    symbol_directly_observable,
)
from pipeline.kb.factual_case_input import (
    case_given_predicate_name,
    case_text_explicitly_supports_factual_input,
    is_factual_case_input_candidate,
    is_query_or_legal_output_predicate,
)
from pipeline.kb.factual_criteria import (
    case_text_supports_factual_criteria,
    is_factual_criteria_input_candidate,
    pragmatic_factual_criteria_mode_enabled,
    symbol_marked_factual_criteria_input,
)
from pipeline.kb.legal_effect import (
    predicate_looks_like_classification_output,
    predicate_represents_legal_effect_output,
)

_CASE_FACT_EXEMPT_KINDS = frozenset({"observable", "input"})

_COMPOSITE_REJECTION_CODES = frozenset(
    {"derived_or_helper", "computed_composite", "classification_output"}
)

_NUMERIC_VALUE_RE = re.compile(
    r"(?<!\w)(?:\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?)(?!\w)"
)

CASE_EXTRACTION_REPAIR_ARTIFACT = "case_extraction_repair.json"


class CaseFactAssertionRejected(Exception):
    """Case IR asserted a predicate/function that may not be a case fact."""

    def __init__(self, message: str, *, pred: str, rejection_code: str) -> None:
        super().__init__(message)
        self.pred = pred
        self.rejection_code = rejection_code


@dataclass
class CaseFactRejectionDiagnostics:
    rejected_case_fact: str = ""
    rejection_reason: str = ""
    suggested_observable_replacements: list[dict[str, Any]] = field(default_factory=list)
    decomposition_required: bool = False
    case_text_has_numeric_values: bool = False
    empty_facts_after_repair: bool = False
    repair_attempt: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rejected_case_fact": self.rejected_case_fact,
            "rejection_reason": self.rejection_reason,
            "suggested_observable_replacements": self.suggested_observable_replacements,
            "decomposition_required": self.decomposition_required,
            "case_text_has_numeric_values": self.case_text_has_numeric_values,
            "empty_facts_after_repair": self.empty_facts_after_repair,
            "repair_attempt": self.repair_attempt,
        }

def case_fact_assertion_exempt(sig: dict[str, Any] | None) -> bool:
    """True when schema explicitly allows asserting this symbol from case text."""
    if not isinstance(sig, dict):
        return False
    if symbol_directly_observable(sig):
        return True
    if symbol_background_or_case_input(sig):
        return True
    if sig.get("case_input") is True:
        return True
    if symbol_marked_factual_criteria_input(sig):
        return True
    return False


def case_predicate_may_be_asserted_as_factual_criteria(
    sig: dict[str, Any] | None,
    *,
    case_text: str | None = None,
    evidence_text: str | None = None,
    query_predicate: str | None = None,
    kb_schema: dict | None = None,
) -> tuple[bool, str | None, str]:
    """Pragmatic mode: factual legal criteria with explicit case evidence."""
    if not pragmatic_factual_criteria_mode_enabled():
        return False, "mode_disabled", ""
    if not isinstance(sig, dict) or not sig.get("name"):
        return False, "unknown_symbol", ""
    if is_query_or_legal_output_predicate(sig, query_predicate=query_predicate):
        return False, "legal_output", ""
    if not (
        symbol_marked_factual_criteria_input(sig)
        or is_factual_criteria_input_candidate(sig, query_predicate=query_predicate, kb_schema=kb_schema)
    ):
        return False, "not_factual_criteria", ""
    supported, snippet = case_text_supports_factual_criteria(
        case_text,
        str(sig["name"]),
        sig,
        evidence_text=evidence_text,
    )
    if not supported:
        return False, "unsupported_by_case_text", ""
    return True, None, snippet


def _symbol_legal_output(sig: dict[str, Any]) -> bool:
    lo = sig.get("legal_output")
    lo_bool = lo if isinstance(lo, bool) else None
    return predicate_represents_legal_effect_output(
        str(sig.get("name") or ""),
        description=str(sig.get("description") or ""),
        kind=str(sig.get("kind") or ""),
        legal_output=lo_bool,
        output_category=str(sig.get("output_category") or ""),
    )


def _symbol_classification_output(sig: dict[str, Any]) -> bool:
    lo = sig.get("legal_output")
    lo_bool = lo if isinstance(lo, bool) else None
    return predicate_looks_like_classification_output(
        str(sig.get("name") or ""),
        description=str(sig.get("description") or ""),
        kind=str(sig.get("kind") or ""),
        legal_output=lo_bool,
        output_category=str(sig.get("output_category") or ""),
    )


def case_predicate_may_be_asserted_as_factual_input(
    sig: dict[str, Any] | None,
    *,
    case_text: str | None = None,
    evidence_text: str | None = None,
    query_predicate: str | None = None,
    kb_schema: dict | None = None,
) -> tuple[bool, str | None, str]:
    """
    Narrow exception: helper/composite threshold/criterion satisfaction explicitly stated in case.

    Returns (allowed, rejection_code, evidence_snippet).
    """
    if not isinstance(sig, dict) or not sig.get("name"):
        return False, "unknown_symbol", ""

    if is_query_or_legal_output_predicate(sig, query_predicate=query_predicate):
        return False, "legal_output", ""

    if not is_factual_case_input_candidate(sig, kb_schema):
        return False, "not_factual_case_input", ""

    supported, snippet = case_text_explicitly_supports_factual_input(
        case_text,
        str(sig["name"]),
        sig,
        evidence_text=evidence_text,
    )
    if not supported:
        return False, "unsupported_by_case_text", ""
    return True, None, snippet


def case_predicate_may_be_asserted(
    sig: dict[str, Any] | None,
    *,
    case_text: str | None = None,
    evidence_text: str | None = None,
    query_predicate: str | None = None,
    kb_schema: dict | None = None,
) -> tuple[bool, str | None]:
    """
    Return (allowed, rejection_code).

    Rejects derived/helper/composite/legal-output predicates unless the schema
    marks them as directly_observable, background, or case_input.
    """
    if not isinstance(sig, dict) or not sig.get("name"):
        return False, "unknown_symbol"

    name = str(sig.get("name") or "")
    if query_predicate and name == str(query_predicate).strip():
        return False, "query_predicate"

    if case_fact_assertion_exempt(sig):
        return True, None

    kind = str(sig.get("kind") or "unknown").strip().lower()
    description = str(sig.get("description") or "")

    if kind in {"observable", "input"}:
        if sig.get("legal_output") is True:
            return False, "legal_output"
        allowed_fc, code_fc, _ = case_predicate_may_be_asserted_as_factual_criteria(
            sig,
            case_text=case_text,
            evidence_text=evidence_text,
            query_predicate=query_predicate,
            kb_schema=kb_schema,
        )
        if allowed_fc:
            return True, None
        if looks_computed_composite(name, description):
            return False, "computed_composite"
        return True, None

    if sig.get("legal_output") is True or _symbol_legal_output(sig):
        return False, "legal_output"

    if _symbol_classification_output(sig):
        return False, "classification_output"

    if kind in {"helper", "derived", "conclusion"}:
        allowed_fc, code_fc, _ = case_predicate_may_be_asserted_as_factual_criteria(
            sig,
            case_text=case_text,
            evidence_text=evidence_text,
            query_predicate=query_predicate,
            kb_schema=kb_schema,
        )
        if allowed_fc:
            return True, None
        allowed_factual, code, _ = case_predicate_may_be_asserted_as_factual_input(
            sig,
            case_text=case_text,
            evidence_text=evidence_text,
            query_predicate=query_predicate,
            kb_schema=kb_schema,
        )
        if allowed_factual:
            return True, None
        return False, code or code_fc or "derived_or_helper"

    if looks_computed_composite(name, description):
        allowed_fc, code_fc, _ = case_predicate_may_be_asserted_as_factual_criteria(
            sig,
            case_text=case_text,
            evidence_text=evidence_text,
            query_predicate=query_predicate,
            kb_schema=kb_schema,
        )
        if allowed_fc:
            return True, None
        allowed_factual, code, _ = case_predicate_may_be_asserted_as_factual_input(
            sig,
            case_text=case_text,
            evidence_text=evidence_text,
            query_predicate=query_predicate,
            kb_schema=kb_schema,
        )
        if allowed_factual:
            return True, None
        return False, "computed_composite"

    if kind not in _CASE_FACT_EXEMPT_KINDS:
        return False, "unsupported_kind"

    return True, None


def case_function_may_be_asserted(sig: dict[str, Any] | None) -> tuple[bool, str | None]:
    """Same policy for numeric/function value assertions."""
    if not isinstance(sig, dict) or not sig.get("name"):
        return False, "unknown_symbol"

    if case_fact_assertion_exempt(sig):
        return True, None

    kind = str(sig.get("kind") or "unknown").strip().lower()
    name = str(sig.get("name") or "")
    description = str(sig.get("description") or "")

    if kind in {"helper", "derived"}:
        return False, "derived_or_helper"

    if looks_computed_composite(name, description) and kind != "observable":
        return False, "computed_composite"

    if kind not in {"observable", "input", "function"}:
        return False, "unsupported_kind"

    return True, None


def build_case_predicate_rejection_message(pred: str, rejection_code: str | None) -> str:
    code = rejection_code or "invalid_case_fact"
    if code == "unsupported_by_case_text":
        return (
            "Case extraction cannot assert predicate "
            + pred
            + " as a case-given factual input: the case text does not explicitly support it."
        )
    if code == "not_factual_case_input":
        return (
            "Case extraction cannot assert predicate "
            + pred
            + " as a case fact (not a controlled factual threshold/criterion input)."
        )
    if code == "derived_or_helper":
        return (
            "Case extraction cannot assert helper/composite/derived predicate "
            + pred
            + ". Use observable base facts only; let the KB derive helpers and legal conclusions."
        )
    if code == "legal_output":
        return (
            "Case extraction cannot assert legal-output predicate "
            + pred
            + " as a fact. Assert observable inputs only; the query stage derives legal conclusions."
        )
    if code == "query_predicate":
        return (
            "Case extraction cannot assert the selected query predicate "
            + pred
            + " as a case fact. Use observable or factual threshold inputs only."
        )
    if code == "classification_output":
        return (
            "Case extraction cannot assert classification/legal-output predicate "
            + pred
            + " as a fact. Use observable base facts from the case text."
        )
    if code == "computed_composite":
        return (
            "Case extraction cannot assert computed/composite predicate "
            + pred
            + " unless it is marked directly_observable/background/case_input. "
            "Decompose into base observable facts or numeric values."
        )
    if code == "unsupported_kind":
        return (
            "Case extraction cannot assert predicate "
            + pred
            + " as a case fact (unsupported symbol kind). Use observable facts only."
        )
    return "Case extraction cannot assert predicate " + pred + ". Use observable facts only."


def _is_atomic_observable_predicate(sym: dict[str, Any]) -> bool:
    if str(sym.get("returns") or "Bool").strip().lower() != "bool":
        return False
    kind = str(sym.get("kind") or "").strip().lower()
    if kind not in _CASE_FACT_EXEMPT_KINDS:
        return False
    if sym.get("legal_output") is True or _symbol_legal_output(sym) or _symbol_classification_output(sym):
        return False
    if looks_computed_composite(str(sym.get("name") or ""), str(sym.get("description") or "")):
        return False
    allowed, _ = case_predicate_may_be_asserted(sym)
    return allowed


def _is_numeric_observable_function(sym: dict[str, Any]) -> bool:
    kind = str(sym.get("kind") or "").strip().lower()
    if kind in {"helper", "derived"}:
        return False
    ret = str(sym.get("returns") or "").strip()
    if ret not in {"Int", "Real", "Float"}:
        return False
    allowed, _ = case_function_may_be_asserted(sym)
    return allowed


def _is_directly_observable_threshold_predicate(sym: dict[str, Any]) -> bool:
    if not symbol_directly_observable(sym):
        return False
    if str(sym.get("returns") or "Bool").strip().lower() != "bool":
        return False
    if not looks_computed_composite(str(sym.get("name") or ""), str(sym.get("description") or "")):
        return False
    allowed, _ = case_predicate_may_be_asserted(sym)
    return allowed


def list_atomic_observable_predicates(kb_schema: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in (kb_schema or {}).get("predicates") or []:
        if isinstance(p, dict) and p.get("name") and _is_atomic_observable_predicate(p):
            out.append(p)
    return out


def list_numeric_observable_functions(kb_schema: dict) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in (kb_schema or {}).get("functions") or []:
        if isinstance(f, dict) and f.get("name") and _is_numeric_observable_function(f):
            out.append(f)
    return out


def _format_symbol_line(sym: dict[str, Any], *, is_function: bool = False) -> str:
    name = str(sym.get("name") or "")
    args = ", ".join(sym.get("args") or [])
    desc = str(sym.get("description") or "").strip()
    if is_function:
        ret = str(sym.get("returns") or "Int")
        line = f"- {name}({args}) -> {ret}"
    else:
        line = f"- {name}({args})"
    if desc:
        line += f": {desc}"
    return line


def _find_symbol(kb_schema: dict, name: str) -> dict[str, Any] | None:
    for p in (kb_schema or {}).get("predicates") or []:
        if isinstance(p, dict) and p.get("name") == name:
            return p
    for f in (kb_schema or {}).get("functions") or []:
        if isinstance(f, dict) and f.get("name") == name:
            return f
    return None


def _case_text_tokens(case_text: str | None) -> set[str]:
    from pipeline.extraction.ir_utils import question_tokens, symbol_tokens

    if not case_text:
        return set()
    return question_tokens(case_text) | set(symbol_tokens(case_text))


def _case_text_for_numeric_scan(case_text: str | None) -> str:
    s = str(case_text or "")
    s = re.sub(r"\b\d+\s*:\s*\d+\b", " ", s)
    s = re.sub(r"\bart(?:icle)?\.?\s*\d+(?:\s*:\s*\d+)?\b", " ", s, flags=re.I)
    return s


def case_text_has_numeric_values(case_text: str | None) -> bool:
    if not case_text:
        return False
    scanned = _case_text_for_numeric_scan(case_text)
    for m in _NUMERIC_VALUE_RE.finditer(scanned):
        raw = m.group(0).replace(" ", "").replace(",", "")
        digits = re.sub(r"\D", "", raw)
        if not digits.isdigit() or len(digits) < 2:
            continue
        val = int(digits)
        if 1900 <= val <= 2100 and len(digits) == 4:
            continue
        return True
    return False


def parse_rejected_predicate_from_error(error_message: str) -> str:
    err_s = str(error_message or "")
    patterns = (
        r"helper/composite/derived predicate\s+([A-Za-z_]\w*)",
        r"legal-output predicate\s+([A-Za-z_]\w*)",
        r"classification/legal-output predicate\s+([A-Za-z_]\w*)",
        r"computed/composite predicate\s+([A-Za-z_]\w*)",
        r"helper predicate\s+([A-Za-z_]\w*)",
        r"invalid fact [`']([^`']+)[`']",
    )
    for pat in patterns:
        m = re.search(pat, err_s, re.I)
        if m:
            return m.group(1)
    return ""


def parse_rejection_code_from_error(error_message: str) -> str | None:
    el = str(error_message or "").lower()
    if "missing_decomposed_observables" in el or "added no observable" in el:
        return "missing_decomposed_observables"
    if "legal-output" in el:
        return "legal_output"
    if "classification/legal-output" in el:
        return "classification_output"
    if "computed/composite" in el:
        return "computed_composite"
    if "helper/composite/derived" in el or "helper predicate" in el:
        return "derived_or_helper"
    if "must not assert derived" in el:
        return "derived_or_helper"
    return None


def _score_replacement_candidate(
    sym: dict[str, Any],
    *,
    rejected_tokens: set[str],
    case_tokens: set[str],
    composite_helper: bool,
    symbol_type: str,
) -> tuple[float, list[str]]:
    from pipeline.extraction.ir_utils import symbol_tokens as _symbol_tokens

    name = str(sym.get("name") or "")
    desc = str(sym.get("description") or "")
    sym_tokens = set(_symbol_tokens(name) + _symbol_tokens(desc))
    reasons: list[str] = []
    score = 0.0
    if rejected_tokens and sym_tokens:
        inter = len(rejected_tokens & sym_tokens)
        if inter:
            score += (2.5 * inter) / float(max(1, len(rejected_tokens | sym_tokens)))
            reasons.append("semantic_overlap_with_rejected_helper")
    if case_tokens and sym_tokens:
        inter = len(case_tokens & sym_tokens)
        if inter:
            score += (1.8 * inter) / float(max(1, len(case_tokens | sym_tokens)))
            reasons.append("semantic_overlap_with_case_text")
    if composite_helper and symbol_type == "function":
        score += 0.45
        reasons.append("numeric_function_for_composite_helper")
    if composite_helper and symbol_directly_observable(sym):
        score += 0.25
        reasons.append("directly_observable_threshold_predicate")
    return score, reasons


def suggest_observable_replacements(
    rejected_pred: str,
    kb_schema: dict,
    *,
    rejection_code: str | None = None,
    case_text: str | None = None,
) -> list[dict[str, Any]]:
    rejected_sig = _find_symbol(kb_schema, rejected_pred)
    rejected_desc = str(rejected_sig.get("description") or "") if rejected_sig else ""
    from pipeline.extraction.ir_utils import symbol_tokens as _symbol_tokens

    rejected_tokens = set(_symbol_tokens(rejected_pred) + _symbol_tokens(rejected_desc))
    case_tokens = _case_text_tokens(case_text)
    composite_helper = (rejection_code or "") in _COMPOSITE_REJECTION_CODES

    scored: list[tuple[float, dict[str, Any], list[str], str]] = []

    for sym in list_numeric_observable_functions(kb_schema):
        sc, reasons = _score_replacement_candidate(
            sym,
            rejected_tokens=rejected_tokens,
            case_tokens=case_tokens,
            composite_helper=composite_helper,
            symbol_type="function",
        )
        scored.append((sc, sym, reasons, "function"))

    for sym in list_atomic_observable_predicates(kb_schema):
        sc, reasons = _score_replacement_candidate(
            sym,
            rejected_tokens=rejected_tokens,
            case_tokens=case_tokens,
            composite_helper=composite_helper,
            symbol_type="predicate",
        )
        scored.append((sc, sym, reasons, "predicate"))

    for p in (kb_schema or {}).get("predicates") or []:
        if isinstance(p, dict) and _is_directly_observable_threshold_predicate(p):
            sc, reasons = _score_replacement_candidate(
                p,
                rejected_tokens=rejected_tokens,
                case_tokens=case_tokens,
                composite_helper=True,
                symbol_type="predicate",
            )
            scored.append((sc + 0.15, p, reasons + ["directly_observable_threshold"], "predicate"))

    scored.sort(key=lambda x: (-x[0], str(x[1].get("name") or "")))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sc, sym, reasons, symbol_type in scored:
        name = str(sym.get("name") or "")
        if not name or name in seen:
            continue
        if sc < 0.04 and not (composite_helper and symbol_type == "function"):
            continue
        seen.add(name)
        out.append(
            {
                "name": name,
                "symbol_type": symbol_type,
                "kind": sym.get("kind"),
                "args": list(sym.get("args") or []),
                "returns": sym.get("returns"),
                "score": round(sc, 4),
                "reasons": reasons,
                "description": sym.get("description") or "",
            }
        )
        if len(out) >= 12:
            break
    if composite_helper and not out:
        for sym in list_numeric_observable_functions(kb_schema)[:8]:
            name = str(sym.get("name") or "")
            if name and name not in seen:
                out.append(
                    {
                        "name": name,
                        "symbol_type": "function",
                        "kind": sym.get("kind"),
                        "args": list(sym.get("args") or []),
                        "returns": sym.get("returns"),
                        "score": 0.0,
                        "reasons": ["fallback_numeric_observable"],
                        "description": sym.get("description") or "",
                    }
                )
    return out


def decomposition_required_from_case_text(
    case_text: str | None,
    suggestions: list[dict[str, Any]],
) -> bool:
    if not suggestions:
        return False
    if case_text_has_numeric_values(case_text):
        return True
    case_tokens = _case_text_tokens(case_text)
    if not case_tokens:
        return False
    from pipeline.extraction.ir_utils import symbol_tokens as _symbol_tokens

    for s in suggestions:
        reasons = list(s.get("reasons") or [])
        if reasons == ["fallback_numeric_observable"]:
            continue
        sym_tokens = set(
            _symbol_tokens(str(s.get("name") or ""))
            + _symbol_tokens(str(s.get("description") or ""))
        )
        overlap = len(case_tokens & sym_tokens)
        if overlap >= 2:
            return True
        if (
            overlap >= 1
            and s.get("symbol_type") == "function"
            and "semantic_overlap_with_case_text" in reasons
        ):
            return True
    return False


def build_rejection_diagnostics(
    rejected_pred: str,
    rejection_code: str,
    kb_schema: dict,
    *,
    case_text: str | None = None,
    repair_attempt: int = 0,
) -> CaseFactRejectionDiagnostics:
    suggestions = suggest_observable_replacements(
        rejected_pred,
        kb_schema,
        rejection_code=rejection_code,
        case_text=case_text,
    )
    has_numeric = case_text_has_numeric_values(case_text)
    decomposition_required = False
    if rejection_code in _COMPOSITE_REJECTION_CODES:
        decomposition_required = decomposition_required_from_case_text(case_text, suggestions)
    return CaseFactRejectionDiagnostics(
        rejected_case_fact=rejected_pred,
        rejection_reason=rejection_code,
        suggested_observable_replacements=suggestions,
        decomposition_required=decomposition_required,
        case_text_has_numeric_values=has_numeric,
        repair_attempt=repair_attempt,
    )


def case_object_has_non_entity_facts(case_obj: dict | None) -> bool:
    if not isinstance(case_obj, dict):
        return False
    facts = case_obj.get("facts") or []
    if isinstance(facts, list) and any(str(f or "").strip() for f in facts):
        return True
    for key in ("assertions", "value_assertions", "assignments"):
        vals = case_obj.get(key)
        if isinstance(vals, list) and vals:
            return True
    return False


def build_empty_decomposition_repair_error(diag: CaseFactRejectionDiagnostics) -> str:
    lines = [
        "Case repair removed invalid fact `"
        + (diag.rejected_case_fact or "INVALID")
        + "` but added no observable assertions or value_assertions.",
        "Simply deleting the helper/composite fact is insufficient when the case text states "
        "underlying numeric or atomic observable facts that the KB schema can represent.",
        "Assert matching observable predicates/functions from the suggested replacement list.",
    ]
    if diag.case_text_has_numeric_values:
        lines.append(
            "The case text contains numeric values; map each stated number to a matching "
            "numeric function in value_assertions."
        )
    return " ".join(lines)


def validate_decomposition_repair_or_raise(
    case_obj: dict,
    diag: CaseFactRejectionDiagnostics | None,
) -> None:
    if not diag or not diag.decomposition_required:
        return
    if case_object_has_non_entity_facts(case_obj):
        return
    diag.empty_facts_after_repair = True
    raise CaseFactAssertionRejected(
        build_empty_decomposition_repair_error(diag),
        pred=diag.rejected_case_fact,
        rejection_code="missing_decomposed_observables",
    )


def build_case_decomposition_repair_hint(
    diag: CaseFactRejectionDiagnostics,
    *,
    case_text: str | None = None,
) -> str:
    pred = diag.rejected_case_fact or "INVALID_PREDICATE"
    lines = [
        "",
        "REMEDIATION (case facts — decompose into observables):",
        "- Rejected case fact: `" + pred + "` (" + (diag.rejection_reason or "invalid") + ").",
        "- Do NOT re-assert helper, composite, derived, classification, or legal-output predicates.",
        "- Exception: when the case explicitly states a threshold/criterion satisfaction condition, you MAY "
        "assert a listed factual case input predicate with evidence_text (never invent numeric values).",
        "- Removing the invalid assertion alone is NOT enough when the case states underlying facts.",
        "- Decompose the case text into assertable observable predicate assertions and/or numeric value_assertions.",
    ]
    if diag.rejection_reason == "legal_output":
        lines.append(
            "- Legal-output predicates belong in the query stage, never in case assertions."
        )
        return "\n".join(lines)

    if diag.case_text_has_numeric_values:
        lines.append(
            "- The case text contains numeric values: assert each stated number using a matching "
            "numeric observable function from KB_SCHEMA in value_assertions."
        )
    elif diag.decomposition_required:
        lines.append(
            "- The case text overlaps with observable schema symbols below; assert those base facts."
        )
    else:
        lines.append(
            "- If the case only states a composite legal abstraction with no decomposable base facts, "
            "omit the helper and leave only entities; the answer may remain unknown."
        )

    suggestions = diag.suggested_observable_replacements
    if suggestions:
        lines.append("")
        lines.append("Suggested observable replacements (prioritized by schema/case overlap):")
        for s in suggestions[:12]:
            args = ", ".join(s.get("args") or [])
            if s.get("symbol_type") == "function":
                line = f"- {s['name']}({args}) -> {s.get('returns', 'Int')}"
            else:
                line = f"- {s['name']}({args})"
            desc = str(s.get("description") or "").strip()
            if desc:
                line += f": {desc}"
            if s.get("reasons"):
                line += "  [" + ", ".join(s["reasons"]) + "]"
            lines.append(line)
    else:
        lines.append("")
        lines.append(
            "No assertable observable replacement symbols matched the rejected helper and case text; "
            "entities-only repair is acceptable."
        )

    if case_text:
        snippet = str(case_text).strip().replace("\n", " ")
        if len(snippet) > 240:
            snippet = snippet[:237] + "..."
        lines.append("")
        lines.append("Case text to decompose:")
        lines.append(snippet)

    return "\n".join(lines)


def build_case_fact_rejection_repair_hint(
    pred: str,
    kb_schema: dict,
    *,
    rejection_code: str | None = None,
    case_text: str | None = None,
    rejection_diag: CaseFactRejectionDiagnostics | None = None,
) -> str:
    """Machine repair supplement when case extraction asserts a forbidden predicate."""
    diag = rejection_diag or build_rejection_diagnostics(
        pred,
        rejection_code or "invalid_case_fact",
        kb_schema,
        case_text=case_text,
    )
    return build_case_decomposition_repair_hint(diag, case_text=case_text)


def build_factual_case_input_diagnostics(
    case: dict[str, Any] | None,
    *,
    case_text: str | None = None,
    query_predicate: str | None = None,
    kb_schema: dict | None = None,
) -> dict[str, Any]:
    """Summarize accepted/rejected factual case inputs for artifacts."""
    from pipeline.kb.factual_case_input import CASE_GIVEN_PREFIX

    accepted = list((case or {}).get("case_given_factual_inputs") or [])
    bridge_used = any(
        str(e.get("input_predicate") or "").startswith(CASE_GIVEN_PREFIX) for e in accepted
    )
    return {
        "case_given_factual_inputs": accepted,
        "accepted_threshold_satisfaction_facts": [
            {
                "input_predicate": e.get("input_predicate"),
                "target_predicate": e.get("target_predicate"),
                "args": e.get("args"),
                "evidence_text": e.get("evidence_text"),
                "assertion_kind": e.get("assertion_kind"),
            }
            for e in accepted
        ],
        "case_text_has_numeric_values": case_text_has_numeric_values(case_text),
        "case_text_numeric_values_explicit": case_text_has_numeric_values(case_text),
        "bridge_predicates_generated": bridge_used,
        "rejected_query_predicate_assertions": [],
        "rejected_legal_outputs": [],
        "query_predicate": query_predicate,
    }


def validate_case_facts_not_query_target(
    case: dict[str, Any],
    query: dict[str, Any],
    kb_schema: dict | None = None,
) -> None:
    """Reject case facts that assert the selected boolean query predicate."""
    if not isinstance(case, dict) or not isinstance(query, dict):
        return
    qpred = str(query.get("predicate") or "").strip()
    if not qpred:
        return
    from pipeline.kb.factual_case_input import CASE_GIVEN_PREFIX

    import re

    atom_re = re.compile(r"^\s*(?:not|~|¬)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    for ln in case.get("facts") or []:
        if not isinstance(ln, str):
            continue
        m = atom_re.match(ln.strip())
        if not m:
            continue
        fact_pred = m.group(1)
        if fact_pred == qpred:
            raise CaseFactAssertionRejected(
                build_case_predicate_rejection_message(qpred, "query_predicate"),
                pred=qpred,
                rejection_code="query_predicate",
            )
        if fact_pred.startswith(CASE_GIVEN_PREFIX) and fact_pred[len(CASE_GIVEN_PREFIX) :] == qpred:
            raise CaseFactAssertionRejected(
                build_case_predicate_rejection_message(qpred, "query_predicate"),
                pred=qpred,
                rejection_code="query_predicate",
            )


def case_fact_validation_error_matches(error_message: str) -> bool:
    el = str(error_message or "").lower()
    needles = (
        "cannot assert helper",
        "cannot assert legal-output",
        "cannot assert classification",
        "cannot assert computed/composite",
        "must not assert derived",
        "use observable facts only",
        "use observable base facts",
        "added no observable",
        "missing_decomposed_observables",
    )
    return any(n in el for n in needles)
