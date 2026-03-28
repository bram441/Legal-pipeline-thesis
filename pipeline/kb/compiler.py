import os

from pipeline.utils.prompt_loader import render_prompt
from pipeline.kb.exceptions import LawCompilationError

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


def compile_law_to_kb_fo(law_text, model=None, repair_feedback=None):
    """Compile natural-language law text into FO(.) (vocabulary + theory only).

    Compilation modes (when not repairing):
    - PIPELINE_USE_LE=0, PIPELINE_KB_TWO_PHASE=0: law → single-shot FO (kb_compilation.txt).
    - PIPELINE_USE_LE=0, PIPELINE_KB_TWO_PHASE=1: law → vocab → theory (kb/*_only.txt).
    - PIPELINE_USE_LE=1, PIPELINE_KB_TWO_PHASE=0: law → LE → single-shot FO (le_to_fo.txt).
    - PIPELINE_USE_LE=1, PIPELINE_KB_TWO_PHASE=1: law → LE → vocab → theory (le/*_only.txt).

    If repair_feedback is set, uses kb_compilation_repair*.txt with full previous output.
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

    if repair_feedback:
        err = repair_feedback.get("error_message", "") or ""
        is_unsat = any(
            s in err for s in ("unsatisfiable", "Conflicting", "rules led to an inconsistency")
        )
        prompt_name = (
            "kb/kb_compilation_repair_unsat.txt" if is_unsat else "kb/kb_compilation_repair.txt"
        )
        user_prompt = render_prompt(
            prompt_name,
            law_text=(law_text or "").strip(),
            error_message=repair_feedback["error_message"],
            previous_output=repair_feedback["previous_output"],
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

            if two_ph:
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
