"""Parse JSON objects from OpenAI-compatible chat completion responses."""

from __future__ import annotations

import json
from typing import Any


def extract_chat_message_content(resp: Any) -> str:
    """Normalize ``choices[0].message.content`` (string, parts list, or empty)."""
    if resp is None:
        return ""
    choices = getattr(resp, "choices", None) or []
    if not choices:
        return ""
    choice = choices[0]
    msg = getattr(choice, "message", None)
    if msg is None:
        text = getattr(choice, "text", None)
        return (text or "").strip() if text is not None else ""

    content = getattr(msg, "content", None)
    if content is None:
        refusal = getattr(msg, "refusal", None)
        if refusal:
            return str(refusal).strip()
        return ""

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict):
                ptype = part.get("type")
                if ptype in ("text", "output_text") and part.get("text"):
                    chunks.append(str(part["text"]))
            else:
                text = getattr(part, "text", None)
                if text:
                    chunks.append(str(text))
        return "\n".join(chunks).strip()

    return str(content).strip()


def parse_llm_json_object(raw_text: str) -> dict:
    """
    Parse a single JSON object from model text (strips fences, finds ``{...}``).

    Raises ``ValueError`` when content is empty or not parseable.
    """
    from pipeline.kb.json_ir import JSONIRCompilationError, parse_json_ir

    s = (raw_text or "").strip()
    if not s:
        raise ValueError("Empty model response (no message content)")
    try:
        obj = parse_json_ir(s)
    except JSONIRCompilationError as e:
        raise ValueError(str(e)) from e
    if not isinstance(obj, dict):
        raise ValueError("JSON root must be an object")
    return obj


def parse_chat_completion_json(resp: Any) -> dict:
    """Extract message content from a chat response and parse as JSON object."""
    raw = extract_chat_message_content(resp)
    return parse_llm_json_object(raw)
