# pipeline/law/law_compiler.py

import os


class LawCompilationError(Exception):
    pass


def _law_to_fo_prompt(law_text):
    return (
        "Convert the following LEGAL RULE TEXT into a reusable FO(.) knowledge base for IDP-Z3.\n"
        "Output ONLY FO(.) code, and NOTHING else.\n\n"
        "You MUST output exactly two blocks:\n"
        "1) vocabulary V { ... }\n"
        "2) theory T:V { ... }\n\n"
        "Hard constraints:\n"
        "- Do NOT output any 'structure' block.\n"
        "- Use FO(.) quantifier syntax EXACTLY like this example:\n"
        "    ! p in Party: liable(p) <=> negligent(p) & causedDamage(p).\n"
        "  (Do NOT use !p[Party]:  and do NOT use forall(...).)\n"
        "- Use these symbols and names:\n"
        "    type Party\n"
        "    negligent: Party -> Bool\n"
        "    causedDamage: Party -> Bool\n"
        "    liable: Party -> Bool\n\n"
        "LEGAL RULE TEXT:\n"
        + law_text.strip()
    )


def compile_law_to_kb_fo(law_text, model=None):
    """
    Uses an LLM to compile a natural-language law description into FO(.) KB code.
    Returns a FO(.) string containing vocabulary+theory only (no structure).

    Params:
      law_text (str): Natural-language law text.
      model (str|None): Optional OpenAI model (defaults to env OPENAI_MODEL).

    Returns:
      str: FO(.) code (vocabulary + theory).
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

    messages = [
        {"role": "system", "content": "You compile legal rules into FO(.) code for IDP-Z3."},
        {"role": "user", "content": _law_to_fo_prompt(law_text)},
    ]

    try:
        resp = client.chat.completions.create(
            model=chosen_model,
            messages=messages,
        )
    except Exception as e:
        raise LawCompilationError("OpenAI call failed: " + str(e))

    text = resp.choices[0].message.content or ""
    text = text.strip()

    if not text:
        raise LawCompilationError("Empty KB output from LLM")

    return text
