#!/usr/bin/env python
"""
Remove generated artifacts from inputs/json/run_* folders, keeping run.json.

Usage (from project root):
  python scripts/clean_generated_artifacts.py
  python scripts/clean_generated_artifacts.py --dry-run
  python scripts/clean_generated_artifacts.py --runs-dir inputs/json
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

# Paths relative to each run folder (files or directories).
_ARTIFACT_NAMES = (
    "results.json",
    "score.json",
    "run_trace.txt",
    "kb.fo",
    "kb_schema.json",
    "kb_compile.log",
    "translated",
    "json_ir_compile",
    "json_ir",
    "kb_strategy_compare",
    "reports",
    "compare_summary.json",
    "_expected_templates_run_002_009.json",
)


def clean_run_dir(run_dir: Path, *, dry_run: bool) -> list[str]:
    removed: list[str] = []
    for name in _ARTIFACT_NAMES:
        p = run_dir / name
        if not p.exists():
            continue
        removed.append(str(p.relative_to(run_dir)))
        if not dry_run:
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
    return removed


def main() -> int:
    p = argparse.ArgumentParser(description="Clean generated artifacts from JSON run folders.")
    p.add_argument("--runs-dir", default="inputs/json")
    p.add_argument("--dry-run", action="store_true", help="List what would be removed")
    args = p.parse_args()

    runs_dir = Path(args.runs_dir)
    if not runs_dir.is_absolute():
        runs_dir = _ROOT / runs_dir

    if not runs_dir.is_dir():
        print("Runs directory not found:", runs_dir)
        return 1

    total = 0
    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir() or not (run_dir / "run.json").is_file():
            continue
        removed = clean_run_dir(run_dir, dry_run=args.dry_run)
        if removed:
            print(run_dir.name + ":")
            for r in removed:
                print("  ", r)
            total += len(removed)

    action = "Would remove" if args.dry_run else "Removed"
    print(action, total, "artifact path(s) under", runs_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
