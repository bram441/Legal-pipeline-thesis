#!/usr/bin/env python
"""Run run_evaluation.py once per model and aggregate comparison metrics.

Example (OpenRouter):

  python scripts/run_model_sweep.py ^
    --provider openrouter ^
    --models-file config/model_sweep_models.txt ^
    --input-dir inputs/json_final_clean ^
    --strategies direct_json_ir_no_translate le_json_ir_no_translate ^
    --config config/ablation_balanced.json ^
    --ignore-local-config ^
    --clean ^
    --no-fail-on-missing-score ^
    --output-root results/reports/model_sweep_clean_law
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_OPENROUTER_DEFAULT_BASE = "https://openrouter.ai/api/v1"


def sanitize_model_name(model: str) -> str:
    """Filesystem-safe folder name: ``openai/gpt-5.5`` -> ``openai_gpt-5.5``."""
    s = (model or "").strip()
    for ch in ("/", "\\", ":", " ", "@", "#", "?", "*"):
        s = s.replace(ch, "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_") or "unknown_model"


def _strategies_for_subprocess(strategies: list[str]) -> str:
    return ",".join(s.strip() for s in strategies if s.strip())


def load_models_from_file(path: str | Path) -> list[str]:
    """
    Load model ids from a text or JSON file.

    Text format: one model per line; ``#`` starts a comment (rest of line ignored).
    JSON format: a list of strings, or ``{"models": ["...", ...]}``.
    """
    p = Path(path)
    if not p.is_absolute():
        p = (_ROOT / p).resolve()
    else:
        p = p.resolve()
    if not p.is_file():
        raise FileNotFoundError("Models file not found: " + str(p))

    if p.suffix.lower() == ".json":
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            raw = data
        elif isinstance(data, dict) and isinstance(data.get("models"), list):
            raw = data["models"]
        else:
            raise ValueError(
                "JSON models file must be a list or {\"models\": [\"model/id\", ...]}: " + str(p)
            )
        return [str(m).strip() for m in raw if str(m).strip()]

    models: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0].strip()
        if line:
            models.append(line)
    return models


def resolve_models(cli_models: list[str] | None, models_file: str | None) -> list[str]:
    """Merge models from ``--models-file`` and ``--models`` (file first, de-duplicated)."""
    out: list[str] = []
    seen: set[str] = set()
    if models_file:
        for m in load_models_from_file(models_file):
            if m not in seen:
                seen.add(m)
                out.append(m)
    for m in cli_models or []:
        m = m.strip()
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _aggregate_matrix(
    matrix_path: Path,
    *,
    model: str,
    provider: str,
    output_dir: Path,
    exit_code: int,
    duration_sec: float,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "model": model,
        "provider": provider,
        "output_dir": str(output_dir),
        "exit_code": exit_code,
        "duration_sec": round(duration_sec, 2),
        "matrix_path": str(matrix_path) if matrix_path.is_file() else None,
        "total_cells": 0,
        "scored_cells": 0,
        "correct_decisive": 0,
        "wrong_decisive": 0,
        "inconclusive": 0,
        "law_compilation_failures": 0,
        "completed_with_errors": 0,
        "unsupported_intent": 0,
        "strict_accuracy": None,
        "coverage": None,
        "decisive_precision": None,
        "decisive_wrong_rate": None,
        "total_llm_calls": None,
        "total_prompt_tokens": None,
        "total_completion_tokens": None,
        "total_tokens": None,
        "estimated_cost_usd": None,
    }
    if not matrix_path.is_file():
        return row

    data = json.loads(matrix_path.read_text(encoding="utf-8"))
    cells = data.get("cells") or {}
    runs = data.get("runs") or []
    strategies = data.get("strategies") or []

    total_cells = 0
    scored_cells = 0
    correct_decisive = 0
    wrong_decisive = 0
    inconclusive = 0
    law_compilation = 0
    completed_with_errors = 0
    unsupported_intent = 0

    for run_id in runs:
        for strat in strategies:
            cell = (cells.get(run_id) or {}).get(strat)
            if not cell:
                continue
            total_cells += 1
            if cell.get("scored"):
                scored_cells += 1
                correct_decisive += int(cell.get("correct_decisive") or 0)
                wrong_decisive += int(cell.get("incorrect_decisive") or 0)
                inconclusive += int(cell.get("inconclusive") or 0)
            cat = (cell.get("failure_category") or "").strip()
            if cat == "law_compilation":
                law_compilation += 1
            elif cat == "completed_with_errors":
                completed_with_errors += 1
            elif cat == "unsupported_intent":
                unsupported_intent += 1

    decisive = correct_decisive + wrong_decisive
    row.update(
        {
            "total_cells": total_cells,
            "scored_cells": scored_cells,
            "correct_decisive": correct_decisive,
            "wrong_decisive": wrong_decisive,
            "inconclusive": inconclusive,
            "law_compilation_failures": law_compilation,
            "completed_with_errors": completed_with_errors,
            "unsupported_intent": unsupported_intent,
            "strict_accuracy": (correct_decisive / total_cells) if total_cells else None,
            "coverage": (scored_cells / total_cells) if total_cells else None,
            "decisive_precision": (correct_decisive / decisive) if decisive else None,
            "decisive_wrong_rate": (wrong_decisive / decisive) if decisive else None,
        }
    )

    llm_summary = data.get("llm_call_summary") or {}
    if llm_summary:
        row["total_llm_calls"] = llm_summary.get("call_count")
        row["total_prompt_tokens"] = llm_summary.get("total_prompt_tokens")
        row["total_completion_tokens"] = llm_summary.get("total_completion_tokens")
        row["total_tokens"] = llm_summary.get("total_tokens")
        row["estimated_cost_usd"] = llm_summary.get("estimated_total_cost_usd")
    else:
        llm_path = output_dir / "llm_call_summary.json"
        if llm_path.is_file():
            try:
                ls = json.loads(llm_path.read_text(encoding="utf-8"))
                row["total_llm_calls"] = ls.get("call_count")
                row["total_prompt_tokens"] = ls.get("total_prompt_tokens")
                row["total_completion_tokens"] = ls.get("total_completion_tokens")
                row["total_tokens"] = ls.get("total_tokens")
                row["estimated_cost_usd"] = ls.get("estimated_total_cost_usd")
            except (OSError, json.JSONDecodeError):
                pass

    cli = data.get("evaluation_cli") or {}
    if cli.get("model"):
        row["model"] = cli["model"]
    if cli.get("provider"):
        row["provider"] = cli["provider"]

    return row


def _rank_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]) -> tuple:
        sa = r.get("strict_accuracy")
        dp = r.get("decisive_precision")
        cov = r.get("coverage")
        cost = r.get("estimated_cost_usd")
        tokens = r.get("total_tokens")
        return (
            -(sa if isinstance(sa, (int, float)) else -1.0),
            -(dp if isinstance(dp, (int, float)) else -1.0),
            -(cov if isinstance(cov, (int, float)) else -1.0),
            cost if isinstance(cost, (int, float)) else 1e18,
            tokens if isinstance(tokens, (int, float)) else 1e18,
            str(r.get("model") or ""),
        )

    return sorted(rows, key=key)


def _write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "model",
        "provider",
        "exit_code",
        "strict_accuracy",
        "coverage",
        "decisive_precision",
        "decisive_wrong_rate",
        "total_cells",
        "scored_cells",
        "correct_decisive",
        "wrong_decisive",
        "inconclusive",
        "law_compilation_failures",
        "completed_with_errors",
        "unsupported_intent",
        "total_llm_calls",
        "total_tokens",
        "estimated_cost_usd",
        "duration_sec",
        "output_dir",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _write_summary_md(path: Path, rows: list[dict[str, Any]], *, timestamp: str) -> None:
    ranked = _rank_rows(rows)
    lines = [
        "# Model sweep report",
        "",
        "Generated: " + timestamp,
        "",
        "**Warnings**",
        "",
        "- Model sweeps on a subset are exploratory only.",
        "- Confirm the final model with a full best-strategy run on the thesis test set.",
        "- ``possible`` / model-expansion answers are not Boolean entailment.",
        "- Compare models only with the same strategy, config profile, and test set.",
        "- Non-OpenAI models may be worse at strict JSON; validation/repair still applies.",
        "- Cost limits are best-effort when enforced only after each model completes.",
        "",
        "## Ranking (strict accuracy, then decisive precision, coverage, cost)",
        "",
        "| Rank | Model | Provider | Exit | Strict acc | Coverage | Decisive prec | Cost USD | Tokens |",
        "|---:|---|---|:---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ranked, start=1):
        sa = r.get("strict_accuracy")
        cov = r.get("coverage")
        dp = r.get("decisive_precision")
        cost = r.get("estimated_cost_usd")
        tok = r.get("total_tokens")
        lines.append(
            "| %d | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                i,
                r.get("model", ""),
                r.get("provider", ""),
                r.get("exit_code", ""),
                "%.4f" % sa if isinstance(sa, (int, float)) else "—",
                "%.4f" % cov if isinstance(cov, (int, float)) else "—",
                "%.4f" % dp if isinstance(dp, (int, float)) else "—",
                "%.4f" % cost if isinstance(cost, (int, float)) else "—",
                str(tok) if tok is not None else "—",
            )
        )
    lines.extend(["", "## Per-model output directories", ""])
    for r in ranked:
        lines.append("- `%s` → `%s`" % (r.get("model"), r.get("output_dir")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _subprocess_env(
    *,
    provider: str,
    model: str,
    base_url: str | None,
) -> dict[str, str]:
    env = os.environ.copy()
    env["LLM_PROVIDER"] = provider
    env["LLM_MODEL"] = model
    env["OPENAI_MODEL"] = model
    if provider == "openrouter":
        env["LLM_BASE_URL"] = (base_url or _OPENROUTER_DEFAULT_BASE).strip()
        key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("LLM_API_KEY") or "").strip()
        if key:
            env["LLM_API_KEY"] = key
    elif base_url:
        env["LLM_BASE_URL"] = base_url.strip()
    return env


def main() -> int:
    ap = argparse.ArgumentParser(description="Run evaluation once per model and aggregate results.")
    ap.add_argument(
        "--models",
        nargs="*",
        default=None,
        help="Model ids on the command line (optional if --models-file is set)",
    )
    ap.add_argument(
        "--models-file",
        default=None,
        help="Path to a text file (one model per line, # comments) or JSON list of models",
    )
    ap.add_argument(
        "--input-dir",
        "--runs-dir",
        dest="runs_dir",
        default="inputs/json",
        help="Benchmark input directory (alias: --runs-dir)",
    )
    ap.add_argument("--strategies", nargs="+", required=True, help="Strategies (space-separated)")
    ap.add_argument("--config", required=True, help="Config profile JSON path")
    ap.add_argument("--output-root", required=True, help="Root folder for per-model outputs and summary")
    ap.add_argument("--runs", default=None, help="Optional comma-separated run ids")
    ap.add_argument("--ignore-local-config", action="store_true")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--no-fail-on-missing-score", action="store_true")
    ap.add_argument(
        "--provider",
        default=None,
        choices=("openai", "openrouter"),
        help="LLM provider (default: LLM_PROVIDER env or openai)",
    )
    ap.add_argument("--base-url", default=None, help="Optional API base URL override")
    ap.add_argument("--max-total-cost", type=float, default=None, help="Stop sweep after estimated USD (best-effort)")
    ap.add_argument("--max-llm-calls", type=int, default=None, help="Passed to run_evaluation.py per model")
    ap.add_argument(
        "--max-llm-calls-per-model",
        type=int,
        default=None,
        help="Alias for --max-llm-calls (per-model eval budget)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print commands only")
    args = ap.parse_args()

    try:
        models = resolve_models(args.models, args.models_file)
    except (OSError, json.JSONDecodeError, ValueError) as e:
        ap.error(str(e))
    if not models:
        ap.error("No models to run: provide --models-file and/or --models")

    provider = (args.provider or os.getenv("LLM_PROVIDER") or "openai").strip().lower()
    if provider not in ("openai", "openrouter"):
        provider = "openrouter" if provider in ("open_router",) else "openai"

    max_llm_calls = args.max_llm_calls
    if max_llm_calls is None and args.max_llm_calls_per_model is not None:
        max_llm_calls = args.max_llm_calls_per_model

    output_root = Path(args.output_root)
    if not output_root.is_absolute():
        output_root = _ROOT / output_root
    output_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    strategies = _strategies_for_subprocess(args.strategies)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (_ROOT / config_path).resolve()

    rows: list[dict[str, Any]] = []
    cumulative_cost = 0.0
    cost_known = False
    exit_code = 0

    print("Models (%d):" % len(models), ", ".join(models))

    for model in models:
        folder = "%s_%s" % (sanitize_model_name(model), timestamp)
        out_dir = output_root / folder
        cmd = [
            sys.executable,
            str(_ROOT / "scripts" / "run_evaluation.py"),
            "--input-dir",
            args.runs_dir,
            "--strategies",
            strategies,
            "--config",
            str(config_path),
            "--output-dir",
            str(out_dir),
        ]
        if args.runs:
            cmd.extend(["--runs", args.runs])
        if args.ignore_local_config:
            cmd.append("--ignore-local-config")
        if args.clean:
            cmd.append("--clean")
        if args.no_fail_on_missing_score:
            cmd.append("--no-fail-on-missing-score")
        if max_llm_calls is not None:
            cmd.extend(["--max-llm-calls", str(max_llm_calls)])

        env = _subprocess_env(provider=provider, model=model, base_url=args.base_url)
        print("\n=== MODEL", model, "===")
        print("Output:", out_dir)
        print("Provider:", provider)
        if args.dry_run:
            print("Command:", " ".join(cmd))
            continue

        t0 = time.perf_counter()
        rc = subprocess.call(cmd, env=env, cwd=str(_ROOT))
        duration = time.perf_counter() - t0
        if rc != 0:
            exit_code = rc

        matrix_path = out_dir / "matrix.json"
        row = _aggregate_matrix(
            matrix_path,
            model=model,
            provider=provider,
            output_dir=out_dir,
            exit_code=rc,
            duration_sec=duration,
        )
        rows.append(row)

        est = row.get("estimated_cost_usd")
        if isinstance(est, (int, float)):
            cost_known = True
            cumulative_cost += float(est)
        if args.max_total_cost is not None and cost_known and cumulative_cost >= args.max_total_cost:
            print(
                "Stopping sweep: cumulative estimated cost %.4f >= max %.4f"
                % (cumulative_cost, args.max_total_cost)
            )
            break

    stamp = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at": stamp,
        "timestamp": timestamp,
        "provider": provider,
        "output_root": str(output_root),
        "models": models,
        "models_file": str(Path(args.models_file).resolve()) if args.models_file else None,
        "rows": rows,
    }
    (output_root / "model_sweep_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_summary_csv(output_root / "model_sweep_summary.csv", rows)
    _write_summary_md(output_root / "model_sweep_report.md", rows, timestamp=stamp)

    print("\nWrote:", output_root / "model_sweep_summary.json")
    print("Wrote:", output_root / "model_sweep_summary.csv")
    print("Wrote:", output_root / "model_sweep_report.md")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
