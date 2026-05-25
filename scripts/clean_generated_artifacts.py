#!/usr/bin/env python
"""
Remove generated artifacts from inputs/json and inputs/text run folders.

Keeps curated inputs (run.json, law/case text files, manifests).

Usage (from project root):
  python scripts/clean_generated_artifacts.py
  python scripts/clean_generated_artifacts.py --dry-run
  python scripts/clean_generated_artifacts.py --roots inputs/json,inputs/text
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
    "effective_config.json",
    "kb.fo",
    "kb_schema.json",
    "kb_compile.log",
    "cache_manifest.json",
    "translated",
    "json_ir_compile",
    "json_ir",
    "kb_strategy_compare",
    "reports",
    "compare_summary.json",
    "case_extraction_repair.json",
    "schema_environment.json",
    "case_entity_type_mapping.json",
    "pre_solver_domain_validation.json",
    "case_factual_input_diagnostics.json",
    "symbolic_proof_gap.json",
    "_expected_templates_run_002_009.json",
)

# Nested under translated/ or json_ir_compile/
_NESTED_ARTIFACT_GLOBS = (
    "translated/**/kb.fo",
    "translated/**/kb_schema.json",
    "translated/**/kb_compile.log",
)


def _is_run_dir(path: Path) -> bool:
    return path.is_dir() and (path / "run.json").is_file()


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
    for pattern in _NESTED_ARTIFACT_GLOBS:
        for p in run_dir.glob(pattern):
            if not p.exists():
                continue
            rel = str(p.relative_to(run_dir))
            if rel in removed:
                continue
            removed.append(rel)
            if not dry_run:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
    return removed


def clean_roots(roots: list[Path], *, dry_run: bool) -> int:
    total = 0
    for root in roots:
        if not root.is_dir():
            print("Skip missing root:", root)
            continue
        for run_dir in sorted(root.iterdir()):
            if not _is_run_dir(run_dir):
                continue
            removed = clean_run_dir(run_dir, dry_run=dry_run)
            if removed:
                print(run_dir.name + ":")
                for r in removed:
                    print("  ", r)
                total += len(removed)
    return total


def main() -> int:
    p = argparse.ArgumentParser(description="Clean generated artifacts from benchmark run folders.")
    p.add_argument(
        "--roots",
        default="inputs/json,inputs/text",
        help="Comma-separated roots containing run_* folders (default: inputs/json,inputs/text)",
    )
    p.add_argument("--dry-run", action="store_true", help="List what would be removed")
    args = p.parse_args()

    roots = []
    for part in str(args.roots).split(","):
        part = part.strip()
        if not part:
            continue
        path = Path(part)
        if not path.is_absolute():
            path = _ROOT / path
        roots.append(path)

    total = clean_roots(roots, dry_run=args.dry_run)
    action = "Would remove" if args.dry_run else "Removed"
    print(action, total, "artifact path(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
