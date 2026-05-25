"""
Deterministic symbolic intent routing from question text, expected answer shape,
and extracted query metadata.

Routing selects the execution intent; extraction may still supply predicate targets.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pipeline.symbolic.intent_registry import get_intent_spec

QUESTION_TYPE_BOOLEAN = "boolean"
QUESTION_TYPE_POSSIBLE_LIST = "possible_list"
QUESTION_TYPE_RANGE_VALUE = "range_value"
QUESTION_TYPE_CONSISTENCY = "consistency"
QUESTION_TYPE_EXPLANATION = "explanation"
QUESTION_TYPE_UNKNOWN = "unknown"

INTENT_DEDUCTION = "deduction"
INTENT_DEDUCTION_SET = "deduction_set"
INTENT_MODEL_EXPANSION = "model_expansion"
INTENT_GET_RANGE = "get_range"
INTENT_OPTIMIZATION = "optimization"
INTENT_SATISFIABLE = "satisfiable"
INTENT_EXPLAIN = "explain"
INTENT_RELEVANCE = "relevance"
INTENT_PROPAGATION = "propagation"

_CONSISTENCY_PATTERNS = (
    r"\bare these facts consistent\b",
    r"\bis this case possible\b",
    r"\bcan these facts occur\b",
    r"\bconsistent with the law\b",
    r"\bconsistent under the law\b",
    r"\btheorie.*consistent\b",
    r"\bzijn deze feiten consistent\b",
    r"\bis deze casus mogelijk\b",
    r"\bkunnen deze feiten voorkomen\b",
)

_EXPLANATION_PATTERNS = (
    r"\bwhy\b",
    r"\bexplain\b",
    r"\bexplanation\b",
    r"\bwhich facts matter\b",
    r"\bwhich rules are relevant\b",
    r"\bwhat rules (are|were) relevant\b",
    r"\bwaarom\b",
    r"\bverklaar\b",
    r"\bleg uit\b",
    r"\bwelke feiten\b.*\b(belangrijk|relevant)\b",
    r"\bwelke regels\b.*\brelevant\b",
)

_RANGE_PATTERNS = (
    r"\bfine range\b",
    r"\bpossible fine\b",
    r"\bamount can be imposed\b",
    r"\bhow many years\b",
    r"\bminimum\b",
    r"\bmaximum\b",
    r"\bmin(?:imum)?\b",
    r"\bmax(?:imum)?\b",
    r"\bwhat values are possible\b",
    r"\bwhat is the (?:possible )?range\b",
    r"\bboete.*bereik\b",
    r"\bminimum.*boete\b",
    r"\bmaximum.*boete\b",
    r"\bbedrag\b",
    r"\bjaren\b",
)

_MIN_MAX_PATTERNS = (
    r"\bminimum\b",
    r"\bmaximum\b",
    r"\blowest\b",
    r"\bhighest\b",
    r"\bmin(?:imum)?\b",
    r"\bmax(?:imum)?\b",
)

_POSSIBLE_LIST_PATTERNS = (
    r"\bwhat possible\b",
    r"\bwhich possible\b",
    r"\bwhich sanctions\b",
    r"\bwhich punishments\b",
    r"\bwhich legal consequences\b",
    r"\bwhich consequences\b",
    r"\bwhich classifications\b",
    r"\bwhat outcomes are possible\b",
    r"\bmay apply\b",
    r"\bcan apply\b",
    r"\bcould (?:this|the)\b",
    r"\bwelke sancties\b",
    r"\bwelke straffen\b",
    r"\bwelke mogelijke\b",
    r"\bwelke juridische gevolgen\b",
    r"\bwelke gevolgen\b",
    r"\bmogelijke straffen\b",
    r"\bmogelijke sancties\b",
)

_BOOLEAN_PATTERNS = (
    r"\bis\s+.+\s+true\b",
    r"\bdoes\s+.+\s+apply\b",
    r"\bcan it be concluded\b",
    r"\bare the legal consequences applicable\b",
    r"\bis the company\b",
    r"\bqualifies as\b",
    r"\bhas the right\b",
    r"\bis entitled\b",
    r"\bapplicable\b",
    r"\bgeldt\b",
    r"\bvan toepassing\b",
    r"\bis er sprake van\b",
    r"\bkan worden geconcludeerd\b",
    r"\bheeft\b.+\brecht\b",
)


def _matches(question: str, patterns: tuple[str, ...]) -> bool:
    t = (question or "").strip()
    if not t:
        return False
    for pat in patterns:
        if re.search(pat, t, re.IGNORECASE):
            return True
    return False


def _expected_question_type(expected: dict | None) -> str | None:
    if not isinstance(expected, dict):
        return None
    if str(expected.get("intent") or "").strip().lower() == "satisfiable":
        return QUESTION_TYPE_CONSISTENCY
    if str(expected.get("intent") or "").strip().lower() == "get_range":
        return QUESTION_TYPE_RANGE_VALUE
    mode = str(expected.get("mode") or "").strip().lower()
    if mode == "boolean":
        return QUESTION_TYPE_BOOLEAN
    if mode == "set":
        return QUESTION_TYPE_POSSIBLE_LIST
    return None


def _query_hint_type(query: dict | None) -> str | None:
    if not isinstance(query, dict):
        return None
    if str(query.get("type") or "").lower() == "intent":
        intent = str(query.get("intent") or query.get("internal_intent") or "").lower()
        mapping = {
            "satisfiable": QUESTION_TYPE_CONSISTENCY,
            "get_range": QUESTION_TYPE_RANGE_VALUE,
            "optimization": QUESTION_TYPE_RANGE_VALUE,
            "model_expansion": QUESTION_TYPE_POSSIBLE_LIST,
            "deduction_set": QUESTION_TYPE_POSSIBLE_LIST,
            "explain": QUESTION_TYPE_EXPLANATION,
            "relevance": QUESTION_TYPE_EXPLANATION,
            "propagation": QUESTION_TYPE_EXPLANATION,
        }
        return mapping.get(intent)
    if str(query.get("type") or "").lower() == "predicate":
        mode = str(query.get("mode") or "boolean").lower()
        if mode == "set":
            return QUESTION_TYPE_POSSIBLE_LIST
        if bool(query.get("explain")):
            return QUESTION_TYPE_EXPLANATION
        return QUESTION_TYPE_BOOLEAN
    return None


def _intent_for_question_type(
    question_type: str,
    *,
    question_text: str,
    optimization_supported: bool = True,
) -> tuple[str, str | None, list[str]]:
    warnings: list[str] = []
    fallback: str | None = None

    if question_type == QUESTION_TYPE_CONSISTENCY:
        return INTENT_SATISFIABLE, None, warnings

    if question_type == QUESTION_TYPE_EXPLANATION:
        return INTENT_EXPLAIN, INTENT_RELEVANCE, warnings

    if question_type == QUESTION_TYPE_RANGE_VALUE:
        if _matches(question_text, _MIN_MAX_PATTERNS):
            if optimization_supported:
                return INTENT_OPTIMIZATION, INTENT_GET_RANGE, warnings
            warnings.append("optimization_not_supported; using get_range")
            return INTENT_GET_RANGE, None, warnings
        return INTENT_GET_RANGE, INTENT_OPTIMIZATION, warnings

    if question_type == QUESTION_TYPE_POSSIBLE_LIST:
        return INTENT_MODEL_EXPANSION, INTENT_DEDUCTION_SET, warnings

    if question_type == QUESTION_TYPE_BOOLEAN:
        return INTENT_DEDUCTION, None, warnings

    return "unknown", INTENT_DEDUCTION, ["unknown_question_type"]


def _has_boolean_target(query: dict | None) -> bool:
    if not isinstance(query, dict):
        return False
    if str(query.get("type") or "").lower() == "predicate":
        pred = str(query.get("predicate") or "").strip()
        return bool(pred) and str(query.get("mode") or "boolean").lower() == "boolean"
    if str(query.get("type") or "").lower() == "intent":
        tgt = query.get("target")
        if isinstance(tgt, dict) and tgt.get("predicate"):
            return True
    return False


def _legal_output_symbols(
    kb_schema: dict | None,
    schema_environment: dict | None,
) -> list[str]:
    if schema_environment:
        syms = schema_environment.get("legal_output_query_targets")
        if isinstance(syms, list) and syms:
            return [str(s) for s in syms]
    if not kb_schema:
        return []
    out: list[str] = []
    for p in kb_schema.get("predicates") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        lo = p.get("legal_output")
        cat = str(p.get("output_category") or "").lower()
        if lo is True or cat in (
            "sanction",
            "punishment",
            "legal_effect",
            "consequence",
            "classification",
        ):
            out.append(str(p["name"]))
    return sorted(set(out))


def classify_symbolic_intent(
    *,
    question_text: str,
    expected: dict | None = None,
    query: dict | None = None,
    kb_schema: dict | None = None,
    schema_environment: dict | None = None,
    optimization_supported: bool = True,
) -> dict[str, Any]:
    """
    Classify question type and select symbolic execution intent.
    """
    exp_type = _expected_question_type(expected)
    query_type = _query_hint_type(query)
    text_type: str | None = None

    if _matches(question_text, _CONSISTENCY_PATTERNS):
        text_type = QUESTION_TYPE_CONSISTENCY
    elif _matches(question_text, _EXPLANATION_PATTERNS):
        text_type = QUESTION_TYPE_EXPLANATION
    elif _matches(question_text, _RANGE_PATTERNS):
        text_type = QUESTION_TYPE_RANGE_VALUE
    elif _matches(question_text, _POSSIBLE_LIST_PATTERNS):
        text_type = QUESTION_TYPE_POSSIBLE_LIST
    elif _matches(question_text, _BOOLEAN_PATTERNS):
        text_type = QUESTION_TYPE_BOOLEAN

    # Expected answer shape wins for scoring alignment when present.
    if exp_type == QUESTION_TYPE_BOOLEAN:
        detected = QUESTION_TYPE_BOOLEAN
        reason = "expected.mode=boolean"
    elif exp_type:
        detected = exp_type
        reason = "expected_answer_shape"
    elif query_type and str((query or {}).get("type") or "").lower() == "intent":
        detected = query_type
        reason = "extracted_intent_query"
    elif text_type:
        detected = text_type
        reason = "question_text_patterns"
    elif query_type:
        detected = query_type
        reason = "extracted_query_hint"
    elif _has_boolean_target(query):
        detected = QUESTION_TYPE_BOOLEAN
        reason = "concrete_boolean_query_target"
    else:
        detected = QUESTION_TYPE_UNKNOWN
        reason = "no_clear_signals"

    selected, fallback, warnings = _intent_for_question_type(
        detected,
        question_text=question_text,
        optimization_supported=optimization_supported,
    )

    if detected == QUESTION_TYPE_UNKNOWN:
        if _has_boolean_target(query):
            selected = INTENT_DEDUCTION
            detected = QUESTION_TYPE_BOOLEAN
            reason = "fallback_boolean_target"
        else:
            selected = "unknown"
            warnings.append("no_concrete_target_for_deduction")

    scorable = False
    if selected and selected != "unknown":
        try:
            spec = get_intent_spec(selected)
            scorable = spec.scorable in ("yes", "partial")
        except Exception:
            scorable = selected in (INTENT_DEDUCTION, INTENT_SATISFIABLE, INTENT_GET_RANGE)

    routing = {
        "question": question_text,
        "detected_question_type": detected,
        "selected_intent": selected,
        "selected_reason": reason,
        "scorable": scorable,
        "fallback_intent": fallback,
        "warnings": warnings,
        "legal_output_symbols": _legal_output_symbols(kb_schema, schema_environment),
        "query_hint_type": query_type,
        "expected_question_type": exp_type,
    }
    return routing


def write_symbolic_intent_routing(path: str | Path, routing: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(routing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
