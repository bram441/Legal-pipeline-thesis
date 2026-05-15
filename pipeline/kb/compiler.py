import os
import json
from pathlib import Path

from pipeline.utils.openai_sampling import chat_completion_sampling_kwargs
from pipeline.utils.prompt_loader import load_json_ir_contract, render_prompt
from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.compile_backend import get_kb_backend_from_env
from pipeline.kb.json_ir import (
    JSONIRCompilationError,
    parse_json_ir,
    render_json_ir_to_fo_and_schema,
)
from pipeline.kb.json_ir_repair import (
    JsonIRErrorKind,
    classify_json_ir_validation_error,
    format_symbol_repair_error,
    normalize_error_signature,
)
from pipeline.kb.law_scope import select_law_text_for_compilation, write_scope_artifacts
from pipeline.kb.repair_hints import build_json_ir_compile_hints, build_machine_repair_hints

_MAX_JSON_IR_ATTEMPTS = int(os.getenv("JSON_IR_MAX_COMPILE_ATTEMPTS", "8"))
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


def _kb_repair_prompt_path(error_message: str) -> str:
    """Pick repair template: syntax (parse/lint), semantic (theory/model), symbolic fallback."""
    e = (error_message or "").lower()
    syntax_markers = (
        "idp failed to parse",
        "expected",
        "kb lint",
        "schema extraction failed",
        "missing 'vocabulary v'",
        "missing 'theory t:v'",
    )
    if any(m in e for m in syntax_markers):
        return "kb/kb_compilation_repair_syntax.txt"
    semantic_markers = (
        "unsatisfiable",
        "no model exists",
        "conflicting assignments",
        "conflicting formulas",
        "kb theory is unsatisfiable",
        "theory is unsatisfiable",
        "rules led to an inconsistency",
        "ordinal must be",
    )
    if any(m in e for m in semantic_markers):
        return "kb/kb_compilation_repair_semantic.txt"
    return "kb/kb_compilation_repair_symbolic.txt"

# Re-export for: from pipeline.kb.compiler import LawCompilationError
__all__ = ["compile_law_to_kb_fo", "LawCompilationError"]


def _compile_direct_kb_single_call(law_text, client, chosen_model):
    """Single LLM call: full vocabulary + theory (original kb_compilation.txt)."""
    user_prompt = render_prompt("kb/kb_compilation.txt", law_text=(law_text or "").strip())
    try:
        resp = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": "You compile legal rules into FO(.) code for IDP-Z3."},
                {"role": "user", "content": user_prompt},
            ],
            **chat_completion_sampling_kwargs(),
        )
    except Exception as e:
        raise LawCompilationError("OpenAI call failed: " + str(e)) from e
    return (resp.choices[0].message.content or "").strip()


def _json_chat_object(client, chosen_model, system_content, user_prompt):
    try:
        req = {
            "model": chosen_model,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_prompt},
            ],
            **chat_completion_sampling_kwargs(),
        }
        # Prefer strict JSON object output when model/API supports it.
        try:
            resp = client.chat.completions.create(
                **req,
                response_format={"type": "json_object"},
            )
        except TypeError:
            resp = client.chat.completions.create(**req)
        except Exception as fmt_exc:
            # Some models reject response_format; fall back to normal call.
            msg = str(fmt_exc).lower()
            if "response_format" in msg or "json_object" in msg:
                resp = client.chat.completions.create(**req)
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
    req = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt},
        ],
        **chat_completion_sampling_kwargs(),
    }
    try:
        resp = client.chat.completions.create(
            **req,
            response_format=_kb_rules_response_format(),
        )
    except Exception as fmt_exc:
        msg = str(fmt_exc).lower()
        if "response_format" in msg or "json_schema" in msg:
            return _json_chat_object(client, chosen_model, system_content, user_prompt)
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
    req = {
        "model": chosen_model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_prompt},
        ],
        **chat_completion_sampling_kwargs(),
    }
    try:
        resp = client.chat.completions.create(
            **req,
            response_format=_kb_symbols_response_format(),
        )
    except Exception as fmt_exc:
        msg = str(fmt_exc).lower()
        if "response_format" in msg or "json_schema" in msg:
            return _json_chat_object(client, chosen_model, system_content, user_prompt)
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
    prompt_name = (
        "kb/kb_compilation_json_ir_symbols_repair.txt"
        if repair
        else "kb/kb_compilation_json_ir_symbols.txt"
    )
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
    st_json = json.dumps(symbol_table, ensure_ascii=False, indent=2)
    if repair:
        rules_prompt = render_prompt(
            "kb/kb_compilation_json_ir_rules_repair.txt",
            law_text=law_text,
            symbol_table_json=st_json,
            error_message=error_message,
            previous_output=previous_output,
            machine_hints=machine_hints,
            json_ir_contract=contract,
        )
    else:
        rules_prompt = render_prompt(
            "kb/kb_compilation_json_ir_rules.txt",
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
) -> str:
    """Select cited/retrieved law slice from natural language (before LE or JSON-IR)."""
    scoped, scope_meta = select_law_text_for_compilation(
        (law_text or "").strip(),
        question_text=question_text,
        case_text=case_text,
    )
    if artifact_dir:
        write_scope_artifacts(str(artifact_dir), scoped, scope_meta)
    return scoped


def _compile_json_ir_two_step(
    source_text,
    client,
    chosen_model,
    *,
    repair_feedback=None,
    artifact_dir: str | Path | None = None,
):
    src = (source_text or "").strip()
    art = Path(artifact_dir) if artifact_dir else None

    error_history: list[str] = []
    if repair_feedback:
        boot = (repair_feedback.get("error_message") or "").strip()
        if boot:
            error_history.append(boot)
    error_signatures: dict[str, int] = {}
    rules_repair_streak = 0
    symbols_repair_count = 0

    symbol_table: dict | None = None
    rules: list | None = None
    raw_symbols = ""
    raw_rules = ""
    symbols_obj: dict | None = None
    rules_obj: dict | None = None

    for attempt in range(1, _MAX_JSON_IR_ATTEMPTS + 1):
        try:
            if symbol_table is None:
                sym_repair = symbols_repair_count > 0
                prev = _json_ir_repair_context(
                    symbol_table=symbol_table,
                    symbols_obj=symbols_obj,
                    raw_symbols=raw_symbols,
                    rules_obj={"rules": rules} if rules is not None else None,
                    merged_ir=(
                        {**symbol_table, "rules": rules}
                        if symbol_table and rules is not None
                        else None
                    ),
                )
                rules_json = json.dumps({"rules": rules}, ensure_ascii=False, indent=2) if rules else ""
                err_msg = error_history[-1] if error_history else ""
                jh = build_json_ir_compile_hints(err_msg) if sym_repair else ""
                symbols_obj, raw_symbols = _call_symbols_llm(
                    client,
                    chosen_model,
                    src,
                    repair=sym_repair,
                    error_message=err_msg,
                    previous_output=prev,
                    rules_json=rules_json,
                    machine_hints=jh,
                )
                symbol_table = _symbol_table_from_obj(symbols_obj)
                for key in ("types", "predicates", "functions"):
                    if not isinstance(symbol_table[key], list):
                        raise JSONIRCompilationError(
                            "JSON IR symbols phase returned invalid %r." % key
                        )
                from pipeline.kb.json_ir import validate_json_ir_symbols

                validate_json_ir_symbols(symbol_table)
                if art:
                    _write_json_ir_artifact(
                        art,
                        attempt,
                        "symbols.normalized.json",
                        json.dumps(symbol_table, ensure_ascii=False, indent=2),
                    )
                    _write_json_ir_artifact(art, attempt, "symbols.raw.json", raw_symbols)

            if rules is None:
                prev = _json_ir_repair_context(
                    symbol_table=symbol_table,
                    raw_symbols=raw_symbols,
                    rules_obj=rules_obj,
                    raw_rules=raw_rules,
                )
                err_msg = error_history[-1] if error_history else ""
                machine_hints = build_machine_repair_hints(err_msg, prev) if err_msg else ""
                jh = build_json_ir_compile_hints(err_msg)
                if jh.strip():
                    machine_hints = (machine_hints + "\n\nJSON IR compile hints:\n" + jh).strip()
                rules_repair = bool(err_msg)
                rules_obj, raw_rules = _call_rules_llm(
                    client,
                    chosen_model,
                    src,
                    symbol_table,
                    repair=rules_repair,
                    error_message=err_msg,
                    previous_output=prev,
                    machine_hints=machine_hints,
                )
                rules = rules_obj.get("rules")
                if not isinstance(rules, list):
                    raise JSONIRCompilationError("JSON IR rules phase returned invalid 'rules'.")
                if art:
                    _write_json_ir_artifact(
                        art, attempt, "rules.raw.json", raw_rules
                    )

            merged_ir = {
                "types": symbol_table["types"],
                "predicates": symbol_table["predicates"],
                "functions": symbol_table["functions"],
                "rules": rules,
            }
            if art:
                _write_json_ir_artifact(
                    art,
                    attempt,
                    "combined_ir.json",
                    json.dumps(merged_ir, ensure_ascii=False, indent=2),
                )
            fo_text, schema = render_json_ir_to_fo_and_schema(merged_ir)
            if art:
                _write_json_ir_artifact(art, attempt, "rendered.fo", fo_text)
            return fo_text, schema

        except JSONIRCompilationError as e:
            msg = str(e)
            error_history.append(msg)
            sig = normalize_error_signature(msg)
            error_signatures[sig] = error_signatures.get(sig, 0) + 1
            kind = classify_json_ir_validation_error(
                msg,
                error_history[:-1],
                rules_repair_count=rules_repair_streak,
                max_rules_before_symbol_escalation=_MAX_RULES_REPAIR_BEFORE_SYMBOL_ESCALATION,
            )
            if error_signatures[sig] >= 2 and kind == JsonIRErrorKind.RULES_REPAIR_ONLY:
                kind = JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED
            if symbol_table is None:
                kind = JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED

            if art:
                sub = art / ("attempt_%02d" % attempt)
                sub.mkdir(parents=True, exist_ok=True)
                (sub / "validation_error.txt").write_text(msg, encoding="utf-8")
                (sub / "error_classification.txt").write_text(kind.value, encoding="utf-8")
                if kind == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED:
                    reason = (
                        "Routed to symbol repair: %s\nSignatures: %s\n"
                        % (msg, json.dumps(error_signatures, indent=2))
                    )
                    (sub / "symbol_repair_reason.txt").write_text(reason, encoding="utf-8")

            if kind == JsonIRErrorKind.SYMBOLS_REPAIR_REQUIRED:
                symbols_repair_count += 1
                rules_repair_streak = 0
                rules = None
                rules_obj = None
                raw_rules = ""
                symbol_table = None
                symbols_obj = None
                continue

            rules_repair_streak += 1
            rules = None
            rules_obj = None
            raw_rules = ""
            continue

    ctx = _json_ir_repair_context(
        symbol_table=symbol_table,
        symbols_obj=symbols_obj,
        raw_symbols=raw_symbols,
        raw_rules=raw_rules,
        rules_obj={"rules": rules} if rules else None,
    )
    summary = (
        "JSON IR compilation failed after %d attempts. Last errors:\n%s"
        % (
            _MAX_JSON_IR_ATTEMPTS,
            "\n---\n".join(error_history[-3:]) if error_history else "(none)",
        )
    )
    raise LawCompilationError(
        summary,
        repair_snapshot={"previous_output": ctx, "error_history": error_history},
    ) from (error_history[-1] if error_history else None)


def compile_law_to_kb_fo(
    law_text,
    model=None,
    repair_feedback=None,
    *,
    question_text=None,
    case_text=None,
    artifact_dir=None,
):
    """Compile natural-language law text into FO(.) (vocabulary + theory only).

    Returns ``(fo_text, kb_schema_dict_or_none)``. For ``json_ir`` backend the second
    value is the normalized symbol JSON (types, predicates, functions with metadata)
    for canonical ``kb_schema.json``; for legacy FO compilation it is ``None``.

    Compilation modes (when not repairing):
    - PIPELINE_USE_LE=0, PIPELINE_KB_TWO_PHASE=0: law → single-shot FO (kb_compilation.txt).
    - PIPELINE_USE_LE=0, PIPELINE_KB_TWO_PHASE=1: law → vocab → theory (kb/*_only.txt).
    - PIPELINE_USE_LE=1, PIPELINE_KB_TWO_PHASE=0: law → LE → single-shot FO (le_to_fo.txt).
    - PIPELINE_USE_LE=1, PIPELINE_KB_TWO_PHASE=1: law → LE → vocab → theory (le/*_only.txt).

    If repair_feedback is set, uses kb_compilation_repair_symbolic.txt (parse/syntax) or
    kb_compilation_repair_semantic.txt (unsat / semantic check), plus machine-detected hints.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise LawCompilationError("Missing OPENAI_API_KEY environment variable")

    provider = (os.getenv("PIPELINE_KB_COMPILER") or "openai").strip().lower()
    if provider != "openai":
        raise LawCompilationError("PIPELINE_KB_COMPILER must be 'openai' for now (got: " + provider + ")")

    try:
        from openai import OpenAI
    except Exception as e:
        raise LawCompilationError("OpenAI SDK not installed/importable: " + str(e))

    client = OpenAI(api_key=api_key)
    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
    sys_msg = "You compile legal rules into FO(.) code for IDP-Z3."

    kb_backend = get_kb_backend_from_env()
    ir_schema = None
    full_law = (law_text or "").strip()
    scoped_law = _scope_law_text_once(
        full_law,
        question_text=question_text,
        case_text=case_text,
        artifact_dir=artifact_dir,
    )

    if repair_feedback:
        if kb_backend == "json_ir":
            return _compile_json_ir_two_step(
                scoped_law,
                client,
                chosen_model,
                repair_feedback=repair_feedback,
                artifact_dir=artifact_dir,
            )
        err = repair_feedback.get("error_message", "") or ""
        prev = repair_feedback.get("previous_output", "") or ""
        prompt_name = _kb_repair_prompt_path(err)
        machine_hints = build_machine_repair_hints(err, prev)
        user_prompt = render_prompt(
            prompt_name,
            law_text=scoped_law,
            error_message=repair_feedback["error_message"],
            previous_output=prev,
            machine_hints=machine_hints,
        )
        try:
            resp = client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": sys_msg},
                    {"role": "user", "content": user_prompt},
                ],
                **chat_completion_sampling_kwargs(),
            )
        except Exception as e:
            raise LawCompilationError("OpenAI call failed: " + str(e)) from e
        text = (resp.choices[0].message.content or "").strip()
    else:
        use_le = False
        try:
            from pipeline.le import use_le_enabled, law_text_to_le, le_to_fo
            use_le = use_le_enabled()
        except ImportError:
            law_text_to_le = None
            le_to_fo = None

        from pipeline.kb.staged_compile import compile_two_phase, two_phase_enabled

        two_ph = two_phase_enabled()

        if use_le and law_text_to_le and le_to_fo:
            try:
                le_text = law_text_to_le(scoped_law, client, chosen_model)
            except Exception as e:
                raise LawCompilationError("Logical English layer failed: " + str(e)) from e
            if artifact_dir:
                try:
                    Path(artifact_dir).mkdir(parents=True, exist_ok=True)
                    (Path(artifact_dir) / "selected_law_le.txt").write_text(
                        le_text.strip() + "\n", encoding="utf-8"
                    )
                except OSError:
                    pass

            if kb_backend == "json_ir":
                text, ir_schema = _compile_json_ir_two_step(
                    le_text,
                    client,
                    chosen_model,
                    artifact_dir=artifact_dir,
                )
            elif two_ph:
                text = compile_two_phase(
                    le_text,
                    client,
                    chosen_model,
                    vocab_prompt="le/le_vocab_only.txt",
                    theory_prompt="le/le_theory_only.txt",
                    system_message=sys_msg,
                    single_shot_fn=lambda: le_to_fo(le_text, client, chosen_model),
                )
            else:
                try:
                    text = le_to_fo(le_text, client, chosen_model)
                except Exception as e:
                    raise LawCompilationError("Logical English layer failed: " + str(e)) from e
        elif kb_backend == "json_ir":
            text, ir_schema = _compile_json_ir_two_step(
                scoped_law,
                client,
                chosen_model,
                artifact_dir=artifact_dir,
            )
        elif two_ph:
            text = compile_two_phase(
                scoped_law,
                client,
                chosen_model,
                system_message=sys_msg,
                single_shot_fn=lambda: _compile_direct_kb_single_call(scoped_law, client, chosen_model),
            )
        else:
            text = _compile_direct_kb_single_call(scoped_law, client, chosen_model)

    if not text:
        raise LawCompilationError("Empty KB output from LLM")

    return text, ir_schema
