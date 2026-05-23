"""
Optional Logical English (LE) layer: natural language -> LE -> FO(.).
Enable with environment variable: PIPELINE_USE_LE=1 or true or yes.
When enabled, KB compilation goes: law text -> LE -> FO(.) instead of law text -> FO(.).
"""

import os

from pipeline.utils.openai_sampling import chat_completion_sampling_kwargs
from pipeline.utils.prompt_loader import render_prompt


def use_le_enabled():
    """True if the pipeline should use the Logical English intermediate layer."""
    v = (os.getenv("PIPELINE_USE_LE") or "").strip().lower()
    return v in ("1", "true", "yes")


def law_text_to_le(law_text, client, model):
    """
    Convert law text to Logical English (controlled natural language).
    Returns a single string of LE rules/clauses.
    """
    from pipeline.utils.prompt_paths import LE_LAW_TO_LE, LE_TO_FO

    user_prompt = render_prompt(LE_LAW_TO_LE, law_text=(law_text or "").strip())
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You convert legal text into Logical English: clear, structured rules with explicit if-then, every/some, and types. Output only the Logical English text, no FO(.) code."},
            {"role": "user", "content": user_prompt},
        ],
        **chat_completion_sampling_kwargs(),
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("Empty Logical English output from LLM")
    return text


def le_to_fo(le_text, client, model):
    """
    Convert Logical English text to FO(.) (vocabulary + theory) for IDP-Z3.
    Returns a single string of FO(.) code.
    """
    user_prompt = render_prompt(LE_TO_FO, le_text=(le_text or "").strip())
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You convert Logical English rules into valid FO(.) code for IDP-Z3. Output ONLY the FO(.) code (vocabulary V { } and theory T:V { }), no explanations."},
            {"role": "user", "content": user_prompt},
        ],
        **chat_completion_sampling_kwargs(),
    )
    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("Empty FO(.) output from LE->FO step")
    return text
