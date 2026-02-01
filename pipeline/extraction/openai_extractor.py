import json
import os

from pipeline.utils.prompt_loader import render_prompt


class LLMExtractionError(Exception):
    pass


def _response_format_schema():
    """Structured output schema for query extraction.

    We keep a fixed-shape query object where all fields are always present.
    Unused fields must be filled with defaults by the model:
    - intent query: predicate="", mode="set", args=[]
    - predicate query: intent=""
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "case_query_extraction",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["case", "query"],
                "properties": {
                    "case": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["facts"],
                        "properties": {
                            "facts": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "query": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "explain", "predicate", "mode", "args", "intent"],
                        "properties": {
                            "type": {"type": "string", "enum": ["predicate", "intent"]},
                            "explain": {"type": "boolean"},
                            "predicate": {"type": "string"},
                            "mode": {"type": "string", "enum": ["set", "boolean"]},
                            "args": {"type": "array", "items": {"type": "string"}},
                            "intent": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def extract_case_and_query_openai(case_text, user_question, model, kb_schema=None, feedback=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")

    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))

    client = OpenAI(api_key=api_key)

    kb_schema_json = json.dumps(kb_schema or {}, ensure_ascii=False, indent=2)
    feedback_block = ""
    if feedback:
        feedback_block = "Validation feedback:\n" + str(feedback)

    # ---------------------------
    # CASE-ONLY call
    # ---------------------------
    case_user = render_prompt(
        "openai_extract_case_prompt.txt",
        kb_schema_json=kb_schema_json,
        case_text=str(case_text),
        feedback_block=feedback_block,
    )

    case_resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract case facts only."},
            {"role": "user", "content": case_user},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "case_only",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["facts"],
                    "properties": {"facts": {"type": "array", "items": {"type": "string"}}},
                },
            },
        },
    )

    case_obj = json.loads(case_resp.choices[0].message.content)

    # ---------------------------
    # QUERY-ONLY call
    # ---------------------------
    query_user = render_prompt(
        "openai_extract_query_prompt.txt",
        kb_schema_json=kb_schema_json,
        user_question=str(user_question),
        feedback_block=feedback_block,
    )

    query_resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract query only."},
            {"role": "user", "content": query_user},
        ],
        response_format=_response_format_schema(),
    )

    raw = json.loads(query_resp.choices[0].message.content)
    query_obj = raw.get("query") if isinstance(raw, dict) and "query" in raw else raw

    combined = {"case": {"facts": case_obj.get("facts", [])}, "query": query_obj}
    return json.dumps(combined, ensure_ascii=False)
