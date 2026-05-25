import os

from pipeline.utils.openai_sampling import chat_completion_sampling_kwargs
from pipeline.utils.llm_call_tracker import tracked_chat_completion_create
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

    system = load_prompt("nl/nl_paraphrase_system.txt")
    user = render_prompt(
        "nl/nl_paraphrase_user.txt",
        rule_line=(rule_line or "(missing rule)"),
        facts_block=facts_block,
        conclusion_line=(conclusion_line or "(missing conclusion)"),
    )

    try:
        resp = tracked_chat_completion_create(
            client,
            stage="nl_explanation",
            model=chosen_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            metadata={"kind": "liability"},
            **chat_completion_sampling_kwargs(),
        )
    except Exception as e:
        raise NLExplanationError("OpenAI call failed: " + str(e))

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise NLExplanationError("Empty model output")

    return text


def paraphrase_range_explanation(rules_block, facts_block, result_line, model=None):
    """Paraphrase a get_range explanation. Uses ONLY the provided rules, facts, and result.
    The result_line is the EXACT computed value – the LLM must not change it.
    """
    if not _enabled():
        raise NLExplanationError("LLM NL explanations disabled (set PIPELINE_USE_LLM_EXPLANATIONS=1)")

    provider = _provider()
    if provider != "openai":
        raise NLExplanationError("PIPELINE_NL_EXPLAINER_PROVIDER must be 'openai' for now")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise NLExplanationError("Missing OPENAI_API_KEY")

    try:
        from openai import OpenAI
    except Exception as e:
        raise NLExplanationError("OpenAI SDK not installed: " + str(e))

    chosen_model = model or _model()
    client = OpenAI(api_key=api_key)

    system = (
        "You paraphrase formal logic into plain language. You MUST use ONLY the provided "
        "Rule(s), Facts, and Result. Do NOT add, remove, or change any value or fact. "
        "Do NOT invent reasoning. Paraphrase the exact result only."
    )
    user = render_prompt(
        "nl/nl_paraphrase_range.txt",
        rules_block=(rules_block or "(no rules)"),
        facts_block=(facts_block or "(no facts)"),
        result_line=(result_line or "(no result)"),
    )

    try:
        resp = tracked_chat_completion_create(
            client,
            stage="nl_explanation",
            model=chosen_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            metadata={"kind": "range"},
            **chat_completion_sampling_kwargs(),
        )
    except Exception as e:
        raise NLExplanationError("OpenAI call failed: " + str(e))

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise NLExplanationError("Empty model output")
    return text
