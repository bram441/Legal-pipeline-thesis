#!/usr/bin/env python
"""Run a small budget/profile ablation without modifying config/local.json.

This script reads one or more JSON config overlays, maps supported keys to the
existing environment variable overrides used by pipeline/config.py, and invokes
scripts/run_evaluation.py once per profile.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ENV_MAP = {
    ("json_ir", "scope_mode"): "JSON_IR_SCOPE_MODE",
    ("json_ir", "allow_partial_kb"): "JSON_IR_ALLOW_PARTIAL_KB",
    ("json_ir", "close_world_observables"): "JSON_IR_CLOSE_WORLD_OBSERVABLES",
    ("json_ir", "max_symbol_versions"): "JSON_IR_MAX_SYMBOL_VERSIONS",
    ("json_ir", "max_rules_attempts_per_symbol_version"): "JSON_IR_MAX_RULES_ATTEMPTS_PER_SYMBOL_VERSION",
    ("json_ir", "max_kb_llm_calls"): "JSON_IR_MAX_KB_LLM_CALLS",
    ("json_ir", "repeated_error_limit"): "JSON_IR_REPEATED_ERROR_LIMIT",
    ("json_ir", "max_rules_before_symbol_escalation"): "JSON_IR_MAX_RULES_REPAIR",
    ("json_ir", "allow_evidence_extension"): "JSON_IR_ALLOW_EVIDENCE_EXTENSION",
    ("json_ir", "max_evidence_extension_calls"): "JSON_IR_MAX_EVIDENCE_EXTENSION_CALLS",
    ("json_ir", "allow_outer_cache_retries"): "JSON_IR_ALLOW_OUTER_CACHE_RETRIES",
    ("extraction", "backend"): "PIPELINE_EXTRACTION_BACKEND",
    ("extraction", "provider"): "PIPELINE_EXTRACTOR",
    ("extraction", "enable_domain_heuristics"): "LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS",
    ("openai", "temperature"): "OPENAI_TEMPERATURE",
    ("openai", "top_p"): "OPENAI_TOP_P",
    ("openai", "seed"): "OPENAI_SEED",
    ("evaluation", "belief_scoring"): "SCORE_TREAT_OPEN_WITH_BELIEF",
    ("evaluation", "boolean_belief_threshold"): "SCORE_BOOLEAN_BELIEF_THRESHOLD",
    ("evaluation", "open_world_p_yes"): "PIPELINE_OPEN_WORLD_P_YES",
    ("debug", "trace"): "PIPELINE_TRACE",
    ("debug", "quiet"): "PIPELINE_QUIET",
}

# Optional compatibility variables for configurations that support extraction retry overrides.
EXTRA_ENV_MAP = {
    ("evaluation", "pragmatic_factual_criteria_mode"): "EVALUATION_PRAGMATIC_FACTUAL_CRITERIA_MODE",
    ("evaluation", "run_pre_query_satisfiability_check"): "EVALUATION_RUN_PRE_QUERY_SATISFIABILITY_CHECK",
    ("evaluation", "enable_intent_diagnostics_on_unknown"): "EVALUATION_ENABLE_INTENT_DIAGNOSTICS_ON_UNKNOWN",
    ("debug", "llm_call_tracking"): "DEBUG_LLM_CALL_TRACKING",
}


def _env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def env_from_profile(profile: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for mapping in (ENV_MAP, EXTRA_ENV_MAP):
        for (section, key), env_name in mapping.items():
            if isinstance(profile.get(section), dict) and key in profile[section]:
                out[env_name] = _env_value(profile[section][key])
    if isinstance(profile.get("extraction"), dict) and "max_retries" in profile["extraction"]:
        out["PIPELINE_EXTRACTION_MAX_RETRIES"] = _env_value(profile["extraction"]["max_retries"])
    return out


def profile_name(path: Path) -> str:
    stem = path.stem
    for prefix in ("ablation_", "config_"):
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
    return stem


def main() -> int:
    ap = argparse.ArgumentParser(description="Run evaluation for several config profiles without editing config/local.json.")
    ap.add_argument("--profiles", nargs="+", required=True, help="Config overlay JSON files, e.g. config/cheap.json")
    ap.add_argument("--runs", required=True, help="Comma-separated runs, e.g. run_001,run_004,run_009")
    ap.add_argument("--strategies", default="direct_json_ir_no_translate", help="Comma-separated strategies")
    ap.add_argument("--runs-dir", default="inputs/json_final", help="Run input directory")
    ap.add_argument("--output-root", default=None, help="Root output directory; default results/reports/config_<timestamp>")
    ap.add_argument("--model", default=None, help="Optional OPENAI_MODEL override for all profiles")
    ap.add_argument("--no-clean", action="store_true", help="Do not pass --clean to run_evaluation.py")
    ap.add_argument("--dry-run", action="store_true", help="Print commands/env but do not run")
    args = ap.parse_args()

    root = Path(args.output_root or f"results/reports/config_{datetime.now().strftime('%Y%m%dT%H%M%S')}")
    root.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for profile_path_s in args.profiles:
        profile_path = Path(profile_path_s)
        with open(profile_path, encoding="utf-8") as f:
            profile = json.load(f)
        env = os.environ.copy()
        if args.model:
            env["OPENAI_MODEL"] = args.model
        name = profile_name(profile_path)
        out_dir = root / name
        profile_resolved = profile_path.resolve()
        cmd = [
            sys.executable,
            "scripts/run_evaluation.py",
            "--runs-dir",
            args.runs_dir,
            "--runs",
            args.runs,
            "--strategies",
            args.strategies,
            "--config",
            str(profile_resolved),
            "--ignore-local-config",
            "--output-dir",
            str(out_dir),
            "--no-fail-on-missing-score",
        ]
        if not args.no_clean:
            cmd.append("--clean")
        print("\n=== PROFILE", name, "===")
        print("Config:", profile_path)
        print("Output:", out_dir)
        if args.model:
            print("Env overrides:")
            print(f"  OPENAI_MODEL={env.get('OPENAI_MODEL', '')}")
        print("Command:", " ".join(cmd))
        if args.dry_run:
            continue
        rc = subprocess.call(cmd, env=env)
        if rc != 0:
            exit_code = rc
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
