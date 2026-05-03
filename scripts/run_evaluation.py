#!/usr/bin/env python
"""
Run JSON benchmark(s) across selected KB compilation strategies and produce a comparison report.

Usage (from project root):

  python scripts/run_evaluation.py
  python scripts/run_evaluation.py --runs run_003
  python scripts/run_evaluation.py --runs all --strategies direct_single,le_single
  python scripts/run_evaluation.py --runs-dir inputs/json --runs run_001,run_003 --excel

Outputs under results/reports/evaluation_<timestamp>/:
  - matrix.json      full results
  - report.md        human-readable tables
  - summary.csv      open in Excel / LibreOffice
  - summary.xlsx     if openpyxl is installed (--excel)
  - work/            per (run, strategy) output dirs (run.json + pipeline results)
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import importlib.util

_es_path = Path(__file__).resolve().parent / "eval_support.py"
_spec = importlib.util.spec_from_file_location("eval_support", _es_path)
eval_support = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(eval_support)

STRATEGY_CHOICES = eval_support.STRATEGY_CHOICES
copy_run_json = eval_support.copy_run_json
parse_runs_selection = eval_support.parse_runs_selection
parse_strategies_selection = eval_support.parse_strategies_selection
read_score = eval_support.read_score
run_main_json = eval_support.run_main_json
work_dir_name = eval_support.work_dir_name
classify_failure = eval_support.classify_failure
from pipeline.kb.compile_backend import KB_BACKEND_CHOICES


def _write_markdown(path: Path, matrix: dict) -> None:
    runs = matrix["runs"]
    strategies = matrix["strategies"]
    cells = matrix["cells"]

    lines = [
        "# Evaluation report",
        "",
        "- Generated: " + matrix.get("generated_at", ""),
        "- Runs directory: " + matrix.get("runs_dir", ""),
    ]
    if matrix.get("run_finished") is False:
        lines.extend(["", "**Note:** Run was interrupted; some strategy cells may be missing.", ""])
    lines.extend(
        [
            "",
            "## Accuracy (correct / total)",
            "",
            "| Run | " + " | ".join(strategies) + " |",
            "|" + "---|" * (len(strategies) + 1),
        ]
    )
    for r in runs:
        row = "| " + r + " |"
        for s in strategies:
            c = cells.get(r, {}).get(s, {})
            if c.get("ok"):
                acc = c.get("accuracy")
                cor = c.get("correct")
                tot = c.get("total")
                cell = "" if acc is None else "%.4f" % float(acc)
                if cor is not None and tot is not None:
                    cell += " (%s/%s)" % (cor, tot)
            else:
                cell = "FAIL" if c.get("exit_code") is not None else "—"
            row += " " + cell + " |"
        lines.append(row)

    lines.extend(
        [
            "",
            "## Failure / status category",
            "",
            "Heuristic label from `run_trace.txt` / `kb_compile.log` (see `eval_support.classify_failure`).",
            "",
            "| Run | " + " | ".join(strategies) + " |",
            "|" + "---|" * (len(strategies) + 1),
        ]
    )
    for r in runs:
        row = "| " + r + " |"
        for s in strategies:
            cat = cells.get(r, {}).get(s, {}).get("failure_category") or "—"
            row += " " + str(cat) + " |"
        lines.append(row)

    lines.extend(["", "## Details (JSON)", "", "See `matrix.json`.", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, matrix: dict) -> None:
    runs = matrix["runs"]
    strategies = matrix["strategies"]
    cells = matrix["cells"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run_id"] + list(strategies))
        for r in runs:
            row = [r]
            for s in strategies:
                c = cells.get(r, {}).get(s, {})
                if c.get("ok"):
                    acc = c.get("accuracy")
                    row.append("" if acc is None else acc)
                else:
                    row.append("FAIL")
            w.writerow(row)
        w.writerow([])
        w.writerow(["failure_category (same run order)"])
        w.writerow(["run_id"] + list(strategies))
        for r in runs:
            row = [r]
            for s in strategies:
                c = cells.get(r, {}).get(s, {})
                row.append(c.get("failure_category") or "")
            w.writerow(row)


def _write_xlsx(path: Path, matrix: dict) -> bool:
    try:
        from openpyxl import Workbook
    except ImportError:
        return False

    runs = matrix["runs"]
    strategies = matrix["strategies"]
    cells = matrix["cells"]

    wb = Workbook()
    ws = wb.active
    ws.title = "accuracy"
    ws.append(["run_id"] + list(strategies))
    for r in runs:
        row = [r]
        for s in strategies:
            c = cells.get(r, {}).get(s, {})
            if c.get("ok"):
                row.append(c.get("accuracy"))
            else:
                row.append("FAIL")
        ws.append(row)

    ws2 = wb.create_sheet("details")
    ws2.append(
        [
            "run_id",
            "strategy",
            "ok",
            "failure_category",
            "accuracy",
            "correct",
            "total",
            "path",
            "exit_code",
        ]
    )
    for r in runs:
        for s in strategies:
            c = cells.get(r, {}).get(s, {})
            ws2.append(
                [
                    r,
                    s,
                    c.get("ok"),
                    c.get("failure_category"),
                    c.get("accuracy"),
                    c.get("correct"),
                    c.get("total"),
                    c.get("path"),
                    c.get("exit_code"),
                ]
            )

    wb.save(path)
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description="Run JSON benchmark(s) across KB strategies and write comparison reports."
    )
    p.add_argument(
        "--runs-dir",
        default="inputs/json",
        help="Directory containing run folders (each with run.json). Default: inputs/json",
    )
    p.add_argument(
        "--runs",
        default="all",
        help="Comma-separated run folder names (e.g. run_001,run_003) or 'all'. Default: all",
    )
    p.add_argument(
        "--strategies",
        default="all",
        help="Comma-separated strategy names or 'all'. Choices: "
        + ", ".join(STRATEGY_CHOICES)
        + ". Default: all",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Report folder (default: results/reports/evaluation_<timestamp>)",
    )
    p.add_argument("--no-translate", action="store_true", help="Pass --no-translate to main.py")
    p.add_argument(
        "--kb-backend",
        default="legacy_fo",
        help="KB compiler backend: one of " + ", ".join(KB_BACKEND_CHOICES) + ".",
    )
    p.add_argument(
        "--pipeline-backend",
        default="json_ir",
        help="Unified pipeline backend: 'legacy' or 'json_ir' (sets KB+extraction together). Default: json_ir.",
    )
    p.add_argument("--clean", action="store_true", help="Remove output-dir if it exists before run")
    p.add_argument(
        "--excel",
        action="store_true",
        help="Also write summary.xlsx (requires: pip install openpyxl)",
    )
    args = p.parse_args()
    if args.kb_backend not in KB_BACKEND_CHOICES:
        print("--kb-backend must be one of: " + ", ".join(KB_BACKEND_CHOICES), file=sys.stderr)
        return 1
    if args.pipeline_backend is not None and args.pipeline_backend not in ("legacy", "json_ir"):
        print("--pipeline-backend must be one of: legacy, json_ir", file=sys.stderr)
        return 1

    runs_dir = Path(args.runs_dir)
    if not runs_dir.is_absolute():
        runs_dir = _ROOT / runs_dir
    runs_dir = runs_dir.resolve()

    try:
        run_paths = parse_runs_selection(runs_dir, args.runs)
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 1

    try:
        strategies = parse_strategies_selection(args.strategies)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    if not run_paths:
        print("No runs found under", runs_dir, file=sys.stderr)
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.output_dir) if args.output_dir else _ROOT / "results" / "reports" / ("evaluation_" + stamp)
    if not out.is_absolute():
        out = _ROOT / out
    out = out.resolve()
    work_root = out / "work"

    if args.clean and out.is_dir():
        shutil.rmtree(out)

    out.mkdir(parents=True, exist_ok=True)
    work_root.mkdir(parents=True, exist_ok=True)

    run_ids = [p.name for p in run_paths]
    cells: dict[str, dict[str, dict]] = {rid: {} for rid in run_ids}

    print("Runs directory:", runs_dir)
    print("Runs:", ", ".join(run_ids))
    print("Strategies:", ", ".join(strategies))
    print("KB backend:", args.kb_backend)
    if args.pipeline_backend:
        print("Pipeline backend:", args.pipeline_backend)
    print("Output:", out)
    print()

    exit_ok = True
    run_finished = False
    try:
        for src in run_paths:
            rid = src.name
            for strategy in strategies:
                wdir = work_root / work_dir_name(src, strategy)
                print("===", rid, "+", strategy, "->", wdir.name, "===")
                copy_run_json(src, wdir)
                code = run_main_json(
                    wdir,
                    strategy,
                    args.no_translate,
                    kb_backend=args.kb_backend,
                    pipeline_backend=args.pipeline_backend,
                )
                sc = read_score(wdir / "score.json")
                if code != 0:
                    exit_ok = False
                    cells[rid][strategy] = {
                        "ok": False,
                        "exit_code": code,
                        "path": str(wdir),
                        "accuracy": None,
                        "correct": None,
                        "total": None,
                        "failure_category": classify_failure(wdir, code, ok=False),
                    }
                    continue
                cells[rid][strategy] = {
                    "ok": True,
                    "exit_code": 0,
                    "path": str(wdir),
                    "accuracy": sc.get("accuracy") if sc else None,
                    "correct": sc.get("correct") if sc else None,
                    "total": sc.get("total") if sc else None,
                    "score_id": sc.get("id") if sc else None,
                    "failure_category": classify_failure(wdir, 0, ok=True),
                }
        run_finished = True
    except KeyboardInterrupt:
        print("\nInterrupted — writing partial matrix/report to " + str(out), file=sys.stderr)
    finally:
        matrix = {
            "generated_at": stamp,
            "runs_dir": str(runs_dir),
            "strategies": strategies,
            "runs": run_ids,
            "cells": cells,
            "run_finished": run_finished,
        }
        try:
            (out / "matrix.json").write_text(
                json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            _write_markdown(out / "report.md", matrix)
            _write_csv(out / "summary.csv", matrix)
            xlsx_ok = False
            if args.excel:
                xlsx_ok = _write_xlsx(out / "summary.xlsx", matrix)
                if not xlsx_ok:
                    print(
                        "Note: openpyxl not installed; skipped summary.xlsx. pip install openpyxl",
                        file=sys.stderr,
                    )
            print()
            print("Wrote:", out / "matrix.json")
            print("Wrote:", out / "report.md")
            print("Wrote:", out / "summary.csv")
            if args.excel and xlsx_ok:
                print("Wrote:", out / "summary.xlsx")
        except OSError as e:
            print("Failed to write evaluation reports:", e, file=sys.stderr)

    if not run_finished:
        return 1
    return 0 if exit_ok else 1


if __name__ == "__main__":
    sys.exit(main())
