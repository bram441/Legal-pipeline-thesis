import json
import os

from pipeline.utils.openai_sampling import chat_completion_sampling_kwargs
from pipeline.utils.prompt_loader import load_json_ir_contract, load_prompt, render_prompt


class LLMExtractionError(Exception):
    pass


def _query_schema():
    """Query-only schema for extract_query_only_openai.

    OpenAI structured outputs reject many root-level ``oneOf`` shapes; use one flat
    object and validate ``type``/``intent`` in Python (``normalize_and_validate_query``).
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "query_only",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "type",
                    "explain",
                    "predicate",
                    "mode",
                    "args",
                    "intent",
                    "symbol",
                    "entity",
                ],
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


def _case_ir_schema():
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "case_ir",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["entities", "assertions", "value_assertions"],
                "properties": {
                    "entities": {
                        "type": "object",
                        "additionalProperties": {"type": "array", "items": {"type": "string"}},
                    },
                    "assertions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["symbol", "args", "negated"],
                            "properties": {
                                "symbol": {"type": "string"},
                                "args": {"type": "array", "items": {"type": "string"}},
                                "negated": {"type": "boolean"},
                            },
                        },
                    },
                    "value_assertions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["symbol", "args", "value"],
                            "properties": {
                                "symbol": {"type": "string"},
                                "args": {"type": "array", "items": {"type": "string"}},
                                "value": {
                                    "anyOf": [
                                        {"type": "string"},
                                        {"type": "number"},
                                        {"type": "integer"},
                                        {"type": "boolean"}
                                    ]
                                },
                            },
                        },
                    },
                },
            },
        },
    }


def _query_ir_schema():
    """Flat object schema (no ``oneOf``) for OpenAI structured output compatibility."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "query_ir",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "kind",
                    "predicate_hint",
                    "mode",
                    "args",
                    "intent",
                    "symbol_hint",
                    "entity_hint",
                    "explain",
                ],
                "properties": {
                    "kind": {"type": "string", "enum": ["predicate", "intent"]},
                    "predicate_hint": {"type": "string"},
                    "mode": {"type": "string", "enum": ["set", "boolean"]},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "intent": {"type": "string"},
                    "symbol_hint": {"type": "string"},
                    "entity_hint": {"type": "string"},
                    "explain": {"type": "boolean"},
                },
            },
        },
    }


def _feedback_block(feedback):
    if not feedback:
        return ""
    return "Validation feedback (schema-aware):\n" + str(feedback)


def _lexical_world_knowledge_block() -> str:
    """Shared kinship / multi-party lexical hints; edit prompts/extraction/world_knowledge_lexical.txt."""
    return load_prompt("extraction/world_knowledge_lexical.txt").strip()


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
        world_knowledge_lexical=_lexical_world_knowledge_block(),
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract case facts only."},
            {"role": "user", "content": case_user},
        ],
        **chat_completion_sampling_kwargs(),
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "case_only",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["facts", "entities"],
                    "properties": {
                        "facts": {"type": "array", "items": {"type": "string"}},
                        "entities": {
                            "type": "object",
                            "additionalProperties": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    )

    return json.loads(resp.choices[0].message.content)


def extract_case_ir_only_openai(case_text, model, kb_schema=None, feedback=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")
    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))
    client = OpenAI(api_key=api_key)
    kb_schema_json = json.dumps(kb_schema or {}, ensure_ascii=False, indent=2)
    user_msg = render_prompt(
        "extraction/openai_extract_case_json_ir_prompt.txt",
        kb_schema_json=kb_schema_json,
        case_text=str(case_text),
        feedback_block=_feedback_block(feedback),
        world_knowledge_lexical=_lexical_world_knowledge_block(),
        json_ir_contract=load_json_ir_contract(),
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract case IR only."},
            {"role": "user", "content": user_msg},
        ],
        **chat_completion_sampling_kwargs(),
        response_format=_case_ir_schema(),
    )
    return json.loads(resp.choices[0].message.content)


def extract_query_ir_only_openai(user_question, model, kb_schema=None, case=None, feedback=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")
    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))
    client = OpenAI(api_key=api_key)
    kb_schema_json = json.dumps(kb_schema or {}, ensure_ascii=False, indent=2)
    case_obj = case or {}
    case_facts_json = json.dumps((case_obj.get("facts") or []), ensure_ascii=False, indent=2)
    case_entities_json = json.dumps((case_obj.get("entities") or {}), ensure_ascii=False, indent=2)
    user_msg = render_prompt(
        "extraction/openai_extract_query_json_ir_prompt.txt",
        kb_schema_json=kb_schema_json,
        user_question=str(user_question),
        case_facts_json=case_facts_json,
        case_entities_json=case_entities_json,
        feedback_block=_feedback_block(feedback),
        world_knowledge_lexical=_lexical_world_knowledge_block(),
        json_ir_contract=load_json_ir_contract(),
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract query IR only."},
            {"role": "user", "content": user_msg},
        ],
        **chat_completion_sampling_kwargs(),
        response_format=_query_ir_schema(),
    )
    return json.loads(resp.choices[0].message.content)


def extract_query_only_openai(user_question, model, kb_schema=None, case=None, feedback=None):
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
    case_obj = case or {}
    case_facts_json = json.dumps((case_obj.get("facts") or []), ensure_ascii=False, indent=2)
    case_entities_json = json.dumps((case_obj.get("entities") or {}), ensure_ascii=False, indent=2)

    query_user = render_prompt(
        "extraction/openai_extract_query_prompt.txt",
        kb_schema_json=kb_schema_json,
        user_question=str(user_question),
        case_facts_json=case_facts_json,
        case_entities_json=case_entities_json,
        feedback_block=_feedback_block(feedback),
        world_knowledge_lexical=_lexical_world_knowledge_block(),
    )

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Extract query only."},
            {"role": "user", "content": query_user},
        ],
        **chat_completion_sampling_kwargs(),
        response_format=_query_schema(),
    )

    return json.loads(resp.choices[0].message.content)


