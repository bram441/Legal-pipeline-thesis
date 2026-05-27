"""Versioned pipeline configuration with optional env overrides."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_CONFIG_PATH = _PROJECT_ROOT / "config" / "default.json"
_LOCAL_CONFIG_PATH = _PROJECT_ROOT / "config" / "local.json"
CONFIG_PROFILE_ENV = "PIPELINE_CONFIG_PROFILE"
IGNORE_LOCAL_CONFIG_ENV = "PIPELINE_IGNORE_LOCAL_CONFIG"

# Env var -> (section, key). Secrets stay in env only (OPENAI_API_KEY, models).
_ENV_OVERRIDES: dict[str, tuple[str, str]] = {
    "JSON_IR_SCOPE_MODE": ("json_ir", "scope_mode"),
    "PIPELINE_LAW_SCOPE_MODE": ("json_ir", "scope_mode"),
    "LAW_SCOPE_MODE": ("json_ir", "scope_mode"),
    "JSON_IR_ALLOW_PARTIAL_KB": ("json_ir", "allow_partial_kb"),
    "JSON_IR_CLOSE_WORLD_OBSERVABLES": ("json_ir", "close_world_observables"),
    "JSON_IR_MAX_SYMBOL_VERSIONS": ("json_ir", "max_symbol_versions"),
    "JSON_IR_MAX_RULES_ATTEMPTS_PER_SYMBOL_VERSION": ("json_ir", "max_rules_attempts_per_symbol_version"),
    "JSON_IR_MAX_KB_LLM_CALLS": ("json_ir", "max_kb_llm_calls"),
    "JSON_IR_REPEATED_ERROR_LIMIT": ("json_ir", "repeated_error_limit"),
    "JSON_IR_MAX_RULES_REPAIR": ("json_ir", "max_rules_before_symbol_escalation"),
    "JSON_IR_ALLOW_EVIDENCE_EXTENSION": ("json_ir", "allow_evidence_extension"),
    "JSON_IR_MAX_EVIDENCE_EXTENSION_CALLS": ("json_ir", "max_evidence_extension_calls"),
    "JSON_IR_ALLOW_OUTER_CACHE_RETRIES": ("json_ir", "allow_outer_cache_retries"),
    "PIPELINE_USE_LE": ("le", "use_le"),
    "PIPELINE_EXTRACTION_BACKEND": ("extraction", "backend"),
    "PIPELINE_EXTRACTOR": ("extraction", "provider"),
    "LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS": ("extraction", "enable_domain_heuristics"),
    "LLM_PROVIDER": ("llm", "provider"),
    "LLM_MODEL": ("llm", "model"),
    "LLM_BASE_URL": ("llm", "base_url"),
    "OPENAI_TEMPERATURE": ("openai", "temperature"),
    "OPENAI_TOP_P": ("openai", "top_p"),
    "OPENAI_SEED": ("openai", "seed"),
    "SCORE_TREAT_OPEN_WITH_BELIEF": ("evaluation", "belief_scoring"),
    "SCORE_BOOLEAN_BELIEF_THRESHOLD": ("evaluation", "boolean_belief_threshold"),
    "PIPELINE_OPEN_WORLD_P_YES": ("evaluation", "open_world_p_yes"),
    "EVALUATION_PRAGMATIC_FACTUAL_CRITERIA_MODE": ("evaluation", "pragmatic_factual_criteria_mode"),
    "PIPELINE_TRACE": ("debug", "trace"),
    "PIPELINE_QUIET": ("debug", "quiet"),
    "PIPELINE_LLM_CALL_TRACKING": ("debug", "llm_call_tracking"),
}


def _coerce_value(key: str, raw: str) -> Any:
    s = str(raw).strip()
    if key in {
        "allow_partial_kb",
        "close_world_observables",
        "allow_evidence_extension",
        "allow_outer_cache_retries",
        "use_le",
        "enable_domain_heuristics",
        "belief_scoring",
        "run_pre_query_satisfiability_check",
        "continue_if_satisfiability_unsupported",
        "continue_if_satisfiability_error",
        "enable_intent_diagnostics_on_unknown",
        "pragmatic_factual_criteria_mode",
        "trace",
        "quiet",
        "llm_call_tracking",
        "use_seed",
        "use_response_format",
        "use_reasoning_effort",
    }:
        return s.lower() in ("1", "true", "yes", "on")
    if key in {
        "max_symbol_versions",
        "max_rules_attempts_per_symbol_version",
        "max_kb_llm_calls",
        "repeated_error_limit",
        "max_rules_before_symbol_escalation",
        "max_evidence_extension_calls",
        "max_retries",
        "seed",
        "timeout_seconds",
    }:
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return s
    if key in {"temperature", "top_p", "boolean_belief_threshold", "open_world_p_yes"}:
        try:
            return float(s)
        except ValueError:
            return s
    return s


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for key, val in overlay.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out


def resolve_config_path(path: str | Path) -> Path:
    """Resolve a config profile path (absolute or relative to project root)."""
    p = Path(path)
    if not p.is_absolute():
        p = _PROJECT_ROOT / p
    p = p.resolve()
    if not p.is_file():
        raise FileNotFoundError("Config file not found: " + str(p))
    return p


def _profile_path_from_env() -> Path | None:
    raw = (os.environ.get(CONFIG_PROFILE_ENV) or "").strip()
    if not raw:
        return None
    p = Path(raw)
    if p.is_file():
        return p.resolve()
    try:
        return resolve_config_path(p)
    except FileNotFoundError:
        return None


def ignore_local_config_enabled() -> bool:
    """True when ``PIPELINE_IGNORE_LOCAL_CONFIG`` is set (CLI ``--ignore-local-config``)."""
    v = (os.environ.get(IGNORE_LOCAL_CONFIG_ENV) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def load_config_files(
    profile_path: str | Path | None = None,
    *,
    ignore_local: bool | None = None,
) -> dict[str, Any]:
    """Load default.json + optional local.json + optional profile overlay.

    Merge order before env overrides:
    default → local (unless ``ignore_local``) → profile.

    Profile overlay resolution:
    1. ``profile_path`` argument when provided
    2. else ``PIPELINE_CONFIG_PROFILE`` environment variable when set

    ``ignore_local`` defaults to ``ignore_local_config_enabled()``.
    """
    if not _DEFAULT_CONFIG_PATH.is_file():
        raise FileNotFoundError("Missing config file: " + str(_DEFAULT_CONFIG_PATH))
    with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    skip_local = ignore_local if ignore_local is not None else ignore_local_config_enabled()
    if not skip_local and _LOCAL_CONFIG_PATH.is_file():
        try:
            with open(_LOCAL_CONFIG_PATH, encoding="utf-8") as f:
                local = json.load(f)
            if isinstance(local, dict):
                cfg = _deep_merge(cfg, local)
        except (OSError, json.JSONDecodeError):
            pass
    overlay_path: Path | None = None
    if profile_path is not None:
        overlay_path = resolve_config_path(profile_path)
    else:
        overlay_path = _profile_path_from_env()
    if overlay_path is not None:
        try:
            with open(overlay_path, encoding="utf-8") as f:
                overlay = json.load(f)
            if isinstance(overlay, dict):
                cfg = _deep_merge(cfg, overlay)
        except (OSError, json.JSONDecodeError) as e:
            raise ValueError("Invalid config profile: " + str(overlay_path) + ": " + str(e)) from e
    return cfg


def get_active_config_profile() -> Path | None:
    """Return the active profile path from ``PIPELINE_CONFIG_PROFILE``, if any."""
    return _profile_path_from_env()


def activate_config_profile(path: str | Path | None) -> Path | None:
    """Set or clear the active config profile and reload the cached effective config.

    When ``path`` is None, clears ``PIPELINE_CONFIG_PROFILE``.
    """
    get_effective_config.cache_clear()
    if path is None:
        os.environ.pop(CONFIG_PROFILE_ENV, None)
        get_effective_config.cache_clear()
        return None
    resolved = resolve_config_path(path)
    os.environ[CONFIG_PROFILE_ENV] = str(resolved)
    get_effective_config.cache_clear()
    return resolved


def set_ignore_local_config(enabled: bool) -> None:
    """Enable or disable skipping ``config/local.json`` for this process."""
    get_effective_config.cache_clear()
    if enabled:
        os.environ[IGNORE_LOCAL_CONFIG_ENV] = "1"
    else:
        os.environ.pop(IGNORE_LOCAL_CONFIG_ENV, None)
    get_effective_config.cache_clear()


def configure_runtime(
    config_profile: str | Path | None = None,
    *,
    ignore_local_config: bool = False,
) -> Path | None:
    """Apply evaluation/main CLI config switches and reload the effective config cache."""
    get_effective_config.cache_clear()
    if config_profile is not None:
        resolved = resolve_config_path(config_profile)
        os.environ[CONFIG_PROFILE_ENV] = str(resolved)
    else:
        os.environ.pop(CONFIG_PROFILE_ENV, None)
    if ignore_local_config:
        os.environ[IGNORE_LOCAL_CONFIG_ENV] = "1"
    else:
        os.environ.pop(IGNORE_LOCAL_CONFIG_ENV, None)
    get_effective_config.cache_clear()
    return _profile_path_from_env()


def apply_env_overrides(cfg: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(cfg)
    for env_key, (section, field) in _ENV_OVERRIDES.items():
        raw = os.getenv(env_key)
        if raw is None or str(raw).strip() == "":
            continue
        out.setdefault(section, {})
        out[section][field] = _coerce_value(field, raw)
    return out


@lru_cache(maxsize=1)
def get_effective_config() -> dict[str, Any]:
    return apply_env_overrides(load_config_files())


def reload_config() -> dict[str, Any]:
    get_effective_config.cache_clear()
    return get_effective_config()


def config_section(name: str) -> dict[str, Any]:
    cfg = get_effective_config()
    sec = cfg.get(name)
    return dict(sec) if isinstance(sec, dict) else {}


def save_effective_config(path: str | Path) -> dict[str, Any]:
    """Write merged effective config for reproducibility artifacts."""
    from pipeline.llm.client import llm_config_for_artifact

    cfg = get_effective_config()
    prof = get_active_config_profile()
    artifact: dict[str, Any] = {
        "ignore_local_config": ignore_local_config_enabled(),
        "config_profile": str(prof) if prof else None,
        **cfg,
        "llm_runtime": llm_config_for_artifact(),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(artifact, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return artifact


@dataclass(frozen=True)
class JsonIrConfig:
    scope_mode: str
    allow_partial_kb: bool
    close_world_observables: bool
    max_symbol_versions: int
    max_rules_attempts_per_symbol_version: int
    max_kb_llm_calls: int
    repeated_error_limit: int
    max_rules_before_symbol_escalation: int
    allow_evidence_extension: bool
    max_evidence_extension_calls: int
    allow_outer_cache_retries: bool

    @classmethod
    def from_config(cls) -> JsonIrConfig:
        s = config_section("json_ir")
        return cls(
            scope_mode=str(s.get("scope_mode") or ""),
            allow_partial_kb=bool(s.get("allow_partial_kb")),
            close_world_observables=bool(s.get("close_world_observables", True)),
            max_symbol_versions=int(s.get("max_symbol_versions") or 3),
            max_rules_attempts_per_symbol_version=int(s.get("max_rules_attempts_per_symbol_version") or 3),
            max_kb_llm_calls=int(s.get("max_kb_llm_calls") or 7),
            repeated_error_limit=int(s.get("repeated_error_limit") or 2),
            max_rules_before_symbol_escalation=int(s.get("max_rules_before_symbol_escalation") or 2),
            allow_evidence_extension=bool(s.get("allow_evidence_extension", True)),
            max_evidence_extension_calls=int(s.get("max_evidence_extension_calls") or 1),
            allow_outer_cache_retries=bool(s.get("allow_outer_cache_retries")),
        )


def json_ir_config() -> JsonIrConfig:
    return JsonIrConfig.from_config()
