"""Translate text to English. Used as preprocessing so the pipeline always works with English."""

from pipeline.llm.client import get_llm_client, get_llm_model
from pipeline.llm.request import build_chat_completion_kwargs
from pipeline.utils.llm_call_tracker import tracked_chat_completion_create
from pipeline.utils.prompt_loader import render_prompt


class TranslationError(Exception):
    pass


def translate_to_english(text, model=None):
    """Translate text to English. Returns the text unchanged if translation fails (fallback)."""
    if not text or not str(text).strip():
        return text

    try:
        client = get_llm_client()
    except Exception as e:
        raise TranslationError(str(e)) from e
    chosen_model = model or get_llm_model()

    user_prompt = render_prompt("translation/translate_to_english.txt", text=(text or "").strip())

    try:
        req = build_chat_completion_kwargs(
            model=chosen_model,
            messages=[
                {"role": "system", "content": "You translate legal and case text to English. Output only the translation."},
                {"role": "user", "content": user_prompt},
            ],
        )
        resp = tracked_chat_completion_create(client, stage="translation", **req)
    except Exception as e:
        raise TranslationError("Translation failed: " + str(e))

    out = (resp.choices[0].message.content or "").strip()
    return out if out else text
