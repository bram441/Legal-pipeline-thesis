#!/usr/bin/env python
"""Write threshold_numeric_helper_gap.json from latest run KB artifacts (Task A)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.kb.threshold_numeric_helper_scaffold import build_threshold_numeric_helper_gap_report


def _latest_combined_ir(run_dir: Path) -> tuple[Path | None, dict | None]:
    candidates = sorted(
        run_dir.rglob("combined_ir.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for p in candidates:
        try:
            return p, json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return None, None


def _law_text(run_dir: Path) -> str:
    run_json = run_dir / "run.json"
    if not run_json.is_file():
        return ""
    try:
        meta = json.loads(run_json.read_text(encoding="utf-8"))
        law_path = meta.get("law", {}).get("path")
        if law_path:
            lp = _ROOT / law_path if not Path(law_path).is_absolute() else Path(law_path)
            if lp.is_file():
                return lp.read_text(encoding="utf-8")
    except (json.JSONDecodeError, OSError):
        pass
    return ""


def build_gap_for_run(run_dir: Path) -> dict:
    path, ir = _latest_combined_ir(run_dir)
    if not ir:
        return {"error": "no combined_ir.json found", "run_id": run_dir.name}
    symbol_table = {
        "types": ir.get("types") or [],
        "predicates": ir.get("predicates") or [],
        "functions": ir.get("functions") or [],
    }
    report = build_threshold_numeric_helper_gap_report(
        ir,
        symbol_table,
        law_text=_law_text(run_dir),
    )
    report["artifact_path"] = str(path) if path else None
    report["run_id"] = run_dir.name
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Build threshold_numeric_helper_gap.json for runs")
    p.add_argument("--runs", default="run_117", help="Comma-separated run folder names")
    p.add_argument("--runs-root", default="inputs/json")
    args = p.parse_args()
    root = _ROOT / args.runs_root
    for name in [x.strip() for x in args.runs.split(",") if x.strip()]:
        run_dir = root / name
        if not run_dir.is_dir():
            print("Skip missing:", run_dir, file=sys.stderr)
            continue
        gap = build_gap_for_run(run_dir)
        out = run_dir / "threshold_numeric_helper_gap.json"
        out.write_text(json.dumps(gap, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
