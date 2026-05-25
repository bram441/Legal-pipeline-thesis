"""
KB compilation strategy for JSON-IR experiments.

Four cells: direct/le × translate/no_translate. Compilation always uses symbols-then-rules.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

JSON_IR_GENERATION_MODE = "symbols_then_rules"

CANONICAL_JSON_IR_STRATEGIES: tuple[str, ...] = (
    "direct_json_ir_translate",
    "direct_json_ir_no_translate",
    "le_json_ir_translate",
    "le_json_ir_no_translate",
)

STRATEGY_CHOICES: tuple[str, ...] = CANONICAL_JSON_IR_STRATEGIES


@dataclass(frozen=True)
class StrategySpec:
    use_le: bool
    translate: bool
    json_ir_generation: str


def _json_ir_spec(*, use_le: bool, translate: bool) -> StrategySpec:
    return StrategySpec(
        use_le=use_le,
        translate=translate,
        json_ir_generation=JSON_IR_GENERATION_MODE,
    )


STRATEGIES: dict[str, StrategySpec] = {
    "direct_json_ir_translate": _json_ir_spec(use_le=False, translate=True),
    "direct_json_ir_no_translate": _json_ir_spec(use_le=False, translate=False),
    "le_json_ir_translate": _json_ir_spec(use_le=True, translate=True),
    "le_json_ir_no_translate": _json_ir_spec(use_le=True, translate=False),
}


def get_strategy_spec(name: str) -> StrategySpec:
    if name not in STRATEGIES:
        raise ValueError(
            "Unknown kb_compile_strategy: "
            + repr(name)
            + ". Expected one of: "
            + ", ".join(STRATEGY_CHOICES)
        )
    return STRATEGIES[name]


def canonical_strategy_name(strategy_name: str) -> str:
    return strategy_name if strategy_name in CANONICAL_JSON_IR_STRATEGIES else strategy_name


def strategy_to_flags(name: str) -> tuple[bool, bool]:
    spec = get_strategy_spec(name)
    return spec.use_le, False


def flags_to_strategy(use_le: bool, two_phase: bool = False) -> str:
    del two_phase
    for label, spec in STRATEGIES.items():
        if spec.use_le == use_le:
            return label
    return "custom"


def flags_from_process_env() -> tuple[bool, bool]:
    le = (os.getenv("PIPELINE_USE_LE") or "").strip().lower() in ("1", "true", "yes", "on")
    return le, False


def resolve_strategy_label(
    cli_strategy: str | None,
    run_json: dict[str, Any] | None,
) -> str | None:
    if cli_strategy:
        get_strategy_spec(cli_strategy)
        return cli_strategy
    if run_json:
        s = run_json.get("kb_compile_strategy")
        if isinstance(s, str) and s.strip():
            get_strategy_spec(s.strip())
            return s.strip()
    return None


def resolve_translate(strategy_name: str, *, cli_no_translate: bool = False) -> bool:
    return resolve_translation_fields(
        strategy_name,
        cli_no_translate=cli_no_translate,
    )["effective_translation"]


def resolve_translation_fields(
    strategy_name: str,
    *,
    cli_no_translate: bool = False,
    translate_override: bool | None = None,
    translation_source_prefix: str = "",
) -> dict[str, Any]:
    spec = get_strategy_spec(strategy_name)
    configured = spec.translate
    prefix = (translation_source_prefix or "").strip()
    if translate_override is not None:
        effective = translate_override
        source = (prefix + "override") if prefix else "override"
    elif cli_no_translate:
        effective = False
        source = (prefix + "cli_no_translate") if prefix else "cli_no_translate"
    else:
        effective = configured
        source = "strategy"

    warning: str | None = None
    if configured and not effective:
        warning = (
            "--no-translate overrides strategy %r (configured_translation=True, "
            "effective_translation=False)" % strategy_name
        )

    out: dict[str, Any] = {
        "configured_translation": configured,
        "effective_translation": effective,
        "translation_source": source,
        "uses_translation": effective,
    }
    if warning:
        out["translation_override_warning"] = warning
    return out


def strategy_metadata(
    strategy_name: str,
    *,
    belief_scoring: bool = False,
    cli_no_translate: bool = False,
    translate_override: bool | None = None,
    translation_source_prefix: str = "",
) -> dict[str, Any]:
    spec = get_strategy_spec(strategy_name)
    trans = resolve_translation_fields(
        strategy_name,
        cli_no_translate=cli_no_translate,
        translate_override=translate_override,
        translation_source_prefix=translation_source_prefix,
    )
    from pipeline.config import json_ir_config
    from pipeline.kb.cache import json_ir_outer_cache_retries_enabled, resolve_max_repair_attempts
    from pipeline.kb.json_ir_compile_loop import compile_loop_limits_from_env

    law_scope = (os.getenv("PIPELINE_LAW_SCOPE_MODE") or os.getenv("LAW_SCOPE_MODE") or "").strip() or None
    if not law_scope:
        law_scope = str(json_ir_config().scope_mode or "") or None
    limits = compile_loop_limits_from_env()
    meta: dict[str, Any] = {
        "strategy_name": strategy_name,
        "canonical_strategy_name": strategy_name,
        "kb_backend": "json_ir",
        "pipeline_backend_mode": "json_ir",
        "uses_le_intermediate": spec.use_le,
        "json_ir_generation": spec.json_ir_generation,
        "belief_scoring": bool(belief_scoring),
        "law_scope_mode": law_scope,
        "repair_enabled": True,
        "json_ir_structured_repair_enabled": True,
        "json_ir_max_symbol_versions": limits.max_symbol_versions,
        "json_ir_max_rules_attempts_per_symbol_version": limits.max_rules_attempts_per_symbol_version,
        "json_ir_max_kb_llm_calls": limits.max_total_kb_llm_calls,
        "json_ir_outer_cache_retries_enabled": json_ir_outer_cache_retries_enabled(),
        "json_ir_outer_cache_max_attempts": resolve_max_repair_attempts(log_warnings=False),
        **trans,
    }
    return meta


def default_strategies_for_pipeline(pipeline_backend: str | None = None) -> list[str]:
    del pipeline_backend
    return list(CANONICAL_JSON_IR_STRATEGIES)


def kb_run_context(cli_strategy: str | None, run_json: dict[str, Any] | None, mode: str):
    from contextlib import nullcontext

    resolved = resolve_strategy_label(cli_strategy, run_json if mode == "json" else None)
    if resolved is not None:
        spec = get_strategy_spec(resolved)
        return kb_compile_env_overrides(spec.use_le), resolved
    use_le, _ = flags_from_process_env()
    return nullcontext(), flags_to_strategy(use_le)


@contextmanager
def kb_compile_env_overrides(use_le: bool, two_phase: bool = False):
    del two_phase
    key = "PIPELINE_USE_LE"
    saved = os.environ.get(key)
    try:
        os.environ["PIPELINE_USE_LE"] = "1" if use_le else "0"
        yield
    finally:
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved
