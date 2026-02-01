# pipeline/extractors/llm_extractor.py

import os
import json


class LLMExtractionError(Exception):
    pass


def _response_format_schema():
    """
    Some Structured Output schema subsets do NOT allow oneOf/anyOf.
    They also require that 'required' includes every key in 'properties'.

    So we use a fixed-shape query object where all fields are always present.
    Unused fields must be filled with defaults:
      - for intent queries: predicate="", mode="set", args=[]
      - for predicate queries: intent=""
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


def extract_case_and_query_llm(case_text, user_question, model, kb_schema=None, feedback=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")

    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))

    client = OpenAI(api_key=api_key)

    schema_text = ""
    if kb_schema is not None:
        schema_text = "\n\nKB_SCHEMA (hard contract):\n" + json.dumps(kb_schema, ensure_ascii=False, indent=2)

    # ---------------------------
    # CASE-ONLY call
    # ---------------------------
    case_rules = (
        "Rules:\n"
        "- Output must be VALID JSON.\n"
        "- Use lowercase identifiers (snake_case) for constants.\n"
        "- IMPORTANT: Use ONLY predicate/function symbol NAMES from KB_SCHEMA. Copy EXACTLY.\n"
        "- Extract ALL expressible facts. Do NOT drop facts because they seem irrelevant.\n"
        "- Facts must be FO(.) structure lines ending with '.'.\n"
        "- NEGATION: use 'not pred(x).' (do NOT use 'pred(x) = false.').\n"
        "- Output JSON shape: {\"facts\": [\"...\"]}\n"
    )

    case_user = case_rules + schema_text + "\n\nCase:\n" + str(case_text)
    if feedback:
        case_user += "\n\nValidation feedback:\n" + str(feedback)

    case_messages = [
        {"role": "system", "content": "Extract case facts only."},
        {"role": "user", "content": case_user},
    ]

    case_resp = client.chat.completions.create(
        model=model,
        messages=case_messages,
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
    query_rules = (
        "Rules:\n"
        "- Output must be VALID JSON.\n"
        "- Use lowercase identifiers (snake_case) for constants.\n"
        "- IMPORTANT: Use ONLY predicate/function symbol NAMES from KB_SCHEMA. Copy EXACTLY.\n"
        "- 'Why X?' is NOT a separate intent. It is the same predicate query as 'Is X?', but explain=true.\n"
        "- Only use type='intent' for meta questions like satisfiable/propagation/optimization.\n"
        "- Output JSON shape:\n"
        "  {\"type\":\"predicate\"|\"intent\",\"explain\":bool,\"predicate\":\"\",\"mode\":\"set\"|\"boolean\",\"args\":[],\"intent\":\"\"}\n"
        "- For predicate queries: intent=\"\".\n"
        "- For intent queries: predicate=\"\", mode=\"set\", args=[].\n"
    )

    query_user = query_rules + schema_text + "\n\nUser question:\n" + str(user_question)
    if feedback:
        query_user += "\n\nValidation feedback:\n" + str(feedback)

    query_messages = [
        {"role": "system", "content": "Extract query only."},
        {"role": "user", "content": query_user},
    ]

    query_resp = client.chat.completions.create(
        model=model,
        messages=query_messages,
        response_format=_response_format_schema(),  # reuse your existing combined schema
    )

    # We used your combined schema, but we only need query part.
    # Safer: parse and take the "query" field if present; else parse as query itself.
    raw = json.loads(query_resp.choices[0].message.content)
    query_obj = raw.get("query") if isinstance(raw, dict) and "query" in raw else raw

    combined = {"case": {"facts": case_obj.get("facts", [])}, "query": query_obj}
    return json.dumps(combined, ensure_ascii=False)
