#!/usr/bin/env python3
"""Build symbolic_proof_gap.json from an existing results.json artifact."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pipeline.diagnostics.symbolic_proof_gap import (
    build_from_results_json,
    save_symbolic_proof_gap_report,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Build symbolic proof-gap diagnostic artifact.")
    p.add_argument(
        "results_json",
        help="Path to results.json (e.g. eval work dir results.json)",
    )
    p.add_argument(
        "--question-index",
        type=int,
        default=0,
        help="Question index inside results.json (default: 0)",
    )
    p.add_argument(
        "--output-dir",
        default=None,
        help="Directory for symbolic_proof_gap.json (default: same dir as results.json)",
    )
    args = p.parse_args()

    results_path = Path(args.results_json).resolve()
    if not results_path.is_file():
        print("results.json not found:", results_path, file=sys.stderr)
        return 1

    report = build_from_results_json(str(results_path), question_index=args.question_index)
    out_dir = args.output_dir or str(results_path.parent)
    path = save_symbolic_proof_gap_report(out_dir, report)
    print("Wrote:", path)
    print("Primary classification:", report.get("classification", {}).get("primary"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
