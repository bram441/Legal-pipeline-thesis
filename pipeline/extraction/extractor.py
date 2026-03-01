import json
import os

from debug import status_log
from pipeline.extraction.openai_extractor import (
    extract_case_only_openai,
    extract_query_only_openai,
    LLMExtractionError,
)
from pipeline.validation.fo_validation import normalize_and_validate_case, normalize_and_validate_query


class ExtractionError(Exception):
    pass


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
            query = normalize_and_validate_query(query_obj, case, kb_schema=kb_schema)
            break
        except ValueError as e:
            last_query_error = e
            query_feedback = _schema_feedback_message(e, query_obj, kb_schema)
    else:
        raise ExtractionError("Query extraction failed after {} repair attempts: {}".format(max_retries, last_query_error))

    return {"case": case, "query": query}
