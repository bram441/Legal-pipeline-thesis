# pipeline/extractors/llm_extractor.py

import os


class LLMExtractionError(Exception):
    pass

# Defines the JSON Schema used to constrain the LLM output shape (Structured Outputs).
# This schema is intentionally limited to structural/type constraints (keys + basic types).
# Cross-field semantic constraints are enforced later by pipeline/schema.py.
#
# Params:
#   (none)
#
# Returns:
#   dict: A response_format payload specifying a strict json_schema for the LLM response.

def _response_format_schema():
    # Keep schema simple; semantic constraints live in pipeline/schema.py
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "case_query_extraction",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["case", "query"],
                "properties": {
                    "case": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["parties", "negligent", "caused_damage"],
                        "properties": {
                            "parties": {"type": "array", "items": {"type": "string"}},
                            "negligent": {"type": "array", "items": {"type": "string"}},
                            "caused_damage": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "query": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "predicate", "mode", "args", "explain"],
                        "properties": {
                            "type": {"type": "string", "enum": ["predicate"]},
                            "predicate": {"type": "string"},
                            "mode": {"type": "string", "enum": ["set", "boolean"]},
                            "args": {"type": "array", "items": {"type": "string"}},
                            "explain": {"type": "boolean"},
                        },
                    },
                },
            },
        },
    }

# Calls an LLM to extract a structured {"case": {...}, "query": {...}} object
# from (case_text, user_question). Uses Structured Outputs (JSON Schema) to force
# well-formed JSON and stable keys/types. Optionally accepts validation feedback
# to retry and correct previously invalid outputs.
#
# Params:
#   case_text (str): Natural-language case description.
#   user_question (str): Natural-language question to be answered.
#   model (str): Model identifier to use for extraction.
#   feedback (str | None): Optional error feedback and previous JSON to guide a retry.
#
# Returns:
#   str: JSON string (the model output) that should parse into {"case": {...}, "query": {...}}.
#
# Raises:
#   LLMExtractionError: If the API key is missing, the SDK is unavailable, or the API call fails.

def extract_case_and_query_llm(case_text, user_question, model, feedback=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")

    # Lazy import so dummy mode never requires OpenAI SDK.
    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))

    client = OpenAI(api_key=api_key)

    rules = (
        "Rules:\n"
        "- Output must be VALID JSON matching the provided schema.\n"
        "- Use lowercase identifiers and underscores.\n"
        "- negligent and caused_damage must be subsets of parties.\n"
        "- If unknown, use empty lists.\n"
        "- query.mode:\n"
        "  - 'set' -> args MUST be []\n"
        "  - 'boolean' -> args MUST contain exactly one party\n"
        "\n"
        "IMPORTANT SEMANTICS:\n"
        "- caused_damage lists parties who CAUSED damage (actor), not the victim.\n"
    )

    user_content = (
        rules
        + "\nCase:\n" + str(case_text)
        + "\n\nUser question:\n" + str(user_question)
    )

    if feedback:
        user_content += (
            "\n\nValidation feedback (fix your previous JSON):\n"
            + str(feedback)
            + "\n\nReturn corrected JSON only."
        )

    messages = [
        {"role": "system", "content": "You extract a minimal legal case object and a query object."},
        {"role": "user", "content": user_content},
    ]

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=_response_format_schema(),
        )
    except Exception as e:
        raise LLMExtractionError("OpenAI call failed: " + str(e))

    text = resp.choices[0].message.content
    if not text:
        raise LLMExtractionError("Empty model output")

    return text
