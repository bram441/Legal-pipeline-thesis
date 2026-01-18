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

    # Lazy import so dummy mode never requires OpenAI SDK.
    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))

    client = OpenAI(api_key=api_key)

    rules = (
        "Rules:\n"
        "- Output must be VALID JSON matching the provided schema.\n"
        "- Use lowercase identifiers (snake_case) for constants/individuals.\n"
        "- IMPORTANT: You MUST use ONLY predicate/function symbol NAMES that appear in KB_SCHEMA.\n"
        "- Copy symbol names EXACTLY (case-sensitive). Do NOT invent synonyms.\n"
        "- If you cannot express something with the allowed symbols, OMIT that fact.\n"
        "- Facts must be valid FO(.) structure lines ending with '.'.\n"
        "- Do NOT output a 'structure { }' block, only the list of fact lines.\n"
        "\n"
        "How to use KB_SCHEMA:\n"
        "- Allowed predicate symbols are KB_SCHEMA.predicates[].name\n"
        "- Allowed function symbols are KB_SCHEMA.functions[].name\n"
        "- Type names (KB_SCHEMA.types) are NOT predicates unless listed as a predicate.\n"
        "\n"
        "Examples (assume KB_SCHEMA has predicates: negligent, causedDamage):\n"
        "- ✅ negligent(alice).\n"
        "- ✅ causedDamage(alice).\n"
        "- ❌ acted_negligently(alice).   (NOT allowed: invented synonym)\n"
        "- ❌ causes(alice,damage).       (NOT allowed: invented predicate)\n"
        "\n"
        "Query:\n"
        "- type='intent' only for meta questions like satisfiable/consistency.\n"
        "- otherwise type='predicate' with predicate/mode/args.\n"
        "- For intent queries: set predicate='' mode='set' args=[] (defaults).\n"
        "- For predicate queries: set intent='' (default).\n"
    )

    schema_text = ""
    if kb_schema is not None:
        schema_text = "\n\nKB_SCHEMA (hard contract):\n" + json.dumps(kb_schema, ensure_ascii=False, indent=2)

    user_content = (
        rules
        + schema_text
        + "\n\nCase:\n" + str(case_text)
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
