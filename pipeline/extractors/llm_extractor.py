# pipeline/extractors/llm_extractor.py

import os
from openai import OpenAI


class LLMExtractionError(Exception):
    pass


def _response_format_schema():
    # Keep this SIMPLE: no oneOf/anyOf conditionals.
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


def extract_case_and_query_llm(case_text, user_question, model, feedback=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")

    client = OpenAI(api_key=api_key)

    rules = (
        "Rules:\n"
        "- Use lowercase identifiers, underscores instead of spaces\n"
        "- negligent and caused_damage must be subsets of parties\n"
        "- If unknown, use empty lists\n"
        "- query.mode:\n"
        "  - 'set' means args MUST be []\n"
        "  - 'boolean' means args MUST be exactly one party identifier\n"
        "- Return only JSON matching the provided schema\n"
    )

    user_content = (
        rules
        + "\nCase:\n"
        + str(case_text)
        + "\n\nUser question:\n"
        + str(user_question)
    )

    if feedback:
        user_content += (
            "\n\nValidation feedback:\n"
            + str(feedback)
            + "\n\nPlease return a corrected JSON object only."
        )

    messages = [
        {"role": "system", "content": "You extract a minimal legal case object and query object."},
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

    try:
        text = resp.choices[0].message.content
    except Exception:
        raise LLMExtractionError("No message content returned from model")

    if not text:
        raise LLMExtractionError("Empty model output")

    return text
