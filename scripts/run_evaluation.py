#!/usr/bin/env python
"""
Run JSON benchmark(s) across selected KB compilation strategies and produce a comparison report.

Usage (from project root):

  python scripts/run_evaluation.py
  python scripts/run_evaluation.py --runs run_003
  python scripts/run_evaluation.py --runs all --strategies all
  python scripts/run_evaluation.py --runs run_003 --strategies direct_json_ir_translate,le_json_ir_no_translate
  python scripts/run_evaluation.py --runs-dir inputs/json --runs run_001,run_003 --excel
  python scripts/run_evaluation.py --runs all --strategies all --max-failures 8

Outputs under results/reports/evaluation_<timestamp>/:
  - matrix.json      full results (includes evaluation_cli: kb_backend, pipeline_backend)
  - report.md        human-readable tables
  - summary.csv      open in Excel / LibreOffice
  - summary.xlsx     if openpyxl is installed (--excel)
  - timings.csv      per-cell wall-clock duration (seconds)
  - work/            per (run, strategy[, pipeline]) output dirs — distinct names for legacy vs json_ir

Default: --pipeline-backend json_ir; --kb-backend omitted (not passed to main.py). For a legacy sweep use
``--pipeline-backend legacy``. Passing both --kb-backend and --pipeline-backend can confuse: main.py ignores
--kb-backend when --pipeline-backend is set (stderr warning in main.py).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
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
strategy_metadata_for_eval = eval_support.strategy_metadata_for_eval
CANONICAL_JSON_IR_STRATEGIES = eval_support.CANONICAL_JSON_IR_STRATEGIES
read_score = eval_support.read_score
summarize_query_targets = eval_support.summarize_query_targets
run_main_json = eval_support.run_main_json
work_dir_name = eval_support.work_dir_name
classify_failure = eval_support.classify_failure
is_eval_pipeline_failure = eval_support.is_eval_pipeline_failure
from pipeline.kb.compile_backend import KB_BACKEND_CHOICES


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return ""
    s = float(seconds)
    if s < 60:
        return "%.1fs" % s
    if s < 3600:
        return "%.1fm" % (s / 60.0)
    return "%.2fh" % (s / 3600.0)


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
    if matrix.get("stopped_early"):
        lines.extend(
            [
                "",
                "**Note:** Stopped early: " + str(matrix.get("stop_reason") or "") + ".",
                "",
            ]
        )
    elif matrix.get("run_finished") is False:
        lines.extend(["", "**Note:** Run was interrupted; some strategy cells may be missing.", ""])
    lines.extend(
        [
            "",
            "## Accuracy (decisive: correct / total; inconclusive counts as not correct)",
            "",
            "Primary metric: ``accuracy_decisive`` (unknown/open answers are not correct).",
            "",
            "| Run | " + " | ".join(strategies) + " |",
            "|" + "---|" * (len(strategies) + 1),
        ]
    )
    cli = matrix.get("evaluation_cli") or {}
    strat_meta = matrix.get("strategy_definitions") or {}
    if strat_meta:
        lines.extend(
            [
                "",
                "## Strategy configuration",
                "",
                "JSON_IR backend always compiles via ``symbols_then_rules`` (symbols then rules). "
                "Legacy names ``direct_two_phase`` / ``le_two_phase`` only change legacy FO staging; "
                "they are deprecated for JSON_IR sweeps.",
                "",
                "| Strategy | Canonical | LE | Config trans | Effective trans | Source | JSON IR | Depr |",
                "|---|:---|:---:|:---:|:---:|:---|:---|:---:|",
            ]
        )
        for s in strategies:
            d = strat_meta.get(s) or {}
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s | %s |"
                % (
                    s,
                    d.get("canonical_strategy_name") or s,
                    "yes" if d.get("uses_le_intermediate") else "no",
                    "yes" if d.get("configured_translation") else "no",
                    "yes" if d.get("effective_translation") else "no",
                    d.get("translation_source") or "—",
                    d.get("json_ir_generation") or "—",
                    "yes" if d.get("strategy_deprecated") else "no",
                )
            )
        override_warns = [
            d.get("translation_override_warning")
            for d in strat_meta.values()
            if d.get("translation_override_warning")
        ]
        if cli.get("no_translate_global") or override_warns:
            lines.extend(["", "**Translation overrides:**", ""])
            if cli.get("no_translate_global"):
                lines.append(
                    "- Global ``--no-translate``: effective translation forced off for every cell."
                )
            for w in override_warns:
                lines.append("- " + str(w))
    if cli.get("belief_scoring"):
        lines.extend(
            [
                "",
                "**Note:** Belief scoring was enabled for this run. "
                "Open-world answers may be scored probabilistically; "
                "``accuracy_decisive`` is still the main legal entailment metric.",
            ]
        )
    for r in runs:
        row = "| " + r + " |"
        for s in strategies:
            c = cells.get(r, {}).get(s, {})
            if c.get("ok"):
                acc = c.get("accuracy_decisive") if c.get("accuracy_decisive") is not None else c.get("accuracy")
                cor = c.get("correct")
                tot = c.get("total")
                inc = c.get("inconclusive")
                cell = "" if acc is None else "%.4f" % float(acc)
                if cor is not None and tot is not None:
                    cell += " (%s/%s" % (cor, tot)
                    if inc is not None:
                        cell += ", inc=%s" % inc
                    cell += ")"
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

    lines.extend(
        [
            "",
            "## Query target diagnostics",
            "",
            "Per-question query predicate and kind from `score.json` items. "
            "``observable_query_target_warning_count`` / ``antecedent_diagnostic_warning_count`` split score warnings.",
            "",
            "| Run | " + " | ".join(strategies) + " |",
            "|" + "---|" * (len(strategies) + 1),
        ]
    )
    for r in runs:
        row = "| " + r + " |"
        for s in strategies:
            c = cells.get(r, {}).get(s, {})
            oqt = c.get("observable_query_target_warning_count")
            ant = c.get("antecedent_diagnostic_warning_count")
            if c.get("ok") and oqt is not None:
                cell = f"oqt={oqt},ant={ant}"
                targets = c.get("query_targets") or []
                if targets:
                    kinds = ", ".join(
                        sorted(
                            {
                                str(t.get("predicate_kind") or "?")
                                + ":"
                                + str(t.get("predicate") or "?")
                                for t in targets
                            }
                        )
                    )
                    cell += " (" + kinds + ")"
            else:
                cell = "—"
            row += " " + cell + " |"
        lines.append(row)

    timing = matrix.get("timing") or {}
    if timing:
        lines.extend(
            [
                "",
                "## Timing",
                "",
                "- Elapsed: " + _format_duration(timing.get("elapsed_sec"))
                + (" (%s s)" % timing.get("elapsed_sec") if timing.get("elapsed_sec") is not None else ""),
                "- Cells recorded: " + str(timing.get("cells_recorded", "")),
                "- Avg per cell: "
                + _format_duration(timing.get("avg_sec_per_cell"))
                + (" (%s s)" % timing.get("avg_sec_per_cell") if timing.get("avg_sec_per_cell") is not None else ""),
                "",
                "See `timings.csv` for per (run, strategy) durations.",
            ]
        )

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


def _write_timings_csv(path: Path, matrix: dict) -> None:
    runs = matrix["runs"]
    strategies = matrix["strategies"]
    cells = matrix["cells"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "run_id",
                "strategy",
                "duration_sec",
                "duration_human",
                "ok",
                "failure_category",
                "exit_code",
            ]
        )
        for r in runs:
            for s in strategies:
                c = cells.get(r, {}).get(s, {})
                if not c:
                    continue
                dur = c.get("duration_sec")
                w.writerow(
                    [
                        r,
                        s,
                        dur,
                        _format_duration(dur),
                        c.get("ok"),
                        c.get("failure_category"),
                        c.get("exit_code"),
                    ]
                )


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
            "accuracy_decisive",
            "correct",
            "incorrect_decisive",
            "inconclusive",
            "total",
            "scoring_mode",
            "path",
            "exit_code",
            "duration_sec",
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
                    c.get("accuracy_decisive", c.get("accuracy")),
                    c.get("correct"),
                    c.get("incorrect_decisive"),
                    c.get("inconclusive"),
                    c.get("total"),
                    c.get("scoring_mode"),
                    c.get("path"),
                    c.get("exit_code"),
                    c.get("duration_sec"),
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
        help="Comma-separated strategy names or 'all'. Default 'all' runs the four canonical "
        "JSON_IR strategies (direct/le × translate/no_translate). Deprecated legacy aliases "
        "(direct_single, le_two_phase, …) must be named explicitly. Choices: "
        + ", ".join(STRATEGY_CHOICES),
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Report folder (default: results/reports/evaluation_<timestamp>)",
    )
    p.add_argument(
        "--no-translate",
        action="store_true",
        help="Force skip translation for every cell (overrides per-strategy translate defaults). "
        "Without this flag, each strategy uses its own translate setting.",
    )
    p.add_argument(
        "--kb-backend",
        default=None,
        metavar="NAME",
        help="Optional: pass through to main.py --kb-backend (legacy_fo | json_ir). Ignored when "
        "--pipeline-backend is set, because the pipeline flag fixes KB+extraction together. "
        "Omit both this and --pipeline-backend to use .env defaults.",
    )
    p.add_argument(
        "--pipeline-backend",
        default="json_ir",
        metavar="NAME",
        help="Unified pipeline backend for main.py: 'legacy' or 'json_ir' (sets KB+extraction). "
        "Default: json_ir. For a legacy sweep use --pipeline-backend legacy.",
    )
    p.add_argument("--clean", action="store_true", help="Remove output-dir if it exists before run")
    p.add_argument(
        "--excel",
        action="store_true",
        help="Also write summary.xlsx (requires: pip install openpyxl)",
    )
    p.add_argument(
        "--belief-scoring",
        action="store_true",
        help="Set SCORE_TREAT_OPEN_WITH_BELIEF=1 and SCORE_BOOLEAN_BELIEF_THRESHOLD=0.5 for boolean "
        "questions (scores open-world answers by credence; default is off / inconclusive).",
    )
    p.add_argument(
        "--max-failures",
        type=int,
        default=None,
        metavar="N",
        help="Stop the matrix early after N pipeline failures (non-zero exit, compile/reasoning "
        "categories, or symbolic_status=error in score.json). Wrong decisive answers do not "
        "count. Example: --max-failures 8 stops after ~2 runs if all four strategies fail.",
    )
    args = p.parse_args()
    if args.kb_backend is not None and args.kb_backend not in KB_BACKEND_CHOICES:
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
        strategies = parse_strategies_selection(
            args.strategies, pipeline_backend=args.pipeline_backend
        )
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
    strategy_definitions = {
        s: strategy_metadata_for_eval(
            s,
            pipeline_backend=args.pipeline_backend,
            kb_backend=args.kb_backend,
            belief_scoring=args.belief_scoring,
            cli_no_translate=args.no_translate,
        )
        for s in strategies
    }

    print("Runs directory:", runs_dir)
    print("Runs:", ", ".join(run_ids))
    print("Strategies:", ", ".join(strategies))
    print("CLI --kb-backend:", args.kb_backend)
    print("CLI --pipeline-backend:", args.pipeline_backend)
    if args.pipeline_backend and args.kb_backend:
        implied = "json_ir" if args.pipeline_backend == "json_ir" else "legacy_fo"
        if args.kb_backend != implied:
            print(
                "Note: main.py ignores --kb-backend when --pipeline-backend is set "
                "(effective KB backend is " + implied + ").",
                file=sys.stderr,
            )
    print("Output:", out)
    print()

    exit_ok = True
    run_finished = False
    stop_reason: str | None = None
    pipeline_failure_count = 0
    eval_t0 = time.perf_counter()
    max_failures = args.max_failures
    if max_failures is not None and max_failures < 1:
        print("--max-failures must be >= 1", file=sys.stderr)
        return 1
    try:
        for src in run_paths:
            rid = src.name
            for strategy in strategies:
                wdir = work_root / work_dir_name(
                    src,
                    strategy,
                    pipeline_backend=args.pipeline_backend,
                    kb_backend=args.kb_backend if args.pipeline_backend is None else None,
                )
                print("===", rid, "+", strategy, "->", wdir.name, "===")
                cell_t0 = time.perf_counter()
                copy_run_json(src, wdir)
                cell_meta = strategy_metadata_for_eval(
                    strategy,
                    pipeline_backend=args.pipeline_backend,
                    kb_backend=args.kb_backend,
                    belief_scoring=args.belief_scoring,
                    cli_no_translate=args.no_translate,
                )
                code = run_main_json(
                    wdir,
                    strategy,
                    cli_no_translate=args.no_translate,
                    kb_backend=args.kb_backend,
                    pipeline_backend=args.pipeline_backend,
                    belief_scoring=args.belief_scoring,
                )
                sc = read_score(wdir / "score.json")
                duration_sec = round(time.perf_counter() - cell_t0, 2)
                if code != 0:
                    exit_ok = False
                    failure_category = classify_failure(wdir, code, ok=False)
                    cells[rid][strategy] = {
                        "ok": False,
                        "exit_code": code,
                        "path": str(wdir),
                        "accuracy": None,
                        "correct": None,
                        "total": None,
                        "failure_category": failure_category,
                        "duration_sec": duration_sec,
                        "strategy_metadata": cell_meta,
                    }
                    if is_eval_pipeline_failure(
                        exit_code=code,
                        failure_category=failure_category,
                        score=sc,
                    ):
                        pipeline_failure_count += 1
                else:
                    qt = summarize_query_targets(sc)
                    failure_category = classify_failure(wdir, 0, ok=True)
                    cell_ok = failure_category == "completed"
                    if not cell_ok:
                        exit_ok = False
                    cells[rid][strategy] = {
                        "ok": cell_ok,
                        "exit_code": 0,
                        "path": str(wdir),
                        "accuracy": sc.get("accuracy") if sc else None,
                        "accuracy_decisive": sc.get("accuracy_decisive")
                        if sc
                        else sc.get("accuracy")
                        if sc
                        else None,
                        "correct": sc.get("correct") if sc else None,
                        "correct_decisive": sc.get("correct_decisive") if sc else None,
                        "incorrect_decisive": sc.get("incorrect_decisive") if sc else None,
                        "inconclusive": sc.get("inconclusive") if sc else None,
                        "total": sc.get("total") if sc else None,
                        "scoring_mode": sc.get("scoring_mode") if sc else None,
                        "score_id": sc.get("id") if sc else None,
                        "query_targets": qt.get("items") or [],
                        "observable_query_target_warning_count": qt.get(
                            "observable_query_target_warning_count", 0
                        ),
                        "antecedent_diagnostic_warning_count": qt.get(
                            "antecedent_diagnostic_warning_count", 0
                        ),
                        "failure_category": failure_category,
                        "duration_sec": duration_sec,
                        "strategy_metadata": cell_meta,
                    }
                    if is_eval_pipeline_failure(
                        exit_code=0,
                        failure_category=failure_category,
                        score=sc,
                    ):
                        pipeline_failure_count += 1

                status_label = (
                    failure_category
                    if code != 0
                    else (failure_category if not cell_ok else "completed")
                )
                print("[eval] %s — %s" % (_format_duration(duration_sec), status_label))
                ow = cell_meta.get("translation_override_warning")
                if ow:
                    print("[eval] WARNING:", ow, file=sys.stderr)

                if max_failures is not None:
                    print(
                        "[eval] pipeline failures: %s/%s"
                        % (pipeline_failure_count, max_failures)
                    )
                    if pipeline_failure_count >= max_failures:
                        stop_reason = (
                            "max_failures (%s)" % max_failures
                        )
                        print(
                            "Stopping early: %s pipeline failures reached."
                            % pipeline_failure_count,
                            file=sys.stderr,
                        )
                        break
            if stop_reason:
                break
        else:
            run_finished = True
    except KeyboardInterrupt:
        print("\nInterrupted — writing partial matrix/report to " + str(out), file=sys.stderr)
    finally:
        elapsed_sec = round(time.perf_counter() - eval_t0, 2)
        durations = [
            float(c["duration_sec"])
            for row in cells.values()
            for c in row.values()
            if isinstance(c, dict) and c.get("duration_sec") is not None
        ]
        timing_summary = {
            "started_at_utc": stamp,
            "elapsed_sec": elapsed_sec,
            "cells_recorded": len(durations),
            "avg_sec_per_cell": round(sum(durations) / len(durations), 2) if durations else None,
        }
        matrix = {
            "generated_at": stamp,
            "runs_dir": str(runs_dir),
            "strategies": strategies,
            "runs": run_ids,
            "cells": cells,
            "run_finished": run_finished,
            "timing": timing_summary,
            "evaluation_cli": {
                "kb_backend": args.kb_backend,
                "pipeline_backend": args.pipeline_backend,
                "no_translate_global": args.no_translate,
                "belief_scoring": bool(args.belief_scoring),
                "max_failures": max_failures,
            },
            "strategy_definitions": strategy_definitions,
            "canonical_json_ir_strategies": list(CANONICAL_JSON_IR_STRATEGIES),
            "stopped_early": bool(stop_reason),
            "stop_reason": stop_reason,
            "pipeline_failure_count": pipeline_failure_count,
        }
        try:
            (out / "matrix.json").write_text(
                json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            _write_markdown(out / "report.md", matrix)
            _write_csv(out / "summary.csv", matrix)
            _write_timings_csv(out / "timings.csv", matrix)
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
            print("Wrote:", out / "timings.csv")
            if timing_summary.get("cells_recorded"):
                print(
                    "Timing: %s total, %s avg/cell (%s cells)"
                    % (
                        _format_duration(timing_summary.get("elapsed_sec")),
                        _format_duration(timing_summary.get("avg_sec_per_cell")),
                        timing_summary.get("cells_recorded"),
                    )
                )
            if args.excel and xlsx_ok:
                print("Wrote:", out / "summary.xlsx")
        except OSError as e:
            print("Failed to write evaluation reports:", e, file=sys.stderr)

    if stop_reason or not run_finished:
        return 1
    return 0 if exit_ok else 1


if __name__ == "__main__":
    sys.exit(main())
