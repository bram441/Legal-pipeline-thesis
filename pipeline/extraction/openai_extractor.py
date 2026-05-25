import json
import os

from pipeline.utils.openai_sampling import chat_completion_sampling_kwargs
from pipeline.utils.llm_call_tracker import tracked_chat_completion_create
from pipeline.utils.prompt_loader import (
    PromptError,
    load_json_ir_contract,
    load_prompt,
    render_prompt,
)
from pipeline.utils.prompt_paths import (
    EXTRACTION_JSON_IR_CASE,
    EXTRACTION_JSON_IR_CASE_REPAIR,
    EXTRACTION_JSON_IR_QUERY,
    EXTRACTION_JSON_IR_QUERY_REPAIR,
    EXTRACTION_LEGACY_CASE,
    EXTRACTION_LEGACY_CASE_REPAIR,
    EXTRACTION_LEGACY_QUERY,
    EXTRACTION_LEGACY_QUERY_REPAIR,
    EXTRACTION_WORLD_KNOWLEDGE,
)


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
                                "evidence_text": {"type": "string"},
                                "source": {"type": "string"},
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
    from pipeline.symbolic.intent_registry import list_public_intents

    public_intents = list(list_public_intents())
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
                    "focus_symbols",
                    "focus_entities",
                    "max_models",
                    "function",
                    "direction",
                    "target_type",
                ],
                "properties": {
                    "kind": {"type": "string", "enum": ["predicate", "intent"]},
                    "predicate_hint": {"type": "string"},
                    "mode": {"type": "string", "enum": ["set", "boolean"]},
                    "args": {"type": "array", "items": {"type": "string"}},
                    "intent": {"type": "string", "enum": public_intents},
                    "symbol_hint": {"type": "string"},
                    "entity_hint": {"type": "string"},
                    "explain": {"type": "boolean"},
                    "focus_symbols": {"type": "array", "items": {"type": "string"}},
                    "focus_entities": {"type": "array", "items": {"type": "string"}},
                    "max_models": {"type": "integer"},
                    "function": {"type": "string"},
                    "direction": {"type": "string", "enum": ["min", "max", ""]},
                    "target_type": {"type": "string", "enum": ["predicate", "satisfiable", ""]},
                    "include_unknown": {"type": "boolean"},
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
    return load_prompt(EXTRACTION_WORLD_KNOWLEDGE).strip()


def _extraction_repair_preamble(repair_template_rel: str, feedback) -> str:
    """Prepend strict repair text + validation error. Uses replace() so embedded JSON in feedback does not break render_prompt."""
    if feedback is None or not str(feedback).strip():
        return ""
    tmpl = load_prompt(repair_template_rel)
    needle = "{validation_feedback}"
    if needle not in tmpl:
        raise PromptError("Repair template missing " + needle + ": " + repair_template_rel)
    body = tmpl.replace(needle, str(feedback).strip())
    return body.strip() + "\n\n"


def _json_ir_extraction_repair_preamble(is_case: bool, feedback) -> str:
    rel = EXTRACTION_JSON_IR_CASE_REPAIR if is_case else EXTRACTION_JSON_IR_QUERY_REPAIR
    return _extraction_repair_preamble(rel, feedback)


def _legacy_extraction_repair_preamble(is_case: bool, feedback) -> str:
    rel = EXTRACTION_LEGACY_CASE_REPAIR if is_case else EXTRACTION_LEGACY_QUERY_REPAIR
    return _extraction_repair_preamble(rel, feedback)


def _schema_environment_view(kb_schema, schema_environment=None) -> str:
    if schema_environment:
        from pipeline.kb.schema_environment import schema_environment_prompt_view

        return schema_environment_prompt_view(schema_environment)
    if kb_schema:
        from pipeline.kb.schema_environment import build_schema_environment, schema_environment_prompt_view

        return schema_environment_prompt_view(build_schema_environment(kb_schema))
    return ""


def extract_case_only_openai(case_text, model, kb_schema=None, feedback=None, schema_environment=None):
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

    case_user = _legacy_extraction_repair_preamble(True, feedback) + render_prompt(
        EXTRACTION_LEGACY_CASE,
        kb_schema_json=kb_schema_json,
        case_text=str(case_text),
        feedback_block=_feedback_block(feedback),
        world_knowledge_lexical=_lexical_world_knowledge_block(),
    )

    resp = tracked_chat_completion_create(
        client,
        stage="case_extraction",
        model=model,
        messages=[
            {"role": "system", "content": "Extract case facts only."},
            {"role": "user", "content": case_user},
        ],
        metadata={"backend": "legacy"},
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


def extract_case_ir_only_openai(case_text, model, kb_schema=None, feedback=None, schema_environment=None):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LLMExtractionError("Missing OPENAI_API_KEY environment variable")
    try:
        from openai import OpenAI
    except Exception as e:
        raise LLMExtractionError("OpenAI SDK not installed or not importable: " + str(e))
    client = OpenAI(api_key=api_key)
    kb_schema_json = json.dumps(kb_schema or {}, ensure_ascii=False, indent=2)
    user_msg = _json_ir_extraction_repair_preamble(True, feedback) + render_prompt(
        EXTRACTION_JSON_IR_CASE,
        kb_schema_json=kb_schema_json,
        schema_environment_view=_schema_environment_view(kb_schema, schema_environment),
        case_text=str(case_text),
        feedback_block=_feedback_block(feedback),
        world_knowledge_lexical=_lexical_world_knowledge_block(),
        json_ir_contract=load_json_ir_contract(),
    )
    resp = tracked_chat_completion_create(
        client,
        stage="case_extraction",
        model=model,
        messages=[
            {"role": "system", "content": "Extract case IR only."},
            {"role": "user", "content": user_msg},
        ],
        metadata={"backend": "json_ir"},
        **chat_completion_sampling_kwargs(),
        response_format=_case_ir_schema(),
    )
    return json.loads(resp.choices[0].message.content)


def extract_query_ir_only_openai(user_question, model, kb_schema=None, case=None, feedback=None, schema_environment=None):
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
    user_msg = _json_ir_extraction_repair_preamble(False, feedback) + render_prompt(
        EXTRACTION_JSON_IR_QUERY,
        kb_schema_json=kb_schema_json,
        schema_environment_view=_schema_environment_view(kb_schema, schema_environment),
        user_question=str(user_question),
        case_facts_json=case_facts_json,
        case_entities_json=case_entities_json,
        feedback_block=_feedback_block(feedback),
        world_knowledge_lexical=_lexical_world_knowledge_block(),
        json_ir_contract=load_json_ir_contract(),
    )
    resp = tracked_chat_completion_create(
        client,
        stage="query_extraction",
        model=model,
        messages=[
            {"role": "system", "content": "Extract query IR only."},
            {"role": "user", "content": user_msg},
        ],
        metadata={"backend": "json_ir"},
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

    query_user = _legacy_extraction_repair_preamble(False, feedback) + render_prompt(
        EXTRACTION_LEGACY_QUERY,
        kb_schema_json=kb_schema_json,
        user_question=str(user_question),
        case_facts_json=case_facts_json,
        case_entities_json=case_entities_json,
        feedback_block=_feedback_block(feedback),
        world_knowledge_lexical=_lexical_world_knowledge_block(),
    )

    resp = tracked_chat_completion_create(
        client,
        stage="query_extraction",
        model=model,
        messages=[
            {"role": "system", "content": "Extract query only."},
            {"role": "user", "content": query_user},
        ],
        metadata={"backend": "legacy"},
        **chat_completion_sampling_kwargs(),
        response_format=_query_schema(),
    )

    return json.loads(resp.choices[0].message.content)


