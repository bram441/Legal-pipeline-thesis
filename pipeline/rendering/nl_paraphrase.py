import os

from pipeline.utils.prompt_loader import load_prompt, render_prompt


class NLExplanationError(Exception):
    pass


def _enabled():
    return (os.getenv("PIPELINE_USE_LLM_EXPLANATIONS") or "").strip().lower() in ["1", "true", "yes", "on"]


def _provider():
    return (os.getenv("PIPELINE_NL_EXPLAINER_PROVIDER") or "openai").strip().lower()


def _model():
    return (os.getenv("OPENAI_EXPLAINER_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()


def paraphrase_liability_explanation(rule_line, fact_lines, conclusion_line, model=None):
    """Paraphrase a grounded symbolic explanation into natural language.

    This function does not decide anything. It is only a *renderer*.
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

    facts_block = "\n".join(["- " + f for f in (fact_lines or [])]) or "(no facts provided)"

    system = load_prompt("nl_paraphrase_system.txt")
    user = render_prompt(
        "nl_paraphrase_user.txt",
        rule_line=(rule_line or "(missing rule)"),
        facts_block=facts_block,
        conclusion_line=(conclusion_line or "(missing conclusion)"),
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
