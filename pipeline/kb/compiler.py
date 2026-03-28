import os

from pipeline.utils.prompt_loader import render_prompt


class LawCompilationError(Exception):
    pass


def compile_law_to_kb_fo(law_text, model=None, repair_feedback=None):
    """Compile natural-language law text into FO(.) (vocabulary + theory only).

    Notes
    - This function MUST return only FO(.) code (no structure).
    - It is LLM-backed, but it should be deterministic in *format*.
    - If repair_feedback is provided, uses repair prompt with error and previous output.
    - When PIPELINE_USE_LE=1, first converts law text to Logical English, then LE to FO(.) (repair still uses direct law_text).
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

    if repair_feedback:
        err = repair_feedback.get("error_message", "") or ""
        is_unsat = any(
            s in err for s in ("unsatisfiable", "Conflicting", "rules led to an inconsistency")
        )
        prompt_name = "kb_compilation_repair_unsat.txt" if is_unsat else "kb_compilation_repair.txt"
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
                    {"role": "system", "content": "You compile legal rules into FO(.) code for IDP-Z3."},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as e:
            raise LawCompilationError("OpenAI call failed: " + str(e))
        text = (resp.choices[0].message.content or "").strip()
    else:
        use_le = False
        try:
            from pipeline.le import use_le_enabled, law_text_to_le, le_to_fo
            use_le = use_le_enabled()
        except ImportError:
            pass

        if use_le:
            try:
                le_text = law_text_to_le(law_text, client, chosen_model)
                text = le_to_fo(le_text, client, chosen_model)
            except Exception as e:
                raise LawCompilationError("Logical English layer failed: " + str(e))
        else:
            user_prompt = render_prompt("kb_compilation.txt", law_text=(law_text or "").strip())
            try:
                resp = client.chat.completions.create(
                    model=chosen_model,
                    messages=[
                        {"role": "system", "content": "You compile legal rules into FO(.) code for IDP-Z3."},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            except Exception as e:
                raise LawCompilationError("OpenAI call failed: " + str(e))
            text = (resp.choices[0].message.content or "").strip()

    if not text:
        raise LawCompilationError("Empty KB output from LLM")

    return text
