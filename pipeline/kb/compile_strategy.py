"""
KB compilation strategy: LE vs direct, translation, and (legacy FO only) two-phase staging.

Canonical JSON_IR experiment matrix (four cells):
  direct_json_ir_translate      — law → JSON_IR symbols→rules, English translation on
  direct_json_ir_no_translate   — same path, no translation
  le_json_ir_translate          — law → LE → JSON_IR symbols→rules, translation on
  le_json_ir_no_translate       — law → LE → JSON_IR symbols→rules, no translation

For ``json_ir`` backend, ``PIPELINE_KB_TWO_PHASE`` does not select a different generation
mode: compilation always uses symbols-then-rules. Legacy names ``direct_two_phase`` /
``le_two_phase`` only affect legacy FO compilation and are deprecated for JSON_IR sweeps.

Deprecated aliases (legacy FO naming, kept for backwards compatibility):
  direct_single, direct_two_phase, le_single, le_two_phase
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

LEGACY_STRATEGY_ALIASES: tuple[str, ...] = (
    "direct_single",
    "direct_two_phase",
    "le_single",
    "le_two_phase",
)

# Closest canonical JSON_IR experiment cell for deprecated alias names (reporting only).
LEGACY_ALIAS_CANONICAL_JSON_IR: dict[str, str] = {
    "direct_single": "direct_json_ir_translate",
    "direct_two_phase": "direct_json_ir_translate",
    "le_single": "le_json_ir_translate",
    "le_two_phase": "le_json_ir_translate",
}


@dataclass(frozen=True)
class StrategySpec:
    use_le: bool
    translate: bool
    two_phase: bool  # legacy FO staged vocab→theory only
    json_ir_generation: str | None
    deprecated: bool = False
    deprecation_note: str | None = None


def _json_ir_spec(*, use_le: bool, translate: bool) -> StrategySpec:
    return StrategySpec(
        use_le=use_le,
        translate=translate,
        two_phase=False,
        json_ir_generation=JSON_IR_GENERATION_MODE,
        deprecated=False,
    )


STRATEGIES: dict[str, StrategySpec] = {
    "direct_json_ir_translate": _json_ir_spec(use_le=False, translate=True),
    "direct_json_ir_no_translate": _json_ir_spec(use_le=False, translate=False),
    "le_json_ir_translate": _json_ir_spec(use_le=True, translate=True),
    "le_json_ir_no_translate": _json_ir_spec(use_le=True, translate=False),
    # Deprecated legacy FO labels (translate defaults True, matching historical eval defaults).
    "direct_single": StrategySpec(
        use_le=False,
        translate=True,
        two_phase=False,
        json_ir_generation=JSON_IR_GENERATION_MODE,
        deprecated=True,
        deprecation_note=(
            "Legacy name for direct law→FO single-shot (legacy backend) or direct JSON_IR "
            "(symbols_then_rules). Not a distinct JSON_IR generation mode from direct_two_phase."
        ),
    ),
    "direct_two_phase": StrategySpec(
        use_le=False,
        translate=True,
        two_phase=True,
        json_ir_generation=JSON_IR_GENERATION_MODE,
        deprecated=True,
        deprecation_note=(
            "Legacy FO two-phase (vocab→theory). Ignored for json_ir backend, which always uses "
            "symbols_then_rules."
        ),
    ),
    "le_single": StrategySpec(
        use_le=True,
        translate=True,
        two_phase=False,
        json_ir_generation=JSON_IR_GENERATION_MODE,
        deprecated=True,
        deprecation_note="Legacy name for law→LE→FO single-shot or law→LE→JSON_IR symbols_then_rules.",
    ),
    "le_two_phase": StrategySpec(
        use_le=True,
        translate=True,
        two_phase=True,
        json_ir_generation=JSON_IR_GENERATION_MODE,
        deprecated=True,
        deprecation_note=(
            "Legacy FO law→LE→vocab→theory. Ignored for json_ir backend (always symbols_then_rules)."
        ),
    ),
}

STRATEGY_CHOICES: tuple[str, ...] = CANONICAL_JSON_IR_STRATEGIES + LEGACY_STRATEGY_ALIASES


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
    """Canonical JSON_IR matrix name; equals ``strategy_name`` when already canonical."""
    if strategy_name in CANONICAL_JSON_IR_STRATEGIES:
        return strategy_name
    return LEGACY_ALIAS_CANONICAL_JSON_IR.get(strategy_name, strategy_name)


def strategy_to_flags(name: str) -> tuple[bool, bool]:
    spec = get_strategy_spec(name)
    return spec.use_le, spec.two_phase


def flags_to_strategy(use_le: bool, two_phase: bool) -> str:
    for label, spec in STRATEGIES.items():
        if spec.use_le == use_le and spec.two_phase == two_phase and not spec.deprecated:
            return label
    for label, spec in STRATEGIES.items():
        if spec.use_le == use_le and spec.two_phase == two_phase:
            return label
    return "custom"


def flags_from_process_env() -> tuple[bool, bool]:
    """Current effective flags from environment (same rules as use_le_enabled / two_phase_enabled)."""
    le = (os.getenv("PIPELINE_USE_LE") or "").strip().lower() in ("1", "true", "yes", "on")
    tp = (os.getenv("PIPELINE_KB_TWO_PHASE") or "").strip().lower() in ("1", "true", "yes", "on")
    return le, tp


def resolve_strategy_label(
    cli_strategy: str | None,
    run_json: dict[str, Any] | None,
) -> str | None:
    """
    Resolution order: CLI > run.json kb_compile_strategy > None (keep process env).

    Returns canonical strategy name or None.
    """
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
    """
    Whether to translate law/case/questions to English for this run.

    Priority: ``--no-translate`` on CLI forces False; otherwise the strategy's
    ``translate`` field applies.
    """
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
    """
    Configured vs effective translation and override provenance.

    ``translation_source_prefix`` is e.g. ``"eval_"`` or ``"main_"`` for subprocess attribution.
    """
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
    pipeline_backend_mode: str | None = None,
    kb_backend: str | None = None,
    belief_scoring: bool = False,
    cli_no_translate: bool = False,
    translate_override: bool | None = None,
    translation_source_prefix: str = "",
) -> dict[str, Any]:
    """Honest experiment metadata for score.json, run.json, and evaluation reports."""
    spec = get_strategy_spec(strategy_name)
    canon = canonical_strategy_name(strategy_name)
    trans = resolve_translation_fields(
        strategy_name,
        cli_no_translate=cli_no_translate,
        translate_override=translate_override,
        translation_source_prefix=translation_source_prefix,
    )
    pb = (pipeline_backend_mode or "").strip() or None
    kb = (kb_backend or "").strip() or None
    if pb == "json_ir":
        kb = kb or "json_ir"
    elif pb == "legacy":
        kb = kb or "legacy_fo"
    json_ir_gen = spec.json_ir_generation
    if kb == "json_ir" and not json_ir_gen:
        json_ir_gen = JSON_IR_GENERATION_MODE
    law_scope = (os.getenv("PIPELINE_LAW_SCOPE_MODE") or os.getenv("LAW_SCOPE_MODE") or "").strip() or None
    if not law_scope:
        from pipeline.config import json_ir_config

        law_scope = str(json_ir_config().scope_mode or "") or None
    outer_rep = (os.getenv("PIPELINE_KB_MAX_REPAIR_ATTEMPTS") or "").strip()
    inner_rep = (os.getenv("JSON_IR_MAX_COMPILE_ATTEMPTS") or "").strip()
    repair_enabled = False
    json_ir_structured: dict[str, Any] = {}
    if kb == "json_ir":
        from pipeline.kb.cache import json_ir_outer_cache_retries_enabled, resolve_max_repair_attempts
        from pipeline.kb.json_ir_compile_loop import compile_loop_limits_from_env

        limits = compile_loop_limits_from_env()
        repair_enabled = True
        json_ir_structured = {
            "json_ir_structured_repair_enabled": True,
            "json_ir_max_symbol_versions": limits.max_symbol_versions,
            "json_ir_max_rules_attempts_per_symbol_version": limits.max_rules_attempts_per_symbol_version,
            "json_ir_max_kb_llm_calls": limits.max_total_kb_llm_calls,
            "json_ir_outer_cache_retries_enabled": json_ir_outer_cache_retries_enabled(),
            "json_ir_outer_cache_max_attempts": resolve_max_repair_attempts("json_ir", log_warnings=False),
        }
    else:
        try:
            repair_enabled = int(outer_rep or "0") > 0 or int(inner_rep or "0") > 0
        except ValueError:
            repair_enabled = bool(outer_rep or inner_rep)

    meta: dict[str, Any] = {
        "strategy_name": strategy_name,
        "canonical_strategy_name": canon,
        "kb_backend": kb,
        "uses_le_intermediate": spec.use_le,
        "json_ir_generation": json_ir_gen,
        "legacy_two_phase_env": spec.two_phase,
        "belief_scoring": bool(belief_scoring),
        "strategy_deprecated": spec.deprecated,
        "law_scope_mode": law_scope,
        "repair_enabled": repair_enabled,
        **trans,
        **json_ir_structured,
    }
    if strategy_name != canon:
        meta["strategy_is_deprecated_alias"] = True
    if pb:
        meta["pipeline_backend_mode"] = pb
    if spec.deprecated and spec.deprecation_note:
        meta["deprecation_note"] = spec.deprecation_note
    if kb == "json_ir" and spec.two_phase:
        meta["json_ir_two_phase_ignored"] = True
    return meta


def default_strategies_for_pipeline(pipeline_backend: str | None) -> list[str]:
    """Strategy list used when eval CLI passes ``--strategies all``."""
    if (pipeline_backend or "json_ir").strip().lower() == "legacy":
        return list(LEGACY_STRATEGY_ALIASES)
    return list(CANONICAL_JSON_IR_STRATEGIES)


def kb_run_context(cli_strategy: str | None, run_json: dict[str, Any] | None, mode: str):
    """
    Build a context manager for KB env overrides and the resolved strategy label.

    Priority: CLI ``cli_strategy`` > ``run_json["kb_compile_strategy"]`` > process env.

    Returns:
      (context_manager, resolved_label) — label may be a deprecated alias if explicitly requested.
    """
    from contextlib import nullcontext

    resolved = resolve_strategy_label(cli_strategy, run_json if mode == "json" else None)
    if resolved is not None:
        spec = get_strategy_spec(resolved)
        return kb_compile_env_overrides(spec.use_le, spec.two_phase), resolved
    use_le, two_phase = flags_from_process_env()
    return nullcontext(), flags_to_strategy(use_le, two_phase)


@contextmanager
def kb_compile_env_overrides(use_le: bool, two_phase: bool):
    """Temporarily set PIPELINE_USE_LE and PIPELINE_KB_TWO_PHASE; restore after."""
    keys = ("PIPELINE_USE_LE", "PIPELINE_KB_TWO_PHASE")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        os.environ["PIPELINE_USE_LE"] = "1" if use_le else "0"
        os.environ["PIPELINE_KB_TWO_PHASE"] = "1" if two_phase else "0"
        yield
    finally:
        for k in keys:
            v = saved[k]
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
