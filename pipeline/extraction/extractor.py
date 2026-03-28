import json
import os
import re

from debug import status_log
from pipeline.extraction.openai_extractor import (
    extract_case_only_openai,
    extract_query_only_openai,
    LLMExtractionError,
)
from pipeline.validation.fo_validation import (
    normalize_and_validate_case,
    normalize_and_validate_query,
    _entities_from_case,
)


class ExtractionError(Exception):
    pass


# Words that are not entity names when they appear in "Is X ..." patterns
_QUESTION_STOPWORDS = frozenset({
    "the", "what", "who", "which", "how", "why", "when", "where", "does", "did",
    "is", "are", "was", "were", "can", "could", "article", "art", "belgian",
    "law", "case", "facts", "sentence", "minimum", "maximum", "prison", "fine",
})


def _entity_asked_about_in_question(question):
    """Extract the person/entity the question asks about (e.g. 'Is Karel liable?' -> karel)."""
    if not question or not isinstance(question, str):
        return None
    q = question.strip()
    # Patterns: "Is X liable?", "for X", "about X", "X is liable", "sentence for X"
    patterns = [
        r"\b(?:Is|Are|Does|Did|Was|Were)\s+([A-Z][a-zA-Z]+)\b",
        r"\b(?:for|about)\s+([A-Z][a-zA-Z]+)\b",
        r"\b([A-Z][a-zA-Z]+)\s+(?:liable|punishable|eligible|qualifies)\b",
    ]
    for pat in patterns:
        m = re.search(pat, q)
        if m:
            name = m.group(1).strip().lower()
            if name and name not in _QUESTION_STOPWORDS and len(name) >= 2:
                return name
    return None


def _case_entity_set(case):
    """All entity names (lowercase) that appear in the case: from facts and from case.entities."""
    out = set(_entities_from_case(case))
    for key, vals in (case.get("entities") or {}).items():
        if isinstance(vals, list):
            for v in vals:
                if isinstance(v, str) and v.strip():
                    out.add(v.strip().lower())
    return out


def _name_in_text(name_lower, text):
    """True if name appears in text (case-insensitive or capitalized)."""
    if not text or not isinstance(text, str):
        return False
    return name_lower in text.lower() or (name_lower.capitalize() in text and len(name_lower) >= 2)


def _ensure_entity_in_case(asked, case, kb_schema=None):
    """Ensure asked is listed in case['entities'] so downstream validation sees it."""
    if not isinstance(case, dict):
        return
    ents = case.get("entities")
    if isinstance(ents, dict):
        for _t, vals in ents.items():
            if isinstance(vals, list) and asked not in [str(v).strip().lower() for v in vals]:
                vals.append(asked)
                return
    types = (kb_schema or {}).get("types") or []
    primary = types[0] if types else "Person"
    case["entities"] = case.get("entities") or {}
    if not isinstance(case["entities"], dict):
        case["entities"] = {}
    case["entities"].setdefault(primary, []).append(asked)


def _check_entity_consistency(user_question, query_obj, case, case_text=None, kb_schema=None):
    """Raise ValueError if the question asks about an entity but query args/entity use a different one.
    When the question clearly asks about E and E is in the case (or in case_text), fix args/entity to [E]."""
    asked = _entity_asked_about_in_question(user_question)
    if not asked:
        return

    case_entities = set(_case_entity_set(case))
    if asked not in case_entities and case_text and _name_in_text(asked, case_text):
        case_entities.add(asked)
        _ensure_entity_in_case(asked, case, kb_schema)
    if asked not in case_entities:
        return

    q_type = str(query_obj.get("type") or "").strip().lower()
    if q_type == "intent":
        entity = str(query_obj.get("entity") or "").strip().lower()
        if entity and entity != asked:
            query_obj["entity"] = asked
            status_log("Query", "Entity overwrite: question asks about '{}', using entity '{}'".format(asked, asked))
        return

    if q_type == "predicate":
        args = query_obj.get("args") or []
        if not isinstance(args, list):
            return
        args_lower = [str(a).strip().lower() for a in args if a]
        if args_lower and asked not in args_lower:
            query_obj["args"] = [asked]
            status_log("Query", "Entity overwrite: question asks about '{}', using args ['{}']".format(asked, asked))


def _schema_feedback_message(error, previous_output, kb_schema=None):
    """Build schema-aware feedback for LLM repair."""
    msg = (
        "Your previous output did not pass schema validation.\n"
        "Error: " + str(error) + "\n"
        "Previous output: " + json.dumps(previous_output, ensure_ascii=False, indent=2)
    )
    if kb_schema and "Unknown symbol" in str(error):
        preds = [p.get("name") for p in kb_schema.get("predicates", []) if p.get("name")]
        funs = [f.get("name") for f in kb_schema.get("functions", []) if f.get("name")]
        valid = sorted(set(preds + funs))
        if valid:
            msg += "\n\nValid symbols (use EXACT names, case-sensitive): " + ", ".join(valid)
    return msg


def _auto_provider():
    forced = os.getenv("PIPELINE_EXTRACTOR", "").strip().lower()
    if forced:
        return forced

    return "openai"


def extract_case_and_query(case_text, user_question, kb_schema=None, provider="auto", model=None, max_retries=6):
    """Extract raw {case, query} JSON using the configured provider.

    Uses schema-aware feedback loops: case and query are extracted and validated
    separately. Each component retries up to max_retries times with validation
    feedback (IDP-Z3 / schema errors) sent back to the LLM.
    """
    if provider == "auto":
        provider = _auto_provider()

    if provider != "openai":
        raise ExtractionError("Unsupported provider: " + str(provider))

    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"

    # --- Phase 1: Case extraction with feedback loop ---
    case_feedback = None
    case_obj = None
    last_case_error = None
    for case_attempt in range(max_retries):
        if case_attempt == 0:
            status_log("Case", "Extracting")
        else:
            status_log("Case", "Repair attempt {}".format(case_attempt))
        try:
            case_obj = extract_case_only_openai(
                case_text,
                model=chosen_model,
                kb_schema=kb_schema,
                feedback=case_feedback,
            )
        except LLMExtractionError as e:
            raise ExtractionError(str(e))

        try:
            status_log("Case", "Validating")
            case = normalize_and_validate_case(case_obj, kb_schema=kb_schema)
            break
        except ValueError as e:
            last_case_error = e
            case_feedback = _schema_feedback_message(e, case_obj, kb_schema)
    else:
        raise ExtractionError("Case extraction failed after {} repair attempts: {}".format(max_retries, last_case_error))

    # --- Phase 2: Query extraction with feedback loop ---
    query_feedback = None
    query_obj = None
    last_query_error = None
    for query_attempt in range(max_retries):
        if query_attempt == 0:
            status_log("Query", "Extracting")
        else:
            status_log("Query", "Repair attempt {}".format(query_attempt))
        try:
            query_obj = extract_query_only_openai(
                user_question,
                model=chosen_model,
                kb_schema=kb_schema,
                feedback=query_feedback,
            )
        except LLMExtractionError as e:
            raise ExtractionError(str(e))

        try:
            status_log("Query", "Validating")
            _check_entity_consistency(user_question, query_obj, case, case_text=case_text, kb_schema=kb_schema)
            query = normalize_and_validate_query(query_obj, case, kb_schema=kb_schema)
            break
        except ValueError as e:
            last_query_error = e
            query_feedback = _schema_feedback_message(e, query_obj, kb_schema)
    else:
        raise ExtractionError("Query extraction failed after {} repair attempts: {}".format(max_retries, last_query_error))

    return {"case": case, "query": query}


def extract_case_only(case_text, kb_schema=None, provider="auto", model=None, max_retries=6):
    """Extract and validate case facts only. Use for shared case across multiple questions."""
    if provider == "auto":
        provider = _auto_provider()
    if provider != "openai":
        raise ExtractionError("Unsupported provider: " + str(provider))

    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
    case_feedback = None
    case_obj = None
    last_case_error = None
    for case_attempt in range(max_retries):
        if case_attempt == 0:
            status_log("Case", "Extracting")
        else:
            status_log("Case", "Repair attempt {}".format(case_attempt))
        try:
            case_obj = extract_case_only_openai(
                case_text,
                model=chosen_model,
                kb_schema=kb_schema,
                feedback=case_feedback,
            )
        except LLMExtractionError as e:
            raise ExtractionError(str(e))

        try:
            status_log("Case", "Validating")
            case = normalize_and_validate_case(case_obj, kb_schema=kb_schema)
            return case
        except ValueError as e:
            last_case_error = e
            case_feedback = _schema_feedback_message(e, case_obj, kb_schema)
    raise ExtractionError(
        "Case extraction failed after {} repair attempts: {}".format(max_retries, last_case_error)
    )


def extract_query_only(user_question, case, kb_schema=None, provider="auto", model=None, max_retries=6, case_text=None):
    """Extract and validate query only, given an already-validated case."""
    if provider == "auto":
        provider = _auto_provider()
    if provider != "openai":
        raise ExtractionError("Unsupported provider: " + str(provider))

    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
    query_feedback = None
    query_obj = None
    last_query_error = None
    for query_attempt in range(max_retries):
        if query_attempt == 0:
            status_log("Query", "Extracting")
        else:
            status_log("Query", "Repair attempt {}".format(query_attempt))
        try:
            query_obj = extract_query_only_openai(
                user_question,
                model=chosen_model,
                kb_schema=kb_schema,
                feedback=query_feedback,
            )
        except LLMExtractionError as e:
            raise ExtractionError(str(e))

        try:
            status_log("Query", "Validating")
            _check_entity_consistency(user_question, query_obj, case, case_text=case_text, kb_schema=kb_schema)
            query = normalize_and_validate_query(query_obj, case, kb_schema=kb_schema)
            return query
        except ValueError as e:
            last_query_error = e
            query_feedback = _schema_feedback_message(e, query_obj, kb_schema)
    raise ExtractionError(
        "Query extraction failed after {} repair attempts: {}".format(max_retries, last_query_error)
    )
