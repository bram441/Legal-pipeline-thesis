#!/usr/bin/env python
"""
Compare all four KB strategies on a single JSON run.

This is a thin wrapper around the same helpers as ``run_evaluation.py``.
For multiple runs + reports, prefer:

  python scripts/run_evaluation.py --runs <folder> --strategies all
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_es_path = Path(__file__).resolve().parent / "eval_support.py"
_spec = importlib.util.spec_from_file_location("eval_support", _es_path)
eval_support = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(eval_support)


def main() -> int:
    p = argparse.ArgumentParser(description="Compare all four KB strategies on one JSON run.")
    p.add_argument(
        "--run",
        required=True,
        help="Path to JSON run folder containing run.json (e.g. inputs/json/run_003)",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Base folder for the four runs (default: <run>/kb_strategy_compare)",
    )
    p.add_argument(
        "--no-translate",
        action="store_true",
        help="Pass --no-translate to main.py (skip EN translation).",
    )
    p.add_argument(
        "--pipeline-backend",
        default="json_ir",
        choices=["legacy", "json_ir"],
        help="Unified pipeline backend for main.py (default: json_ir). Use legacy for the FO+legacy extraction path.",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="Remove output base dir before running (deletes prior compare results).",
    )
    args = p.parse_args()

    src = Path(args.run)
    if not src.is_absolute():
        src = _ROOT / src
    src = src.resolve()
    run_json = src / "run.json"
    if not run_json.is_file():
        print("Not found:", run_json, file=sys.stderr)
        return 1

    out_base = Path(args.output_dir) if args.output_dir else src / "kb_strategy_compare"
    if not out_base.is_absolute():
        out_base = _ROOT / out_base
    out_base = out_base.resolve()

    if args.clean and out_base.is_dir():
        shutil.rmtree(out_base)

    results_summary: list[dict] = []

    strategies = eval_support.default_strategies_for_pipeline(args.pipeline_backend)
    for strategy in strategies:
        sub = out_base / strategy
        print("\n=== Strategy:", strategy, "->", sub, "===\n")
        eval_support.copy_run_json(src, sub)
        code = eval_support.run_main_json(
            sub,
            strategy,
            cli_no_translate=args.no_translate,
            pipeline_backend=args.pipeline_backend,
        )
        if code != 0:
            print("Run failed with exit code", code, file=sys.stderr)
            results_summary.append(
                {"strategy": strategy, "path": str(sub), "ok": False, "exit_code": code}
            )
            continue
        sc = eval_support.read_score(sub / "score.json")
        row: dict = {"strategy": strategy, "path": str(sub), "ok": True, "exit_code": 0}
        if sc:
            row["accuracy"] = sc.get("accuracy")
            row["correct"] = sc.get("correct")
            row["total"] = sc.get("total")
            row["id"] = sc.get("id")
        results_summary.append(row)

    summary_path = out_base / "compare_summary.json"
    out_base.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n=== Summary ===\n")
    for row in results_summary:
        line = row["strategy"] + ": "
        if row.get("ok"):
            line += "accuracy=%s correct=%s/%s" % (
                row.get("accuracy"),
                row.get("correct"),
                row.get("total"),
            )
        else:
            line += "FAILED exit=%s" % row.get("exit_code")
        print(line)
    print("\nWrote:", summary_path)
    print("Per-strategy folders under:", out_base)
    return 0 if all(r.get("ok") for r in results_summary) else 1


if __name__ == "__main__":
    sys.exit(main())
