#!/usr/bin/env python
"""
Run the same JSON benchmark four times — once per KB compilation strategy — in separate
folders so you can diff results.json / score.json side by side.

Usage (from project root):

  python scripts/compare_kb_strategies.py --run inputs/json/run_003

Output layout (default):

  inputs/json/run_003/kb_strategy_compare/
    direct_single/run.json results.json score.json ...
    direct_two_phase/...
    le_single/...
    le_two_phase/...

Each folder is an independent run directory (its own KB cache under translated/le/...).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.kb.compile_strategy import STRATEGY_CHOICES


def _copy_run_json(src_run_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_run_dir / "run.json", dest_dir / "run.json")


def _run_main_json(run_dir: Path, strategy: str, no_translate: bool) -> int:
    cmd = [
        sys.executable,
        str(_ROOT / "main.py"),
        "--mode",
        "json",
        "--run",
        str(run_dir),
        "--kb-strategy",
        strategy,
    ]
    if no_translate:
        cmd.append("--no-translate")
    return subprocess.call(cmd, cwd=str(_ROOT))


def _read_score(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


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

    for strategy in STRATEGY_CHOICES:
        sub = out_base / strategy
        print("\n=== Strategy:", strategy, "->", sub, "===\n")
        _copy_run_json(src, sub)
        code = _run_main_json(sub, strategy, args.no_translate)
        if code != 0:
            print("Run failed with exit code", code, file=sys.stderr)
            results_summary.append(
                {"strategy": strategy, "path": str(sub), "ok": False, "exit_code": code}
            )
            continue
        sc = _read_score(sub / "score.json")
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
