"""Tests for parsing JSON from chat completion responses."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline.extraction.openai_extractor import LLMExtractionError, extract_case_ir_only_openai
from pipeline.utils.llm_response_json import (
    extract_chat_message_content,
    parse_chat_completion_json,
    parse_llm_json_object,
)


def test_parse_llm_json_object_strips_fences():
    raw = '```json\n{"entities": {}, "assertions": [], "value_assertions": []}\n```'
    obj = parse_llm_json_object(raw)
    assert "entities" in obj


def test_parse_empty_raises():
    with pytest.raises(ValueError, match="Empty"):
        parse_llm_json_object("")


def test_extract_chat_message_content_list_parts():
    resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=[{"type": "text", "text": '{"entities": {}, "assertions": [], "value_assertions": []}'}]
                )
            )
        ]
    )
    text = extract_chat_message_content(resp)
    obj = parse_chat_completion_json(resp)
    assert obj["entities"] == {}


def test_extract_case_ir_raises_llm_extraction_error_not_json_decode(monkeypatch):
    class FakeMsg:
        content = ""

    class FakeChoice:
        message = FakeMsg()

    class FakeResp:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            return FakeResp()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(
        "pipeline.extraction.openai_extractor.get_llm_client",
        lambda: FakeClient(),
    )
    monkeypatch.setattr(
        "pipeline.extraction.openai_extractor.get_llm_model",
        lambda: "test/model",
    )
    monkeypatch.setattr(
        "pipeline.extraction.openai_extractor.tracked_chat_completion_create",
        lambda client, **kwargs: FakeResp(),
    )

    with pytest.raises(LLMExtractionError, match="Empty"):
        extract_case_ir_only_openai("case text", "test/model", kb_schema={})
