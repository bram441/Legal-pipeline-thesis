"""Strategy naming and metadata for JSON_IR experiments."""

from __future__ import annotations

import pytest

from pipeline.kb.compile_strategy import (
    CANONICAL_JSON_IR_STRATEGIES,
    JSON_IR_GENERATION_MODE,
    default_strategies_for_pipeline,
    get_strategy_spec,
    resolve_translate,
    resolve_translation_fields,
    strategy_metadata,
    strategy_to_flags,
)


@pytest.mark.parametrize(
    "name,use_le,translate",
    [
        ("direct_json_ir_translate", False, True),
        ("direct_json_ir_no_translate", False, False),
        ("le_json_ir_translate", True, True),
        ("le_json_ir_no_translate", True, False),
    ],
)
def test_canonical_json_ir_strategy_flags(name: str, use_le: bool, translate: bool) -> None:
    spec = get_strategy_spec(name)
    ul, tp = strategy_to_flags(name)
    assert ul is use_le
    assert tp is False
    assert spec.translate is translate
    assert spec.json_ir_generation == JSON_IR_GENERATION_MODE


def test_resolve_translate_strategy_wins_over_default() -> None:
    assert resolve_translate("direct_json_ir_translate", cli_no_translate=False) is True
    assert resolve_translate("direct_json_ir_no_translate", cli_no_translate=False) is False


def test_cli_no_translate_overrides_translate_strategy() -> None:
    assert resolve_translate("direct_json_ir_translate", cli_no_translate=True) is False


def test_strategy_metadata_distinguishes_four_canonical() -> None:
    metas = {s: strategy_metadata(s) for s in CANONICAL_JSON_IR_STRATEGIES}
    assert len(metas) == 4
    assert {m["uses_le_intermediate"] for m in metas.values()} == {True, False}
    assert {m["configured_translation"] for m in metas.values()} == {True, False}
    for m in metas.values():
        assert m["json_ir_generation"] == JSON_IR_GENERATION_MODE
        assert m["kb_backend"] == "json_ir"
        assert m["repair_enabled"] is True


def test_default_strategies_for_pipeline() -> None:
    assert default_strategies_for_pipeline() == list(CANONICAL_JSON_IR_STRATEGIES)


def test_unknown_strategy_raises() -> None:
    with pytest.raises(ValueError, match="direct_single"):
        get_strategy_spec("direct_single")
