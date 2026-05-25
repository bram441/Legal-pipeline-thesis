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


def load_config_files() -> dict[str, Any]:
    """Load default.json + optional config/local.json (gitignored)."""
    if not _DEFAULT_CONFIG_PATH.is_file():
        raise FileNotFoundError("Missing config file: " + str(_DEFAULT_CONFIG_PATH))
    with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    if _LOCAL_CONFIG_PATH.is_file():
        try:
            with open(_LOCAL_CONFIG_PATH, encoding="utf-8") as f:
                local = json.load(f)
            if isinstance(local, dict):
                cfg = _deep_merge(cfg, local)
        except (OSError, json.JSONDecodeError):
            pass
    return cfg


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
    cfg = get_effective_config()
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return cfg


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
