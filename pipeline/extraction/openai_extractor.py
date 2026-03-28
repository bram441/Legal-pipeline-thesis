import json
import os

from pipeline.utils.prompt_loader import render_prompt


class LLMExtractionError(Exception):
    pass


def _query_schema():
    """Query-only schema for extract_query_only_openai."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "query_only",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "explain", "predicate", "mode", "args", "intent", "symbol", "entity"],
                "properties": {
                    "type": {"type": "string", "enum": ["predicate", "intent"]},
                    "explain": {"type": "boolean"},
                    "predicate": {"type": "string"},
                    "mode": {"type": "string", "enum": ["set", "boolean"]},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "intent": {"type": "string"},
                    "symbol": {"type": "string"},
                    "entity": {"type": "string"},
                },
            },
        },
    }


def _response_format_schema():
    """Full case+query schema for backward compatibility."""
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
                        "required": ["type", "explain", "predicate", "mode", "args", "intent", "symbol", "entity"],
                        "properties": {
                            "type": {"type": "string", "enum": ["predicate", "intent"]},
                            "explain": {"type": "boolean"},
                            "predicate": {"type": "string"},
                            "mode": {"type": "string", "enum": ["set", "boolean"]},
                            "args": {"type": "array", "items": {"type": "string"}},
                            "intent": {"type": "string"},
                            "symbol": {"type": "string"},
                            "entity": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def _feedback_block(feedback):
    if not feedback:
        return ""
    return "Validation feedback (schema-aware):\n" + str(feedback)


def extract_case_only_openai(case_text, model, kb_schema=None, feedback=None):
    """Extract case facts only. Used by schema-aware feedback loop."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")

    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))

    client = OpenAI(api_key=api_key)
    kb_schema_json = json.dumps(kb_schema or {}, ensure_ascii=False, indent=2)

    case_user = render_prompt(
        "extraction/openai_extract_case_prompt.txt",
        kb_schema_json=kb_schema_json,
        case_text=str(case_text),
        feedback_block=_feedback_block(feedback),
    )

    resp = client.chat.completions.create(
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

    return json.loads(resp.choices[0].message.content)


def extract_query_only_openai(user_question, model, kb_schema=None, feedback=None):
    """Extract query only. Used by schema-aware feedback loop."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")

    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))

    client = OpenAI(api_key=api_key)
    kb_schema_json = json.dumps(kb_schema or {}, ensure_ascii=False, indent=2)

    query_user = render_prompt(
        "extraction/openai_extract_query_prompt.txt",
        kb_schema_json=kb_schema_json,
        user_question=str(user_question),
        feedback_block=_feedback_block(feedback),
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract query only."},
            {"role": "user", "content": query_user},
        ],
        response_format=_query_schema(),
    )

    return json.loads(resp.choices[0].message.content)


def extract_case_and_query_openai(case_text, user_question, model, kb_schema=None, feedback=None,
                                  case_feedback=None, query_feedback=None):
    """Extract case and query. Supports component-specific feedback for repair loops."""
    case_fb = case_feedback if case_feedback is not None else feedback
    query_fb = query_feedback if query_feedback is not None else feedback

    case_obj = extract_case_only_openai(case_text, model, kb_schema=kb_schema, feedback=case_fb)
    query_obj = extract_query_only_openai(user_question, model, kb_schema=kb_schema, feedback=query_fb)

    combined = {"case": {"facts": case_obj.get("facts", [])}, "query": query_obj}
    return json.dumps(combined, ensure_ascii=False)
