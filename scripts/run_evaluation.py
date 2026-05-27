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
  - matrix.json      full results (evaluation_cli metadata)
  - report.md        human-readable tables
  - summary.csv      open in Excel / LibreOffice
  - summary.xlsx     if openpyxl is installed (--excel)
  - timings.csv      per-cell wall-clock duration (seconds)
  - work/            per (run, strategy) output dirs
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
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
count_eval_llm_calls = eval_support.count_eval_llm_calls
read_llm_budget_guard = eval_support.read_llm_budget_guard
work_dir_name = eval_support.work_dir_name
build_eval_cell = eval_support.build_eval_cell
summarize_matrix_status = eval_support.summarize_matrix_status
is_eval_pipeline_failure = eval_support.is_eval_pipeline_failure
from pipeline.utils.llm_call_tracker import (  # noqa: E402
    clear_session_records,
    enable_eval_tracking,
    get_eval_call_count,
    reset_cell_call_count,
    reset_eval_call_count as reset_eval_llm_counter,
    set_budget_limits,
    set_eval_report_dir,
    set_run_context,
    write_cell_summary,
    write_eval_summary,
)


def _llm_eval_cli_fields() -> dict[str, str | None]:
    try:
        from pipeline.llm.client import base_url_host, get_llm_model, get_llm_provider

        return {
            "provider": get_llm_provider(),
            "model": get_llm_model(),
            "base_url_host": base_url_host(),
        }
    except Exception:
        return {"provider": None, "model": None, "base_url_host": None}


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
    summary = matrix.get("status_summary") or {}
    lines.extend(
        [
            "",
            "## Pipeline status summary",
            "",
            "- Cells total: " + str(summary.get("cells_total", "")),
            "- **Scored cells** (valid ``score.json`` with ``total``): "
            + str(summary.get("scored_cells", "")),
            "- **evaluation_no_score** (exit 0, no score): "
            + str(summary.get("evaluation_no_score_cells", "")),
            "- **evaluation_bad_score**: " + str(summary.get("evaluation_bad_score_cells", "")),
            "- **law_compilation** failures: " + str(summary.get("law_compilation_cells", "")),
            "- Other failures: " + str(summary.get("other_failure_cells", "")),
        ]
    )
    acc_scored = summary.get("accuracy_decisive_over_scored")
    if acc_scored is not None:
        lines.append(
            "- Accuracy (decisive, **scored cells only**): %.4f" % float(acc_scored)
        )
    lines.extend(
        [
            "",
            "Unscored cells are **not** successful pipeline completions; they are evaluation failures.",
            "",
            "## Accuracy (decisive: correct / total; inconclusive counts as not correct)",
            "",
            "Only **scored** cells show accuracy. Others show ``FAIL`` or status label.",
            "",
            "| Run | " + " | ".join(strategies) + " |",
            "|" + "---|" * (len(strategies) + 1),
        ]
    )
    for r in runs:
        row = "| " + r + " |"
        for s in strategies:
            c = cells.get(r, {}).get(s, {})
            if c.get("scored") and c.get("accuracy_decisive") is not None:
                acc = c.get("accuracy_decisive")
                cor = c.get("correct_decisive")
                tot = c.get("total")
                inc = c.get("inconclusive")
                cell = "%.4f" % float(acc)
                if cor is not None and tot is not None:
                    cell += " (%s/%s" % (cor, tot)
                    if inc is not None:
                        cell += ", inc=%s" % inc
                    cell += ")"
            elif c.get("failure_category"):
                cell = str(c.get("failure_category"))
            else:
                cell = "—"
            row += " " + cell + " |"
        lines.append(row)

    cli = matrix.get("evaluation_cli") or {}
    strat_meta = matrix.get("strategy_definitions") or {}
    if strat_meta:
        lines.extend(
            [
                "",
                "## Strategy configuration",
                "",
                "JSON_IR backend always compiles via ``symbols_then_rules`` (symbols then rules).",
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
            if c.get("scored") and oqt is not None:
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
    summary = matrix.get("status_summary") or {}
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for key, val in summary.items():
            w.writerow([key, val if val is not None else ""])
        w.writerow([])
        w.writerow(["run_id"] + list(strategies))
        w.writerow(["accuracy_decisive (scored cells only)"])
        for r in runs:
            row = [r]
            for s in strategies:
                c = cells.get(r, {}).get(s, {})
                if c.get("scored") and c.get("accuracy_decisive") is not None:
                    row.append(c.get("accuracy_decisive"))
                else:
                    row.append(c.get("failure_category") or "FAIL")
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
        w.writerow([])
        w.writerow(["score_present"])
        w.writerow(["run_id"] + list(strategies))
        for r in runs:
            row = [r]
            for s in strategies:
                c = cells.get(r, {}).get(s, {})
                row.append(c.get("score_present"))
            w.writerow(row)
        w.writerow([])
        w.writerow(["missing_score_reason"])
        w.writerow(["run_id"] + list(strategies))
        for r in runs:
            row = [r]
            for s in strategies:
                c = cells.get(r, {}).get(s, {})
                row.append(c.get("missing_score_reason") or "")
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
                "scored",
                "score_present",
                "failure_category",
                "missing_score_reason",
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
                        c.get("scored"),
                        c.get("score_present"),
                        c.get("failure_category"),
                        c.get("missing_score_reason"),
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
        "--input-dir",
        dest="runs_dir",
        default="inputs/json",
        help="Directory containing run folders (each with run.json). Alias: --input-dir. Default: inputs/json",
    )
    p.add_argument(
        "--runs",
        default="all",
        help="Comma-separated run folder names (e.g. run_001,run_003) or 'all'. Default: all",
    )
    p.add_argument(
        "--strategies",
        default="all",
        help="Comma-separated strategy names or 'all'. Default 'all' runs the four "
        "JSON_IR strategies (direct/le × translate/no_translate). Choices: "
        + ", ".join(STRATEGY_CHOICES),
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Report folder (default: results/reports/evaluation_<timestamp>)",
    )
    p.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Optional config profile JSON merged on top of config/default.json and "
        "config/local.json (e.g. config/ablation_balanced.json). When omitted, uses "
        "default + local only (ignores any stale PIPELINE_CONFIG_PROFILE in the shell).",
    )
    p.add_argument(
        "--ignore-local-config",
        action="store_true",
        help="Skip config/local.json (default + --config profile + env only). "
        "Recommended for reproducible ablations.",
    )
    p.add_argument(
        "--no-translate",
        action="store_true",
        help="Force skip translation for every cell (overrides per-strategy translate defaults). "
        "Without this flag, each strategy uses its own translate setting.",
    )
    p.add_argument("--clean", action="store_true", help="Remove output-dir if it exists before run")
    p.add_argument(
        "--fail-on-missing-score",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit non-zero if any cell has exit 0 but no valid score.json (default: true).",
    )
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
    p.add_argument(
        "--max-llm-calls",
        type=int,
        default=None,
        metavar="N",
        help="Stop evaluation after N total tracked OpenAI calls (writes partial reports).",
    )
    p.add_argument(
        "--max-llm-calls-per-cell",
        type=int,
        default=None,
        metavar="N",
        help="Stop a cell with failure_category=llm_budget_guard after N OpenAI calls in that cell.",
    )
    args = p.parse_args()

    from pipeline.config import configure_runtime, get_active_config_profile

    try:
        active_profile = configure_runtime(
            args.config,
            ignore_local_config=bool(args.ignore_local_config),
        )
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
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

    enable_eval_tracking(force=True)
    clear_session_records()
    reset_eval_llm_counter()
    set_budget_limits(
        max_eval_calls=args.max_llm_calls,
        max_cell_calls=args.max_llm_calls_per_cell,
    )
    set_eval_report_dir(out)

    run_ids = [p.name for p in run_paths]
    cells: dict[str, dict[str, dict]] = {rid: {} for rid in run_ids}
    strategy_definitions = {
        s: strategy_metadata_for_eval(
            s,
            belief_scoring=args.belief_scoring,
            cli_no_translate=args.no_translate,
        )
        for s in strategies
    }

    print("Runs directory:", runs_dir)
    print("Runs:", ", ".join(run_ids))
    print("Strategies:", ", ".join(strategies))
    print("Pipeline: json_ir")
    if active_profile:
        print("Config profile:", active_profile)
    else:
        print("Config profile: (none)")
    if args.ignore_local_config:
        print("Local config: ignored (default + profile + env)")
    else:
        print("Local config: config/local.json merged when present")
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
    if args.max_llm_calls is not None and args.max_llm_calls < 1:
        print("--max-llm-calls must be >= 1", file=sys.stderr)
        return 1
    if args.max_llm_calls_per_cell is not None and args.max_llm_calls_per_cell < 1:
        print("--max-llm-calls-per-cell must be >= 1", file=sys.stderr)
        return 1
    eval_llm_calls_before = 0
    try:
        for src in run_paths:
            rid = src.name
            for strategy in strategies:
                wdir = work_root / work_dir_name(src, strategy)
                print("===", rid, "+", strategy, "->", wdir.name, "===")
                cell_t0 = time.perf_counter()
                if wdir.exists():
                    shutil.rmtree(wdir)
                copy_run_json(src, wdir)
                reset_cell_call_count()
                set_run_context(run_id=rid, strategy=strategy, artifact_dir=wdir)
                cell_meta = strategy_metadata_for_eval(
                    strategy,
                    belief_scoring=args.belief_scoring,
                    cli_no_translate=args.no_translate,
                )
                if (
                    args.max_llm_calls is not None
                    and eval_llm_calls_before >= args.max_llm_calls
                ):
                    stop_reason = "max_llm_calls (%s)" % args.max_llm_calls
                    print(
                        "[eval] stopping: eval LLM budget already at %s/%s"
                        % (eval_llm_calls_before, args.max_llm_calls),
                        file=sys.stderr,
                    )
                    break

                code = run_main_json(
                    wdir,
                    strategy,
                    cli_no_translate=args.no_translate,
                    belief_scoring=args.belief_scoring,
                    config_profile=str(active_profile) if active_profile else None,
                    ignore_local_config=bool(args.ignore_local_config),
                    llm_call_tracking=True,
                    max_llm_calls=args.max_llm_calls,
                    max_llm_calls_per_cell=args.max_llm_calls_per_cell,
                    llm_eval_calls_before=eval_llm_calls_before,
                )

                duration_sec = round(time.perf_counter() - cell_t0, 2)
                write_cell_summary(wdir)
                eval_llm_calls_before = count_eval_llm_calls(work_root)
                cell = build_eval_cell(
                    wdir,
                    code,
                    path=str(wdir),
                    duration_sec=duration_sec,
                    strategy_metadata=cell_meta,
                )
                cells[rid][strategy] = cell
                failure_category = cell.get("failure_category") or "unknown"
                cell_ok = bool(cell.get("ok"))
                if not cell_ok:
                    exit_ok = False
                sc = read_score(wdir / "score.json") if cell.get("score_present") else None
                if is_eval_pipeline_failure(
                    exit_code=code,
                    failure_category=failure_category,
                    score=sc,
                ):
                    pipeline_failure_count += 1
                if (
                    args.fail_on_missing_score
                    and code == 0
                    and not cell.get("scored")
                ):
                    exit_ok = False

                status_label = failure_category
                print(
                    "[eval] %s — %s (llm_calls=%s)"
                    % (_format_duration(duration_sec), status_label, eval_llm_calls_before)
                )
                guard = read_llm_budget_guard(wdir)
                if guard and guard.get("scope") == "eval":
                    stop_reason = "max_llm_calls (%s)" % guard.get("limit")
                    break
                if (
                    args.max_llm_calls is not None
                    and eval_llm_calls_before >= args.max_llm_calls
                ):
                    stop_reason = "max_llm_calls (%s)" % args.max_llm_calls
                    break
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
        status_summary = summarize_matrix_status(cells, run_ids, strategies)
        llm_cli = _llm_eval_cli_fields()
        llm_summary = write_eval_summary(out, work_root=work_root)
        status_summary["llm_eval_call_count"] = count_eval_llm_calls(work_root)
        if llm_summary:
            status_summary["llm_estimated_total_cost_usd"] = llm_summary.get(
                "estimated_total_cost_usd"
            )
        matrix = {
            "generated_at": stamp,
            "runs_dir": str(runs_dir),
            "strategies": strategies,
            "runs": run_ids,
            "cells": cells,
            "status_summary": status_summary,
            "run_finished": run_finished,
            "timing": timing_summary,
            "evaluation_cli": {
                "pipeline_backend": "json_ir",
                "provider": llm_cli.get("provider"),
                "model": llm_cli.get("model"),
                "base_url_host": llm_cli.get("base_url_host"),
                "config_profile": str(active_profile) if active_profile else None,
                "ignore_local_config": bool(args.ignore_local_config),
                "no_translate_global": args.no_translate,
                "belief_scoring": bool(args.belief_scoring),
                "max_failures": max_failures,
                "fail_on_missing_score": bool(args.fail_on_missing_score),
                "max_llm_calls": args.max_llm_calls,
                "max_llm_calls_per_cell": args.max_llm_calls_per_cell,
            },
            "llm_call_summary": llm_summary,
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
            try:
                _eg_path = Path(__file__).resolve().parent / "eval_grouped_metrics.py"
                _eg_spec = importlib.util.spec_from_file_location("eval_grouped_metrics", _eg_path)
                eval_grouped = importlib.util.module_from_spec(_eg_spec)
                assert _eg_spec.loader is not None
                _eg_spec.loader.exec_module(eval_grouped)
                manifest = eval_grouped.load_test_set_manifest(runs_dir)
                grouped = eval_grouped.compute_grouped_metrics(matrix, manifest)
                matrix["grouped_metrics"] = grouped
                (out / "grouped_summary.json").write_text(
                    json.dumps(grouped, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )
                grouped_md = eval_grouped.format_grouped_report_md(grouped)
                report_md = (out / "report.md").read_text(encoding="utf-8")
                (out / "report.md").write_text(
                    report_md.rstrip() + "\n\n" + grouped_md + "\n",
                    encoding="utf-8",
                )
                print("Wrote:", out / "grouped_summary.json")
            except Exception as eg_err:
                print("Note: grouped metrics skipped:", eg_err, file=sys.stderr)
        except OSError as e:
            print("Failed to write evaluation reports:", e, file=sys.stderr)

    if stop_reason or not run_finished:
        return 1
    return 0 if exit_ok else 1


if __name__ == "__main__":
    sys.exit(main())
