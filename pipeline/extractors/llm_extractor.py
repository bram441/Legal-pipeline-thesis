# pipeline/extractors/llm_extractor.py

import os
import json


class LLMExtractionError(Exception):
    pass


def _case_response_format_schema():
    """
    Structured Output schema for case-only extraction.
    Keep it simple and strict: {"facts":[...]} only.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "case_facts_extraction",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["facts"],
                "properties": {
                    "facts": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    }


def _query_response_format_schema():
    """
    Structured Output schema for query-only extraction.

    We keep the fixed-shape query object to avoid anyOf/oneOf issues and
    to satisfy "required includes all properties" constraints in some structured
    output subsets.

    Unused fields must be filled with defaults:
      - for intent queries: predicate="", mode="set", args=[]
      - for predicate queries: intent=""
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "query_extraction",
            "schema": {
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
    }


def _combined_response_format_schema():
    """
    Backwards-compatible wrapper schema: {"case": {"facts":[...]}, "query": {...}}.
    We still return this combined object from extract_case_and_query_llm(),
    but internally we do two calls (case-only + query-only) for determinism.
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


def _build_schema_text(kb_schema):
    if kb_schema is None:
        return ""
    return "\n\nKB_SCHEMA (hard contract):\n" + json.dumps(kb_schema, ensure_ascii=False, indent=2)


def _call_openai_structured(client, model, messages, response_format):
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format=response_format,
        )
    except Exception as e:
        raise LLMExtractionError("OpenAI call failed: " + str(e))

    text = resp.choices[0].message.content
    if not text:
        raise LLMExtractionError("Empty model output")

    return text


def extract_case_and_query_llm(case_text, user_question, model, kb_schema=None, feedback=None):
    """
    Backwards-compatible API: returns JSON TEXT for {"case": {...}, "query": {...}}.

    Internally split extraction into:
      1) case facts only (question NOT shown)
      2) query only (case NOT shown)

    This prevents "case facts drift" where the model omits facts depending on the question.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")

    # Lazy import so dummy mode never requires OpenAI SDK.
    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))

    client = OpenAI(api_key=api_key)

    schema_text = _build_schema_text(kb_schema)

    # ---------------------------
    # 1) CASE-ONLY extraction
    # ---------------------------
    case_rules = (
        "Rules:\n"
        "- Output must be VALID JSON matching the provided schema.\n"
        "- Use lowercase identifiers (snake_case) for constants/individuals.\n"
        "- IMPORTANT: You MUST use ONLY predicate/function symbol NAMES that appear in KB_SCHEMA.\n"
        "- Copy symbol names EXACTLY (case-sensitive). Do NOT invent synonyms.\n"
        "- If you cannot express something with the allowed symbols, OMIT that fact.\n"
        "- Extract ALL expressible facts from the case text; do NOT drop facts because they seem irrelevant.\n"
        "- Facts must be valid FO(.) structure lines ending with '.'.\n"
        "- Do NOT output a 'structure { }' block, only the list of fact lines.\n"
        "\n"
        "NEGATION FORMAT (IMPORTANT):\n"
        "- For negative boolean facts, use: not pred(const).\n"
        "- Do NOT use: pred(const) = false.\n"
        "\n"
        "How to use KB_SCHEMA:\n"
        "- Allowed predicate symbols are KB_SCHEMA.predicates[].name\n"
        "- Allowed function symbols are KB_SCHEMA.functions[].name\n"
        "- Type names (KB_SCHEMA.types) are NOT predicates unless listed as a predicate.\n"
        "\n"
        "Examples (assume KB_SCHEMA has predicates: negligent, causedDamage):\n"
        "- ✅ negligent(alice).\n"
        "- ✅ causedDamage(alice).\n"
        "- ✅ not negligent(bob).\n"
        "- ❌ acted_negligently(alice).   (NOT allowed: invented synonym)\n"
        "- ❌ causes(alice,damage).       (NOT allowed: invented predicate)\n"
        "- ❌ negligent(bob) = false.     (NOT allowed: wrong negation format)\n"
    )

    case_user_content = (
        case_rules
        + schema_text
        + "\n\nCase:\n"
        + str(case_text)
    )

    # If we got validation feedback from json_extractor retry loop, include it here too.
    # It can help the model fix symbol names / syntax in facts.
    if feedback:
        case_user_content += (
            "\n\nValidation feedback (fix your previous JSON):\n"
            + str(feedback)
            + "\n\nReturn corrected JSON only."
        )

    case_messages = [
        {"role": "system", "content": "You extract a minimal legal case facts object."},
        {"role": "user", "content": case_user_content},
    ]

    case_text_out = _call_openai_structured(
        client=client,
        model=model,
        messages=case_messages,
        response_format=_case_response_format_schema(),
    )

    # We expect JSON text; parse here so we can recombine safely.
    try:
        case_obj = json.loads(case_text_out)
    except Exception as e:
        raise LLMExtractionError("Failed to parse case-only JSON: " + str(e))

    if not isinstance(case_obj, dict) or "facts" not in case_obj:
        raise LLMExtractionError("Case-only output shape invalid (expected {'facts':[...]}).")

    # ---------------------------
    # 2) QUERY-ONLY extraction
    # ---------------------------
    query_rules = (
        "Rules:\n"
        "- Output must be VALID JSON matching the provided schema.\n"
        "- Use lowercase identifiers (snake_case) for constants/individuals.\n"
        "- IMPORTANT: You MUST use ONLY predicate/function symbol NAMES that appear in KB_SCHEMA.\n"
        "- Copy symbol names EXACTLY (case-sensitive). Do NOT invent synonyms.\n"
        "\n"
        "CRITICAL:\n"
        "- 'Why' questions are NOT a separate intent.\n"
        "- If the question asks WHY something holds, output the SAME predicate query as the yes/no form,\n"
        "  but set explain=true.\n"
        "\n"
        "When to output type='intent':\n"
        "- Only for explicit meta-requests like '@intent satisfiable', 'is the case consistent?',\n"
        "  'propagate', 'optimize', etc.\n"
        "- If you cannot express the question using allowed symbols, return an intent query with intent='unknown'.\n"
        "\n"
        "Field rules:\n"
        "- For intent queries: type='intent', intent='<name>', explain=false, predicate='', mode='set', args=[]\n"
        "- For predicate queries: type='predicate', intent='', predicate='<name>', mode in {'boolean','set'}.\n"
        "- For predicate boolean queries: args must match predicate arity. For unary predicates: args=['alice'].\n"
        "\n"
        "Examples:\n"
        "- 'Is Alice liable?' -> {type:'predicate', predicate:'liable', mode:'boolean', args:['alice'], explain:false, intent:''}\n"
        "- 'Why is Alice liable?' -> {type:'predicate', predicate:'liable', mode:'boolean', args:['alice'], explain:true, intent:''}\n"
        "- 'Who is liable?' -> {type:'predicate', predicate:'liable', mode:'set', args:[], explain:false, intent:''}\n"
        "- '@intent satisfiable' -> {type:'intent', intent:'satisfiable', explain:false, predicate:'', mode:'set', args:[]}\n"
    )


    query_user_content = (
        query_rules
        + schema_text
        + "\n\nUser question:\n"
        + str(user_question)
    )

    if feedback:
        query_user_content += (
            "\n\nValidation feedback (fix your previous JSON):\n"
            + str(feedback)
            + "\n\nReturn corrected JSON only."
        )

    query_messages = [
        {"role": "system", "content": "You extract a query object for a legal reasoning system."},
        {"role": "user", "content": query_user_content},
    ]

    query_text_out = _call_openai_structured(
        client=client,
        model=model,
        messages=query_messages,
        response_format=_query_response_format_schema(),
    )

    try:
        query_obj = json.loads(query_text_out)
    except Exception as e:
        raise LLMExtractionError("Failed to parse query-only JSON: " + str(e))

    if not isinstance(query_obj, dict):
        raise LLMExtractionError("Query-only output must be a JSON object.")

    # ---------------------------
    # 3) Recombine (backwards-compatible)
    # ---------------------------
    combined = {
        "case": {"facts": case_obj.get("facts", [])},
        "query": query_obj,
    }

    # Optional: sanity check against combined schema constraints (local).
    # This doesn't validate semantics; json_extractor will still do schema validation retries.
    try:
        json.dumps(combined, ensure_ascii=False)
    except Exception as e:
        raise LLMExtractionError("Failed to serialize combined extraction JSON: " + str(e))

    return json.dumps(combined, ensure_ascii=False)
