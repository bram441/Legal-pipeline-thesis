#!/usr/bin/env python3
"""Re-run cells that failed KB compile in evaluation_20260514T083545Z (clears KB cache first)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# From rerun_failures_console.log SUMMARY (exit 1) + run_003 le_single (IDP fy1)
CELLS: list[tuple[str, str]] = [
    ("run_003", "le_single"),
    ("run_006", "le_single"),
    ("run_006", "le_two_phase"),
    ("run_009", "le_two_phase"),
    ("run_102", "direct_two_phase"),
    ("run_105", "le_two_phase"),
    ("run_113", "le_two_phase"),
    ("run_114", "le_two_phase"),
    ("run_115", "le_single"),
    ("run_117", "le_two_phase"),
]

EVAL_DIR = _ROOT / "results" / "reports" / "evaluation_20260514T083545Z"
WORK = EVAL_DIR / "work"


def _clear_kb_cache(wdir: Path) -> None:
    """Remove cached kb.fo under translated/json_ir[/le] so prompts trigger recompile."""
    for kb in wdir.rglob("kb.fo"):
        try:
            kb.unlink()
        except OSError:
            pass
    for schema in wdir.rglob("kb_schema.json"):
        try:
            schema.unlink()
        except OSError:
            pass
    for log in wdir.rglob("kb_compile.log"):
        try:
            log.unlink()
        except OSError:
            pass


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = EVAL_DIR / f"kb_regression_{stamp}.log"
    results: list[dict] = []

    print("KB compile regression:", len(CELLS), "cells")
    print("Log:", log_path)

    with log_path.open("w", encoding="utf-8") as logf:
        logf.write(f"cells={len(CELLS)}\n\n")

    exit_any = 0
    for run_id, strategy in CELLS:
        wname = f"{run_id}__{strategy}__json_ir"
        wdir = WORK / wname
        banner = f"\n{'=' * 72}\n{run_id} + {strategy} -> {wdir}\n{'=' * 72}\n"
        print(banner, flush=True)

        if not wdir.is_dir():
            print("MISSING", wdir, file=sys.stderr)
            exit_any = 1
            results.append({"run": run_id, "strategy": strategy, "exit": 999, "note": "missing_dir"})
            continue

        _clear_kb_cache(wdir)
        cmd = [
            sys.executable,
            "-u",
            str(_ROOT / "main.py"),
            "--mode",
            "json",
            "--pipeline-backend",
            "json_ir",
            "--run",
            str(wdir),
            "--kb-strategy",
            strategy,
        ]
        p = subprocess.run(
            cmd,
            cwd=str(_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        out = p.stdout or ""
        with log_path.open("a", encoding="utf-8") as logf:
            logf.write(banner)
            logf.write(subprocess.list2cmdline(cmd) + "\n")
            logf.write(out)
            logf.write(f"\n--- exit {p.returncode} ---\n")

        try:
            print(out, end="", flush=True)
        except UnicodeEncodeError:
            print(out.encode("utf-8", errors="replace").decode("utf-8", errors="replace"), end="", flush=True)
        print(f"--- exit {p.returncode} ---", flush=True)

        kb_ok = "Compilation successful" in out or "Loading from cache" in out
        if "KB compilation failed" in out or "Law compilation failed" in out:
            kb_ok = False
        results.append(
            {
                "run": run_id,
                "strategy": strategy,
                "exit": p.returncode,
                "kb_compile_ok": kb_ok,
            }
        )
        if p.returncode != 0:
            exit_any = 1

    summary_path = EVAL_DIR / f"kb_regression_{stamp}.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\nSUMMARY")
    for r in results:
        print(
            f"  {r['run']}\t{r['strategy']}\texit={r['exit']}\tkb_ok={r.get('kb_compile_ok')}"
        )
    print("Wrote", summary_path)
    print("Wrote", log_path)
    return exit_any


if __name__ == "__main__":
    raise SystemExit(main())
