import os
import json
from pathlib import Path

from pipeline.llm.client import get_llm_client, get_llm_model
from pipeline.llm.request import build_chat_completion_kwargs
from pipeline.utils.llm_call_tracker import tracked_chat_completion_create
from pipeline.utils.prompt_loader import load_json_ir_contract, render_prompt
from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.json_ir import (
    JSONIRCompilationError,
    parse_json_ir,
    render_json_ir_to_fo_and_schema,
)
from pipeline.kb.json_ir_compile_loop import compile_json_ir_structured
from pipeline.kb.json_ir_repair import format_symbol_repair_error
from pipeline.utils.prompt_paths import (
    KB_JSON_IR_RULES,
    KB_JSON_IR_RULES_REPAIR,
    KB_JSON_IR_SYMBOLS,
    KB_JSON_IR_SYMBOLS_REPAIR,
    json_ir_generation_prompts,
)
from pipeline.kb.law_scope import select_law_text_for_compilation, write_scope_artifacts
from pipeline.kb.repair_hints import build_json_ir_compile_hints, build_machine_repair_hints

# Legacy env vars; structured loop uses JSON_IR_MAX_SYMBOL_VERSIONS / JSON_IR_MAX_KB_LLM_CALLS.
_MAX_JSON_IR_ATTEMPTS = int(os.getenv("JSON_IR_MAX_COMPILE_ATTEMPTS", "2"))
_MAX_RULES_REPAIR_BEFORE_SYMBOL_ESCALATION = int(os.getenv("JSON_IR_MAX_RULES_REPAIR", "2"))

# Short system-role guardrails; full spec lives in the rendered user prompts + json_ir_contract.
_KB_JSON_IR_SYSTEM_SYMBOLS = (
    "You are the KB vocabulary (symbols) phase of a legal FO(.) compiler.\n"
    "Output must be exactly one JSON object: parseable by json.loads, first character `{`, last `}`.\n"
    "No markdown, no code fences, no commentary, no explanation keys.\n"
    "Declare only types, predicates (each returns Bool), and functions as specified in the user message — "
    "do not output law rules in this step."
)

_KB_JSON_IR_SYSTEM_RULES = (
    "You are the KB rules phase of a legal FO(.) compiler.\n"
    "Output must be exactly one JSON object: parseable by json.loads, first character `{`, last `}`.\n"
    "No markdown, no code fences, no commentary, no explanation keys.\n"
    "Use only predicate, function, and type names and arities from the symbol table embedded in the user message; "
    "do not invent, rename, or extend the vocabulary."
)

_JSON_IR_REPAIR_CONTEXT_MAX = 18000


def _json_ir_repair_context(
    *,
    raw_symbols: str | None = None,
    symbols_obj: dict | None = None,
    symbol_table: dict | None = None,
    raw_rules: str | None = None,
    rules_obj: dict | None = None,
    merged_ir: dict | None = None,
) -> str:
    """Human-readable bundle for repair prompts (size-capped)."""
    blocks: list[str] = []

    def _dump(label: str, obj: dict | None) -> None:
        if obj is None:
            return
        try:
            s = json.dumps(obj, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            s = repr(obj)
        blocks.append(label + "\n" + s)

    if raw_symbols is not None and raw_symbols.strip():
        rs = raw_symbols.strip()
        if len(rs) > 12000:
            rs = rs[:12000] + "\n... [truncated]"
        blocks.append("=== RAW MODEL OUTPUT (symbols phase) ===\n" + rs)

    if symbol_table is not None:
        _dump("=== SYMBOL TABLE (types/predicates/functions) ===", symbol_table)
    elif symbols_obj is not None:
        _dump("=== PARSED SYMBOLS ROOT JSON ===", symbols_obj)

    if raw_rules is not None and raw_rules.strip():
        rr = raw_rules.strip()
        if len(rr) > 12000:
            rr = rr[:12000] + "\n... [truncated]"
        blocks.append("=== RAW MODEL OUTPUT (rules phase) ===\n" + rr)

    if rules_obj is not None:
        _dump("=== PARSED RULES ROOT JSON ===", rules_obj)

    if merged_ir is not None:
        _dump("=== MERGED IR (symbols + rules before final validation) ===", merged_ir)

    out = "\n\n".join(blocks).strip()
    if len(out) > _JSON_IR_REPAIR_CONTEXT_MAX:
        return out[:_JSON_IR_REPAIR_CONTEXT_MAX] + "\n... [truncated repair context]"
    return out or "(no structured context captured; rely on error_message)"


# Re-export for: from pipeline.kb.compiler import LawCompilationError
__all__ = ["compile_law_to_kb_fo", "LawCompilationError"]


def _json_chat_object(client, chosen_model, system_content, user_prompt, *, stage: str = "kb_symbols"):
    try:
        req = build_chat_completion_kwargs(
            model=chosen_model,
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        # Prefer strict JSON object output when model/API supports it.
        try:
            resp = tracked_chat_completion_create(
                client,
                stage=stage,
                metadata={"response_format": "json_object"},
                **req,
            )
        except TypeError:
            req_fallback = build_chat_completion_kwargs(
                model=chosen_model,
                messages=req["messages"],
            )
            resp = tracked_chat_completion_create(
                client, stage=stage, metadata={"response_format": "fallback"}, **req_fallback
            )
        except Exception as fmt_exc:
            # Some models reject response_format; fall back to normal call.
            msg = str(fmt_exc).lower()
            if "response_format" in msg or "json_object" in msg:
                req_fallback = build_chat_completion_kwargs(
                    model=chosen_model,
                    messages=req["messages"],
                )
                resp = tracked_chat_completion_create(
                    client, stage=stage, metadata={"response_format": "fallback"}, **req_fallback
                )
            else:
                raise
    except Exception as e:
        raise LawCompilationError("OpenAI call failed: " + str(e)) from e
    raw = (resp.choices[0].message.content or "").strip()
    try:
        return parse_json_ir(raw), raw
    except JSONIRCompilationError as e:
        ctx = _json_ir_repair_context(raw_symbols=raw)
        raise LawCompilationError(
            "JSON IR validation failed: " + str(e),
            repair_snapshot={"previous_output": ctx},
        ) from e


_KIND_ENUM = ["observable", "derived", "helper", "conclusion", "input", "unknown"]


def _kb_symbols_response_format() -> dict:
    """Structured outputs for JSON-IR symbol phase (matches normalize_json_ir)."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "kb_json_ir_symbols",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["types", "predicates", "functions"],
                "properties": {
                    "types": {
                        "type": "array",
                        "items": {
                            "anyOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["name"],
                                    "properties": {
                                        "name": {"type": "string"},
                                        "description": {"type": "string"},
                                    },
                                },
                            ]
                        },
                    },
                    "predicates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "args", "returns"],
                            "properties": {
                                "name": {"type": "string"},
                                "args": {"type": "array", "items": {"type": "string"}},
                                "returns": {"type": "string"},
                                "kind": {"type": "string", "enum": _KIND_ENUM},
                                "description": {"type": "string"},
                            },
                        },
                    },
                    "functions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "args", "returns"],
                            "properties": {
                                "name": {"type": "string"},
                                "args": {"type": "array", "items": {"type": "string"}},
                                "returns": {"type": "string"},
                                "kind": {"type": "string", "enum": _KIND_ENUM},
                                "description": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    }


def _kb_rules_response_format() -> dict:
    """Minimal structured envelope: top-level object with ``rules`` array only.

    Rule bodies stay unconstrained here (string FO or object rules); full validation
    remains in ``normalize_json_ir`` / render. Falls back to ``json_object`` on API errors.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "kb_json_ir_rules",
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["rules"],
                "properties": {
                    "rules": {"type": "array"},
                },
            },
        },
    }


def _json_chat_kb_rules(client, chosen_model, system_content, user_prompt):
    """Rules phase: prefer json_schema envelope; fall back to json_object. Returns (parsed_dict, raw_text)."""
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_prompt},
    ]
    req = build_chat_completion_kwargs(
        model=chosen_model,
        messages=messages,
        response_format=_kb_rules_response_format(),
    )
    try:
        resp = tracked_chat_completion_create(
            client,
            stage="kb_rules",
            metadata={"response_format": "json_schema"},
            **req,
        )
    except Exception as fmt_exc:
        msg = str(fmt_exc).lower()
        if "response_format" in msg or "json_schema" in msg:
            return _json_chat_object(client, chosen_model, system_content, user_prompt, stage="kb_rules")
        raise LawCompilationError("OpenAI KB rules call failed: " + str(fmt_exc)) from fmt_exc
    raw = (resp.choices[0].message.content or "").strip()
    try:
        return parse_json_ir(raw), raw
    except JSONIRCompilationError as e:
        ctx = _json_ir_repair_context(raw_rules=raw)
        raise LawCompilationError(
            "JSON IR validation failed: " + str(e),
            repair_snapshot={"previous_output": ctx},
        ) from e


def _json_chat_kb_symbols(client, chosen_model, system_content, user_prompt):
    """Symbols phase with json_schema when supported; else json_object. Returns (parsed_dict, raw_text)."""
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_prompt},
    ]
    req = build_chat_completion_kwargs(
        model=chosen_model,
        messages=messages,
        response_format=_kb_symbols_response_format(),
    )
    try:
        resp = tracked_chat_completion_create(
            client,
            stage="kb_symbols",
            metadata={"response_format": "json_schema"},
            **req,
        )
    except Exception as fmt_exc:
        msg = str(fmt_exc).lower()
        if "response_format" in msg or "json_schema" in msg:
            return _json_chat_object(client, chosen_model, system_content, user_prompt, stage="kb_symbols")
        raise LawCompilationError("OpenAI KB symbols call failed: " + str(fmt_exc)) from fmt_exc
    raw = (resp.choices[0].message.content or "").strip()
    try:
        return parse_json_ir(raw), raw
    except JSONIRCompilationError as e:
        ctx = _json_ir_repair_context(raw_symbols=raw)
        raise LawCompilationError(
            "JSON IR validation failed: " + str(e),
            repair_snapshot={"previous_output": ctx},
        ) from e


def _write_json_ir_artifact(artifact_dir: Path | None, attempt: int, name: str, content: str) -> None:
    if artifact_dir is None:
        return
    sub = artifact_dir / ("attempt_%02d" % attempt)
    sub.mkdir(parents=True, exist_ok=True)
    (sub / name).write_text(content, encoding="utf-8")


def _symbol_table_from_obj(symbols_obj: dict) -> dict:
    return {
        "types": symbols_obj.get("types", []),
        "predicates": symbols_obj.get("predicates", []),
        "functions": symbols_obj.get("functions", []),
    }


def _call_symbols_llm(
    client,
    chosen_model: str,
    law_text: str,
    *,
    repair: bool,
    error_message: str,
    previous_output: str,
    rules_json: str,
    machine_hints: str,
) -> tuple[dict, str]:
    contract = load_json_ir_contract()
    from pipeline.config import json_ir_config

    symbols_prompt_name, _rules_prompt_name = json_ir_generation_prompts()
    prompt_name = KB_JSON_IR_SYMBOLS_REPAIR if repair else symbols_prompt_name
    err_block = error_message
    if repair and rules_json.strip():
        err_block = format_symbol_repair_error(error_message)
    symbols_prompt = render_prompt(
        prompt_name,
        law_text=law_text,
        error_message=err_block,
        previous_output=previous_output,
        machine_hints=machine_hints,
        json_ir_contract=contract,
        rules_json=rules_json or "(no rules yet)",
        rules_exposed_error=error_message if repair else "",
    )
    symbols_obj, raw_symbols = _json_chat_kb_symbols(
        client, chosen_model, _KB_JSON_IR_SYSTEM_SYMBOLS, symbols_prompt
    )
    return symbols_obj, raw_symbols


def _call_rules_llm(
    client,
    chosen_model: str,
    law_text: str,
    symbol_table: dict,
    *,
    repair: bool,
    error_message: str,
    previous_output: str,
    machine_hints: str,
) -> tuple[dict, str]:
    contract = load_json_ir_contract()
    from pipeline.config import json_ir_config

    _symbols_prompt_name, rules_prompt_name = json_ir_generation_prompts()
    st_json = json.dumps(symbol_table, ensure_ascii=False, indent=2)
    if repair:
        rules_prompt = render_prompt(
            KB_JSON_IR_RULES_REPAIR,
            law_text=law_text,
            symbol_table_json=st_json,
            error_message=error_message,
            previous_output=previous_output,
            machine_hints=machine_hints,
            json_ir_contract=contract,
        )
    else:
        rules_prompt = render_prompt(
            rules_prompt_name,
            law_text=law_text,
            symbol_table_json=st_json,
            json_ir_contract=contract,
        )
    return _json_chat_kb_rules(client, chosen_model, _KB_JSON_IR_SYSTEM_RULES, rules_prompt)


def _scope_law_text_once(
    law_text: str,
    *,
    question_text: str | None,
    case_text: str | None,
    artifact_dir: str | Path | None,
) -> tuple[str, dict]:
    """Select cited/retrieved law slice from natural language (before LE or JSON-IR)."""
    scoped, scope_meta = select_law_text_for_compilation(
        (law_text or "").strip(),
        question_text=question_text,
        case_text=case_text,
    )
    if artifact_dir:
        write_scope_artifacts(str(artifact_dir), scoped, scope_meta)
    return scoped, scope_meta


def _compile_json_ir_two_step(
    source_text,
    client,
    chosen_model,
    *,
    repair_feedback=None,
    artifact_dir: str | Path | None = None,
    scope_metadata: dict | None = None,
    question_text: str | None = None,
):
    from pipeline.config import json_ir_config

    src = (source_text or "").strip()
    art = Path(artifact_dir) if artifact_dir else None
    cfg = json_ir_config()

    def _symbols_llm(
        law_text: str,
        *,
        repair: bool,
        error_message: str,
        previous_output: str,
        rules_json: str,
        machine_hints: str,
    ) -> tuple[dict, str]:
        return _call_symbols_llm(
            client,
            chosen_model,
            law_text,
            repair=repair,
            error_message=error_message,
            previous_output=previous_output,
            rules_json=rules_json,
            machine_hints=machine_hints,
        )

    def _rules_llm(
        law_text: str,
        symbol_table: dict,
        *,
        repair: bool,
        error_message: str,
        previous_output: str,
        machine_hints: str,
    ) -> tuple[dict, str]:
        return _call_rules_llm(
            client,
            chosen_model,
            law_text,
            symbol_table,
            repair=repair,
            error_message=error_message,
            previous_output=previous_output,
            machine_hints=machine_hints,
        )

    return compile_json_ir_structured(
        src,
        symbols_llm=_symbols_llm,
        rules_llm=_rules_llm,
        repair_context_fn=_json_ir_repair_context,
        artifact_dir=art,
        repair_feedback=repair_feedback,
        scope_metadata=scope_metadata,
        question_text=question_text,
    )


def compile_law_to_kb_fo(
    law_text,
    model=None,
    repair_feedback=None,
    *,
    question_text=None,
    case_text=None,
    artifact_dir=None,
):
    """Compile natural-language law text into FO(.) via JSON-IR (symbols then rules).

    Returns ``(fo_text, kb_schema_dict)`` where the schema is normalized symbol JSON
    for ``kb_schema.json``. Optional LE: law → LE → JSON-IR when PIPELINE_USE_LE=1.
    """
    provider = (os.getenv("PIPELINE_KB_COMPILER") or "openai").strip().lower()
    if provider != "openai":
        raise LawCompilationError("PIPELINE_KB_COMPILER must be 'openai' for now (got: " + provider + ")")

    try:
        client = get_llm_client()
    except Exception as e:
        raise LawCompilationError(str(e)) from e
    chosen_model = model or get_llm_model()

    full_law = (law_text or "").strip()
    scoped_law, scope_meta = _scope_law_text_once(
        full_law,
        question_text=question_text,
        case_text=case_text,
        artifact_dir=artifact_dir,
    )

    if repair_feedback:
        return _compile_json_ir_two_step(
            scoped_law,
            client,
            chosen_model,
            repair_feedback=repair_feedback,
            artifact_dir=artifact_dir,
            scope_metadata=scope_meta,
            question_text=question_text,
        )

    compile_src = scoped_law
    try:
        from pipeline.le import use_le_enabled, law_text_to_le

        if use_le_enabled():
            le_text = law_text_to_le(scoped_law, client, chosen_model)
            if artifact_dir:
                try:
                    Path(artifact_dir).mkdir(parents=True, exist_ok=True)
                    (Path(artifact_dir) / "selected_law_le.txt").write_text(
                        le_text.strip() + "\n", encoding="utf-8"
                    )
                except OSError:
                    pass
            compile_src = le_text
    except ImportError:
        pass

    text, ir_schema = _compile_json_ir_two_step(
        compile_src,
        client,
        chosen_model,
        artifact_dir=artifact_dir,
        scope_metadata=scope_meta,
        question_text=question_text,
    )

    if not text:
        raise LawCompilationError("Empty KB output from LLM")

    return text, ir_schema
