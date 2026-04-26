import os
import json

from pipeline.utils.prompt_loader import render_prompt
from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.compile_backend import get_kb_backend_from_env
from pipeline.kb.json_ir import JSONIRCompilationError, parse_json_ir, render_json_ir_to_fo
from pipeline.kb.repair_hints import build_machine_repair_hints


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
        return parse_json_ir(raw)
    except JSONIRCompilationError as e:
        raise LawCompilationError("JSON IR validation failed: " + str(e)) from e


def _compile_json_ir_two_step(source_text, client, chosen_model, *, repair_feedback=None):
    src = (source_text or "").strip()
    err = (repair_feedback or {}).get("error_message", "")
    prev = (repair_feedback or {}).get("previous_output", "")

    symbols_prompt = render_prompt(
        "kb/kb_compilation_json_ir_symbols.txt",
        law_text=src,
        error_message=err,
        previous_output=prev,
    )
    symbols_obj = _json_chat_object(
        client,
        chosen_model,
        "You produce ONLY JSON symbol tables for legal FO(.) compilation.",
        symbols_prompt,
    )

    symbol_table = {
        "types": symbols_obj.get("types", []),
        "predicates": symbols_obj.get("predicates", []),
        "functions": symbols_obj.get("functions", []),
    }
    if not isinstance(symbol_table["types"], list):
        raise LawCompilationError("JSON IR symbols phase returned invalid 'types'.")
    if not isinstance(symbol_table["predicates"], list):
        raise LawCompilationError("JSON IR symbols phase returned invalid 'predicates'.")
    if not isinstance(symbol_table["functions"], list):
        raise LawCompilationError("JSON IR symbols phase returned invalid 'functions'.")

    rules_prompt_name = (
        "kb/kb_compilation_json_ir_rules_repair.txt"
        if repair_feedback
        else "kb/kb_compilation_json_ir_rules.txt"
    )
    rules_prompt = render_prompt(
        rules_prompt_name,
        law_text=src,
        symbol_table_json=json.dumps(symbol_table, ensure_ascii=False, indent=2),
        error_message=err,
        previous_output=prev,
    )
    rules_obj = _json_chat_object(
        client,
        chosen_model,
        "You produce ONLY JSON FO(.) rules over a fixed symbol table.",
        rules_prompt,
    )
    rules = rules_obj.get("rules")
    if not isinstance(rules, list):
        raise LawCompilationError("JSON IR rules phase returned invalid 'rules'.")

    try:
        return render_json_ir_to_fo(
            {
                "types": symbol_table["types"],
                "predicates": symbol_table["predicates"],
                "functions": symbol_table["functions"],
                "rules": rules,
            }
        )
    except JSONIRCompilationError as e:
        raise LawCompilationError("JSON IR validation failed: " + str(e)) from e


def compile_law_to_kb_fo(law_text, model=None, repair_feedback=None):
    """Compile natural-language law text into FO(.) (vocabulary + theory only).

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

    if repair_feedback:
        if kb_backend == "json_ir":
            return _compile_json_ir_two_step(
                law_text,
                client,
                chosen_model,
                repair_feedback=repair_feedback,
            )
        err = repair_feedback.get("error_message", "") or ""
        prev = repair_feedback.get("previous_output", "") or ""
        prompt_name = _kb_repair_prompt_path(err)
        machine_hints = build_machine_repair_hints(err, prev)
        user_prompt = render_prompt(
            prompt_name,
            law_text=(law_text or "").strip(),
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
                le_text = law_text_to_le(law_text, client, chosen_model)
            except Exception as e:
                raise LawCompilationError("Logical English layer failed: " + str(e)) from e

            if kb_backend == "json_ir":
                text = _compile_json_ir_two_step(le_text, client, chosen_model)
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
            text = _compile_json_ir_two_step(law_text, client, chosen_model)
        elif two_ph:
            text = compile_two_phase(
                law_text,
                client,
                chosen_model,
                system_message=sys_msg,
                single_shot_fn=lambda: _compile_direct_kb_single_call(law_text, client, chosen_model),
            )
        else:
            text = _compile_direct_kb_single_call(law_text, client, chosen_model)

    if not text:
        raise LawCompilationError("Empty KB output from LLM")

    return text
