"""
Two-phase KB compilation (VERUS-LM style): vocabulary first, then theory only.

- ``PIPELINE_KB_TWO_PHASE=1`` with ``PIPELINE_USE_LE=0``: source = natural-law text
  (``kb/kb_vocab_only.txt``, ``kb/kb_theory_only.txt``).

- ``PIPELINE_KB_TWO_PHASE=1`` with ``PIPELINE_USE_LE=1``: law → LE first, then source =
  Logical English (``le/le_vocab_only.txt``, ``le/le_theory_only.txt``).

Repair loops use full KB + symbolic vs semantic repair prompts (see compiler.py).
"""

from __future__ import annotations

import os
import re

from pipeline.utils.openai_sampling import chat_completion_sampling_kwargs
from pipeline.utils.prompt_loader import render_prompt
from pipeline.kb.exceptions import LawCompilationError


def two_phase_enabled() -> bool:
    v = (os.getenv("PIPELINE_KB_TWO_PHASE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _find_matching_brace(text: str, open_brace_index: int) -> int:
    if open_brace_index < 0 or open_brace_index >= len(text) or text[open_brace_index] != "{":
        return -1
    depth = 0
    for i in range(open_brace_index, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _extract_vocab_block(raw: str) -> str | None:
    m = re.search(r"\bvocabulary\s+V\s*\{", raw, re.IGNORECASE)
    if not m:
        return None
    open_i = raw.find("{", m.start())
    if open_i < 0:
        return None
    close_i = _find_matching_brace(raw, open_i)
    if close_i < 0:
        return None
    return raw[m.start() : close_i + 1].strip()


def _extract_theory_block(raw: str) -> str | None:
    m = re.search(r"\btheory\s+T\s*:\s*V\s*\{", raw, re.IGNORECASE)
    if not m:
        return None
    open_i = raw.find("{", m.start())
    if open_i < 0:
        return None
    close_i = _find_matching_brace(raw, open_i)
    if close_i < 0:
        return None
    return raw[m.start() : close_i + 1].strip()


def _idp_parse(fo: str) -> None:
    from idp_engine import IDP

    IDP.from_str(fo)


def _vocab_stub_theory(vocab_block: str) -> str:
    """Minimal satisfiable theory so IDP accepts vocabulary-only check."""
    return vocab_block.strip() + "\n\ntheory T:V {\n  true.\n}\n"


def compile_two_phase(
    source_text: str,
    client,
    chosen_model: str,
    *,
    vocab_prompt: str = "kb/legacy/kb_vocab_only.txt",
    theory_prompt: str = "kb/legacy/kb_theory_only.txt",
    system_message: str = "You compile legal rules into FO(.) code for IDP-Z3.",
    single_shot_fn=None,
) -> str:
    """
    Phase 1: vocabulary only. Phase 2: theory only. ``source_text`` is either raw law
    or Logical English, depending on ``vocab_prompt`` / ``theory_prompt``.

    On repeated failure, call ``single_shot_fn()`` if provided (single-shot FO from same pipeline).
    """
    src = (source_text or "").strip()
    feedback_vocab = ""
    vocab_block = None

    for _ in range(2):
        user = render_prompt(
            vocab_prompt,
            source_text=src,
            feedback_block=feedback_vocab or "(none — first attempt.)",
        )
        try:
            resp = client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user},
                ],
                **chat_completion_sampling_kwargs(),
            )
        except Exception as e:
            raise LawCompilationError("OpenAI call failed (vocabulary phase): " + str(e)) from e
        raw = (resp.choices[0].message.content or "").strip()
        vb = _extract_vocab_block(raw)
        if vb:
            try:
                _idp_parse(_vocab_stub_theory(vb))
                vocab_block = vb
                break
            except Exception as e:
                feedback_vocab = (
                    "The vocabulary must parse in IDP-Z3. Error: "
                    + str(e)
                    + "\n\nYour previous output was:\n"
                    + raw[:6000]
                )
        else:
            feedback_vocab = (
                "Output must contain exactly one block starting with vocabulary V { ... }. "
                "No theory block in this step.\n\nYour previous output was:\n" + raw[:6000]
            )

    if not vocab_block:
        if single_shot_fn:
            return single_shot_fn()
        raise LawCompilationError("Vocabulary phase failed after retries; no valid vocabulary block.")

    feedback_theory = ""
    merged = None

    for _ in range(2):
        user = render_prompt(
            theory_prompt,
            source_text=src,
            vocabulary_block=vocab_block,
            feedback_block=feedback_theory or "(none — first attempt.)",
        )
        try:
            resp = client.chat.completions.create(
                model=chosen_model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user},
                ],
                **chat_completion_sampling_kwargs(),
            )
        except Exception as e:
            raise LawCompilationError("OpenAI call failed (theory phase): " + str(e)) from e
        raw = (resp.choices[0].message.content or "").strip()
        tb = _extract_theory_block(raw)
        if tb:
            candidate = vocab_block.strip() + "\n\n" + tb.strip()
            try:
                _idp_parse(candidate)
                merged = candidate
                break
            except Exception as e:
                feedback_theory = (
                    "The merged vocabulary+theory must parse in IDP-Z3. Error: "
                    + str(e)
                    + "\n\nYour previous theory output was:\n"
                    + raw[:6000]
                )
        else:
            feedback_theory = (
                "Output must contain exactly one block starting with theory T:V { ... }.\n\n"
                "Your previous output was:\n" + raw[:6000]
            )

    if not merged:
        if single_shot_fn:
            return single_shot_fn()
        raise LawCompilationError("Theory phase failed after retries; could not produce parseable FO.")

    return merged
