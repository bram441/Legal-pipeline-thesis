# pipeline/rendering/llm_nl_explainer.py
#
# Minimal, *grounded* NL paraphrasing layer for explanations.
# It does NOT decide anything. It only paraphrases what the symbolic core already produced.
#
# Design goals:
# - Keep symbolic core stable (no solver changes)
# - Keep debuggability high (we always include the exact FO(.) rule snippet + exact facts in the final explanation)
# - Be incremental: only supports liability explanations for now
#
# Usage:
#   from pipeline.rendering.llm_nl_explainer import paraphrase_liability_explanation
#   txt = paraphrase_liability_explanation(rule_line, fact_lines, conclusion_line)

import os


class NLExplanationError(Exception):
    pass


def _enabled():
    return (os.getenv("PIPELINE_USE_LLM_EXPLANATIONS") or "").strip().lower() in ["1", "true", "yes", "on"]


def _provider():
    return (os.getenv("PIPELINE_NL_EXPLAINER_PROVIDER") or "openai").strip().lower()


def _model():
    # Separate model knob, so extraction + KB compilation can stay unchanged.
    return (os.getenv("OPENAI_EXPLAINER_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()


def paraphrase_liability_explanation(rule_line, fact_lines, conclusion_line, model=None):
    """
    Returns an LLM paraphrase for a liability explanation.

    IMPORTANT: This function returns ONLY the paraphrase text.
    The caller is responsible for showing the exact rule_line / fact_lines / conclusion_line
    alongside the paraphrase (for grounding & debug).

    Params:
      rule_line (str): Single FO(.) rule snippet (exact text).
      fact_lines (list[str]): Case facts the explanation may use (exact text).
      conclusion_line (str): The derived conclusion (exact text).
      model (str|None): Optional model override.

    Returns:
      str: Paraphrase text (natural language), grounded to the provided inputs.

    Raises:
      NLExplanationError: If disabled, missing keys, SDK unavailable, or API failure.
    """
    if not _enabled():
        raise NLExplanationError("LLM NL explanations disabled (set PIPELINE_USE_LLM_EXPLANATIONS=1)")

    provider = _provider()
    if provider != "openai":
        raise NLExplanationError("PIPELINE_NL_EXPLAINER_PROVIDER must be 'openai' for now (got: " + provider + ")")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise NLExplanationError("Missing OPENAI_API_KEY environment variable")

    try:
        from openai import OpenAI
    except Exception as e:
        raise NLExplanationError("OpenAI SDK not installed/importable: " + str(e))

    chosen_model = model or _model()
    client = OpenAI(api_key=api_key)

    # We strictly constrain: the assistant may ONLY use the provided rule/facts/conclusion.
    # We ask for a short explanation (1-3 sentences), no extra legal theory.
    system = (
        "You rewrite formal logic into plain English. "
        "You MUST stay grounded: use ONLY the provided Rule, Facts, and Conclusion. "
        "Do NOT add new facts, do NOT add new rules, do NOT generalize beyond the inputs. "
        "If something is not explicitly in the inputs, do not mention it. "
        "Keep it short (1 to 3 sentences)."
    )

    # Provide the grounding inputs in a consistent format.
    facts_block = "\n".join(["- " + f for f in (fact_lines or [])]) or "(no facts provided)"
    user = (
        "Rule (exact):\n"
        + (rule_line or "(missing rule)") + "\n\n"
        + "Facts (exact):\n"
        + facts_block + "\n\n"
        + "Conclusion (exact):\n"
        + (conclusion_line or "(missing conclusion)") + "\n\n"
        + "Task: Paraphrase the conclusion in plain English, explicitly linking it to the rule and facts."
    )

    try:
        resp = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
    except Exception as e:
        raise NLExplanationError("OpenAI call failed: " + str(e))

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise NLExplanationError("Empty model output")

    return text
