#!/usr/bin/env python3
"""
Emit a single text digest for JSON benchmark runs (default: run_101..run_120).

Usage (from project root):
  python scripts/generate_runs_digest.py
  python scripts/generate_runs_digest.py --from 101 --to 120 --out results/reports/my_digest.txt
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _trunc(s: str | None, n: int) -> str:
    if not s:
        return ""
    s = str(s).replace("\r\n", "\n").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def _find_kb_compile_logs(run_dir: Path) -> list[Path]:
    if not run_dir.is_dir():
        return []
    return sorted(run_dir.rglob("kb_compile.log"), key=lambda p: p.stat().st_mtime, reverse=True)


def _parse_kb_log_fail(log_text: str) -> tuple[str, str]:
    """Return (short_error, last_kb_snippet)."""
    err = ""
    m = re.search(r"Error:\s*\n?(.*?)(?:\n\n===|\Z)", log_text, re.DOTALL)
    if m:
        err = m.group(1).strip()
    kb = ""
    if "=== LAST RAW KB ===" in log_text:
        kb = log_text.split("=== LAST RAW KB ===", 1)[1].strip()
    return err, kb


def _digest_one_run(run_dir: Path, out_lines: list[str], *, kb_kb_max: int) -> None:
    rid = run_dir.name
    out_lines.append("")
    out_lines.append("=" * 72)
    out_lines.append(f" {rid}")
    out_lines.append("=" * 72)

    run_json_path = run_dir / "run.json"
    if not run_json_path.is_file():
        out_lines.append("  (missing run.json)")
        return

    run_obj = json.loads(run_json_path.read_text(encoding="utf-8"))
    law = run_obj.get("law") or {}
    law_path = law.get("path") or ""
    case_text = (run_obj.get("case") or {}).get("text") or ""
    strat = run_obj.get("kb_compile_strategy")
    flags = run_obj.get("kb_compile_flags")
    out_lines.append(f"  law_path: {law_path}")
    out_lines.append(f"  kb_compile_strategy: {strat}")
    out_lines.append(f"  kb_compile_flags: {flags}")
    out_lines.append(f"  pipeline_backend_mode: {run_obj.get('pipeline_backend_mode')}")
    out_lines.append(f"  case (trunc): {_trunc(case_text, 500)}")

    qs = run_obj.get("questions") or []
    for j, q in enumerate(qs):
        if not isinstance(q, dict):
            continue
        out_lines.append(f"  question[{j}] id={q.get('id')!r}: {_trunc(q.get('text'), 400)}")
        exp = q.get("expected")
        if exp:
            out_lines.append(f"    expected: {json.dumps(exp, ensure_ascii=False)}")

    logs = _find_kb_compile_logs(run_dir)
    kb_fail = False
    if logs:
        log_path = logs[0]
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
        rel = log_path.relative_to(_ROOT)
        out_lines.append(f"  kb_compile.log (newest): {rel}")
        if "KB compilation FAILED" in log_text or "compilation failed" in log_text.lower():
            kb_fail = True
            err, kb = _parse_kb_log_fail(log_text)
            out_lines.append("  OUTCOME: KB_COMPILE_FAILED")
            out_lines.append(f"  kb_error: {err}")
            if kb:
                out_lines.append(f"  last_kb_fo (max {kb_kb_max} chars):")
                out_lines.append(_trunc(kb, kb_kb_max))
        elif "Compilation successful" in log_text or "successful" in log_text.lower():
            out_lines.append("  kb_compile.log indicates: KB compilation reached success at least once")
        else:
            out_lines.append(f"  kb_compile.log (first 400 chars): {_trunc(log_text, 400)}")

    results_path = run_dir / "results.json"
    if results_path.is_file():
        res = json.loads(results_path.read_text(encoding="utf-8"))
        out_lines.append(f"  results.json: present ({results_path.stat().st_size} bytes)")
        score_path = run_dir / "score.json"
        if score_path.is_file():
            sc = json.loads(score_path.read_text(encoding="utf-8"))
            out_lines.append(
                "  score.json: total=%s correct=%s accuracy=%s"
                % (sc.get("total"), sc.get("correct"), sc.get("accuracy"))
            )
        for j, q in enumerate(res.get("questions") or []):
            if not isinstance(q, dict):
                continue
            pipe = q.get("pipeline")
            if not isinstance(pipe, dict):
                continue
            est = q.get("expected")
            err_st = pipe.get("error_stage")
            err = pipe.get("error")
            sat = pipe.get("sat")
            pred = pipe.get("prediction")
            nl = pipe.get("natural_language")
            if err_st or err:
                out_lines.append(f"  pipeline[{j}]: error_stage={err_st!r}")
                out_lines.append(f"    error: {_trunc(str(err), 800)}")
            else:
                out_lines.append(f"  pipeline[{j}]: error_stage=null (no pipeline error field)")
            out_lines.append(f"    sat={sat!r} prediction={json.dumps(pred, ensure_ascii=False) if pred else pred!r}")
            out_lines.append(f"    natural_language (trunc): {_trunc(str(nl), 300)}")
            if est and pred:
                out_lines.append(f"    expected_for_compare: {json.dumps(est, ensure_ascii=False)}")
        if not kb_fail:
            # Classify for summary line
            any_err = False
            for q in res.get("questions") or []:
                pipe = (q or {}).get("pipeline") or {}
                if pipe.get("error_stage") or pipe.get("error"):
                    any_err = True
                    break
            if any_err:
                out_lines.append("  OUTCOME (overall): PIPELINE_COMPLETED_WITH_STAGE_ERROR")
            else:
                out_lines.append("  OUTCOME (overall): PIPELINE_COMPLETED")
    else:
        out_lines.append("  results.json: MISSING (run likely aborted before write)")
        if kb_fail:
            out_lines.append("  OUTCOME (overall): KB_COMPILE_FAILED (no results)")
        else:
            out_lines.append("  OUTCOME (overall): UNKNOWN / INCOMPLETE")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--from", dest="from_id", type=int, default=101)
    p.add_argument("--to", dest="to_id", type=int, default=120)
    p.add_argument(
        "--out",
        type=Path,
        default=_ROOT / "results" / "reports" / "json_runs_101_120_digest.txt",
    )
    p.add_argument("--kb-snippet-max", type=int, default=4000, help="Max chars of LAST RAW KB per failed run")
    args = p.parse_args()

    runs_dir = _ROOT / "inputs" / "json"
    out_path = args.out
    if not out_path.is_absolute():
        out_path = (_ROOT / out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("Legal-pipeline — JSON-IR batch digest")
    lines.append("Generated (UTC): " + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    lines.append("Project root: " + str(_ROOT))
    lines.append("")
    lines.append("Purpose: summarize run.json + kb_compile.log + results.json/score.json per run")
    lines.append("for debugging KB compilation, repair loops, extraction, and symbolic reasoning.")
    lines.append("")
    lines.append("Batch context (from prior full batch):")
    lines.append("  Exit 0 (full process completed): run_103, run_105, run_113, run_117, run_119, run_120")
    lines.append("  Non-zero exit (typically KBCacheError after repairs): run_101, run_102, run_104,")
    lines.append("    run_106, run_107, run_108, run_109, run_110, run_111, run_112, run_114, run_115,")
    lines.append("    run_116, run_118")
    lines.append("")
    lines.append("Note: exit 0 does not mean legally correct answers — check pipeline.error_stage.")

    for i in range(args.from_id, args.to_id + 1):
        run_dir = runs_dir / f"run_{i}"
        _digest_one_run(run_dir, lines, kb_kb_max=args.kb_snippet_max)

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote:", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
