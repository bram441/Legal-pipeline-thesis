# pipeline/extractors/json_extractor.py
#
# Purpose:
#   Single stable entrypoint for "NL -> {case, query}" extraction.
#   Today: uses dummy extractor but still goes through JSON-string parsing
#          to simulate an LLM output boundary.
#   Later: swap the provider to an actual LLM that returns a JSON string.
#
# Design goals:
#   - debuggable: clear error messages, includes raw output on failure
#   - minimal: no advanced semantics, schema validation happens elsewhere
#   - future-proof: provider pluggable, parsing centralized


# pipeline/extractors/json_extractor.py

import json

from pipeline.extractors.dummy_extractor import extract_case_and_query_dummy
from pipeline.extractors.llm_extractor import extract_case_and_query_llm, LLMExtractionError
from pipeline.schema import normalize_and_validate_case, normalize_and_validate_query


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

    candidate = s[first : last + 1].strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        raise ExtractionError("Failed to parse JSON substring: " + str(e))


def _validate_case_and_query(obj):
    case = normalize_and_validate_case(obj.get("case"))
    query = normalize_and_validate_query(obj.get("query"), case)
    return case, query


def extract_case_and_query(case_text, user_question, provider="openai", model="gpt-4.1-mini", max_retries=2):
    if provider == "dummy":
        raw_obj = extract_case_and_query_dummy(case_text, user_question)
        raw_text = json.dumps(raw_obj, ensure_ascii=False)
        parsed = _extract_json_from_text(raw_text)
        return parsed

    if provider != "openai":
        raise ExtractionError("Unknown provider: " + str(provider))

    last_error = None
    last_obj = None

    for attempt in range(max_retries + 1):
        feedback = None
        if last_error is not None:
            feedback = (
                "Your previous JSON did not pass validation.\n"
                "Error: " + str(last_error) + "\n"
                "Previous JSON: " + json.dumps(last_obj, ensure_ascii=False)
            )

        try:
            raw_text = extract_case_and_query_llm(case_text, user_question, model=model, feedback=feedback)
        except LLMExtractionError as e:
            raise ExtractionError(str(e))

        obj = _extract_json_from_text(raw_text)

        try:
            _validate_case_and_query(obj)
            return obj
        except ValueError as e:
            last_error = e
            last_obj = obj

    raise ExtractionError("LLM output failed validation after retries: " + str(last_error))
