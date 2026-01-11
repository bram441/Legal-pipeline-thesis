# pipeline/extractors/json_extractor.py
#
# Stable entrypoint for "NL -> {case, query}" extraction.
# Key design:
# - "auto" provider by default (OpenAI only if configured + available)
# - lazy import of OpenAI extractor so dummy mode never breaks

import json
import os

from pipeline.extractors.dummy_extractor import extract_case_and_query_dummy
from pipeline.schema import normalize_and_validate_case, normalize_and_validate_query


class ExtractionError(Exception):
    pass


# Parses a JSON object from a text blob.
# Supports two modes:
#   1) direct JSON (text is exactly JSON)
#   2) "recovery" mode: finds the first '{' and last '}' and parses that substring
# This is useful when an LLM wraps JSON in additional text.
#
# Params:
#   text (str): Raw string output from an extractor (LLM or simulated boundary).
#
# Returns:
#   dict: Parsed JSON object.
#
# Raises:
#   ExtractionError: If no valid JSON object can be parsed.

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

# Validates and normalizes the extracted JSON payload using pipeline.schema.
# This enforces structural + semantic constraints (identifiers, subset constraints, query rules).
# Returns normalized (case, query) objects if valid.
#
# Params:
#   obj (dict): Parsed extraction output containing at least keys "case" and "query".
#
# Returns:
#   tuple[dict, dict]: (normalized_case, normalized_query)
#
# Raises:
#   ValueError: If the extracted case/query violate schema constraints.

def _validate_case_and_query(obj, kb_schema=None):
    case = normalize_and_validate_case(obj.get("case"), kb_schema=kb_schema)
    query = normalize_and_validate_query(obj.get("query"), case, kb_schema=kb_schema)
    return case, query


def _auto_provider():
    forced = os.getenv("PIPELINE_EXTRACTOR", "").strip().lower()
    if forced:
        return forced

    # Default: use OpenAI only if key exists AND SDK import works; otherwise dummy.
    if os.getenv("OPENAI_API_KEY"):
        try:
            import openai  # noqa: F401
            return "openai"
        except Exception:
            return "dummy"

    return "dummy"

# Top-level extraction entrypoint used by the pipeline.
# Depending on configuration, this may:
#   - use a dummy extractor (no LLM), or
#   - call an LLM extractor that returns JSON text, parse it, then validate it.
# May also retry extraction when validation fails, feeding back the error message.
#
# Params:
#   case_text (str): Natural-language case description.
#   user_question (str): Natural-language user question.
#   provider (str): Which extractor provider to use (e.g., "dummy", "openai", or "auto" if supported in your version).
#   model (str | None): Optional model name when using an LLM provider.
#   max_retries (int): Number of times to retry extraction when validation fails.
#
# Returns:
#   dict: Parsed JSON object {"case": {...}, "query": {...}} (not yet normalized),
#         or normalized depending on your calling convention. In your current pipeline,
#         normalization is done in pipeline/pipeline.py.
#
# Raises:
#   ExtractionError: If extraction/parsing/validation fails after retries.

def extract_case_and_query(case_text, user_question, kb_schema=None, provider="auto", model=None, max_retries=2):
    if provider == "auto":
        provider = _auto_provider()

    if provider == "dummy":
        raw_obj = extract_case_and_query_dummy(case_text, user_question)
        raw_text = json.dumps(raw_obj, ensure_ascii=False)
        return _extract_json_from_text(raw_text)

    if provider != "openai":
        raise ExtractionError("Unknown provider: " + str(provider))

    # Lazy import: prevents OpenAI dependency from breaking dummy mode.
    try:
        from pipeline.extractors.llm_extractor import extract_case_and_query_llm, LLMExtractionError
    except Exception as e:
        raise ExtractionError("OpenAI extractor is not available: " + str(e))

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
            raw_text = extract_case_and_query_llm(
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