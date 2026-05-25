"""Strategy naming and metadata for JSON_IR experiments."""

from __future__ import annotations

import pytest

from pipeline.kb.compile_strategy import (
    CANONICAL_JSON_IR_STRATEGIES,
    JSON_IR_GENERATION_MODE,
    LEGACY_STRATEGY_ALIASES,
    canonical_strategy_name,
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
    assert spec.deprecated is False


def test_legacy_aliases_deprecated_and_json_ir_generation() -> None:
    for alias in ("direct_single", "direct_two_phase", "le_single", "le_two_phase"):
        spec = get_strategy_spec(alias)
        assert spec.deprecated is True
        assert spec.json_ir_generation == JSON_IR_GENERATION_MODE


def test_direct_two_phase_sets_legacy_two_phase_only() -> None:
    _, tp = strategy_to_flags("direct_two_phase")
    assert tp is True
    meta = strategy_metadata("direct_two_phase", pipeline_backend_mode="json_ir", kb_backend="json_ir")
    assert meta["json_ir_two_phase_ignored"] is True


def test_resolve_translate_strategy_wins_over_default() -> None:
    assert resolve_translate("direct_json_ir_translate", cli_no_translate=False) is True
    assert resolve_translate("direct_json_ir_no_translate", cli_no_translate=False) is False


def test_cli_no_translate_overrides_translate_strategy() -> None:
    assert resolve_translate("direct_json_ir_translate", cli_no_translate=True) is False


def test_strategy_metadata_distinguishes_four_canonical() -> None:
    metas = {
        s: strategy_metadata(s, pipeline_backend_mode="json_ir", kb_backend="json_ir")
        for s in CANONICAL_JSON_IR_STRATEGIES
    }
    assert len(metas) == 4
    assert {m["uses_le_intermediate"] for m in metas.values()} == {True, False}
    assert {m["configured_translation"] for m in metas.values()} == {True, False}
    assert {m["effective_translation"] for m in metas.values()} == {True, False}
    for m in metas.values():
        assert m["json_ir_generation"] == JSON_IR_GENERATION_MODE
        assert m["strategy_deprecated"] is False
        assert m["canonical_strategy_name"] == m["strategy_name"]
        assert m["translation_source"] == "strategy"
        assert m["repair_enabled"] is True
        assert m["json_ir_structured_repair_enabled"] is True
        _assert_required_metadata_keys(m)


def test_default_strategies_for_json_ir_pipeline() -> None:
    default = default_strategies_for_pipeline("json_ir")
    assert default == list(CANONICAL_JSON_IR_STRATEGIES)
    assert not any(s in LEGACY_STRATEGY_ALIASES for s in default)


def test_legacy_alias_canonical_name_and_deprecated_flag() -> None:
    meta = strategy_metadata("direct_single", pipeline_backend_mode="json_ir", kb_backend="json_ir")
    assert meta["strategy_name"] == "direct_single"
    assert meta["canonical_strategy_name"] == "direct_json_ir_translate"
    assert meta["strategy_is_deprecated_alias"] is True
    assert meta["strategy_deprecated"] is True
    _assert_required_metadata_keys(meta)


def test_cli_no_translate_override_warning_and_fields() -> None:
    fields = resolve_translation_fields(
        "direct_json_ir_translate",
        cli_no_translate=True,
        translation_source_prefix="eval_",
    )
    assert fields["configured_translation"] is True
    assert fields["effective_translation"] is False
    assert fields["translation_source"] == "eval_cli_no_translate"
    assert fields["translation_override_warning"]

    meta = strategy_metadata(
        "le_json_ir_translate",
        pipeline_backend_mode="json_ir",
        kb_backend="json_ir",
        cli_no_translate=True,
        translation_source_prefix="main_",
    )
    assert meta["configured_translation"] is True
    assert meta["effective_translation"] is False
    assert meta["translation_source"] == "main_cli_no_translate"
    assert meta["translation_override_warning"]


def _assert_required_metadata_keys(meta: dict) -> None:
    for key in (
        "strategy_name",
        "canonical_strategy_name",
        "configured_translation",
        "effective_translation",
        "translation_source",
        "uses_translation",
        "uses_le_intermediate",
        "kb_backend",
        "json_ir_generation",
    ):
        assert key in meta
