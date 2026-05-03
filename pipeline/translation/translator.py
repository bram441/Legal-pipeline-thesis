"""Translate text to English. Used as preprocessing so the pipeline always works with English."""

import os

from pipeline.utils.openai_sampling import chat_completion_sampling_kwargs
from pipeline.utils.prompt_loader import render_prompt


class TranslationError(Exception):
    pass


def translate_to_english(text, model=None):
    """Translate text to English. Returns the text unchanged if translation fails (fallback)."""
    if not text or not str(text).strip():
        return text

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise TranslationError("Missing OPENAI_API_KEY environment variable")

    try:
        from openai import OpenAI
    except Exception as e:
        raise TranslationError("OpenAI SDK not installed/importable: " + str(e))

    client = OpenAI(api_key=api_key)
    chosen_model = model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"

    user_prompt = render_prompt("translation/translate_to_english.txt", text=(text or "").strip())

    try:
        resp = client.chat.completions.create(
            model=chosen_model,
            messages=[
                {"role": "system", "content": "You translate legal and case text to English. Output only the translation."},
                {"role": "user", "content": user_prompt},
            ],
            **chat_completion_sampling_kwargs(),
        )
    except Exception as e:
        raise TranslationError("Translation failed: " + str(e))

    out = (resp.choices[0].message.content or "").strip()
    return out if out else text
