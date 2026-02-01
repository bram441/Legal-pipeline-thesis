import json
import os

from pipeline.extraction.openai_extractor import extract_case_and_query_openai, LLMExtractionError
from pipeline.validation.fo_validation import normalize_and_validate_case, normalize_and_validate_query


class ExtractionError(Exception):
    pass


def _extract_json_from_text(text):
    if not isinstance(text, str):
        raise ExtractionError("Extractor output must be a string")

    s = text.strip()
    if not s:
        raise ExtractionError("Extractor output is empty")

    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    first = s.find("{")
    last = s.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ExtractionError("Could not locate a JSON object in extractor output")

    candidate = s[first:last + 1].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ExtractionError("Failed to parse JSON substring: " + str(e))


def _validate_case_and_query(obj, kb_schema=None):
    case = normalize_and_validate_case(obj.get("case"), kb_schema=kb_schema)
    query = normalize_and_validate_query(obj.get("query"), case, kb_schema=kb_schema)
    return case, query


def _auto_provider():
    forced = os.getenv("PIPELINE_EXTRACTOR", "").strip().lower()
    if forced:
        return forced

    return "openai"


def extract_case_and_query(case_text, user_question, kb_schema=None, provider="auto", model=None, max_retries=2):
    """Extract raw {case, query} JSON using the configured provider.

    This function:
    - calls the provider
    - parses JSON safely
    - validates using schema-driven rules
    - retries with validation feedback (LLM-only)
    """
    if provider == "auto":
        provider = _auto_provider()

    if provider != "openai":
        raise ExtractionError("Unsupported provider: " + str(provider))

    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"

    last_error = None
    last_obj = None

    for _ in range(max_retries + 1):
        feedback = None
        if last_error is not None:
            feedback = (
                "Your previous JSON did not pass validation.\n"
                "Validation error: " + str(last_error) + "\n"
                "Previous JSON: " + json.dumps(last_obj, ensure_ascii=False)
            )

        try:
            raw_text = extract_case_and_query_openai(
                case_text,
                user_question,
                model=chosen_model,
                kb_schema=kb_schema,
                feedback=feedback,
            )
        except LLMExtractionError as e:
            raise ExtractionError(str(e))

        obj = _extract_json_from_text(raw_text)

        try:
            _validate_case_and_query(obj, kb_schema=kb_schema)
            return obj
        except ValueError as e:
            last_error = e
            last_obj = obj

    raise ExtractionError("LLM output failed validation after retries: " + str(last_error))
