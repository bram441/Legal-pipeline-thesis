#!/usr/bin/env python
"""One-off analysis of evaluation work dirs (compile + score patterns)."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def norm_err(msg: str) -> str:
    msg = (msg or "").strip()
    if "incompatible unary subject roles" in msg:
        m = re.search(r"variable '([^']+)' combines", msg)
        roles = re.search(r"\(([^)]+)\)", msg)
        var = m.group(1) if m else "?"
        return f"ROLE_CONFLATION:{var}" + (f" ({roles.group(1)[:40]})" if roles else "")
    if "unbound identifier" in msg:
        m = re.search(r"unbound identifier '([^']+)'", msg)
        return "UNBOUND_ID:" + (m.group(1) if m else "?")
    if "unconstrained consequent variable" in msg:
        m = re.search(r"consequent variable '([^']+)'", msg)
        return "UNCONSTRAINED:" + (m.group(1) if m else "?")
    if "floating helper" in msg.lower():
        return "FLOATING_HELPER"
    if "JSON_IR_RULE_DESIGN_ERROR" in msg:
        return "RULE_DESIGN_OTHER"
    if "compilation failed" in msg.lower():
        lines = [ln.strip() for ln in msg.splitlines() if ln.strip() and not ln.startswith("---")]
        for ln in lines:
            if "rules[" in ln or "JSON_IR" in ln:
                return ln[:140]
        return lines[-1][:140] if lines else "COMPILE_FAILED"
    return msg[:100] if msg else "NO_LOG"


def read_last_error(wdir: Path) -> str:
    for rel in (
        "translated/json_ir/kb_compile.log",
        "json_ir_compile/attempt_02/validation_error.txt",
        "json_ir_compile/attempt_01/validation_error.txt",
    ):
        p = wdir / rel
        if p.is_file():
            return p.read_text(encoding="utf-8", errors="replace")
    rt = wdir / "run_trace.txt"
    if rt.is_file():
        t = rt.read_text(encoding="utf-8", errors="replace")
        for marker in ("--- LLM call failed", "LawCompilationError (json_ir"):
            idx = t.rfind(marker)
            if idx >= 0:
                return t[idx : idx + 2500]
        return t[-2500:]
    return ""


def read_score_issues(wdir: Path) -> list:
    sp = wdir / "score.json"
    if not sp.is_file():
        return []
    sc = json.loads(sp.read_text(encoding="utf-8"))
    issues = []
    for it in sc.get("items") or []:
        sym = it.get("symbolic_status")
        lab = it.get("epistemic_label")
        gold = it.get("gold")
        if sym == "error":
            issues.append(("symbolic_error", it.get("id"), it.get("symbolic_error", "")[:80]))
        elif lab == "unknown":
            issues.append(("inconclusive", it.get("id")))
        elif lab and gold and lab != gold:
            issues.append(("wrong_decisive", it.get("id"), lab, gold))
    return issues


def main() -> int:
    eval_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _ROOT / "results/reports/evaluation_20260516T084645Z"
    work = eval_dir / "work"
    matrix_path = eval_dir / "matrix.json"
    if matrix_path.is_file():
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
        print("stopped_early:", matrix.get("stopped_early"), matrix.get("stop_reason"))
        print("pipeline_failure_count:", matrix.get("pipeline_failure_count"))
        print()

    rows = []
    for wdir in sorted(work.glob("*__json_ir")):
        err_raw = read_last_error(wdir)
        bucket = norm_err(err_raw)
        issues = read_score_issues(wdir)
        rows.append((wdir.name, bucket, issues, err_raw))

    print("=== WORK DIRS:", len(rows), "===\n")
    compile_buckets = Counter()
    score_buckets = Counter()
    for name, bucket, issues, err_raw in rows:
        compile_buckets[bucket] += 1
        has_compile_fail = bucket not in ("NO_LOG",) and (
            bucket.startswith(("ROLE_", "UNBOUND", "UNCONSTRAINED", "FLOATING", "RULE_", "COMPILE", "JSON"))
            or "compilation failed" in err_raw.lower()
            or "rules[" in bucket
        )
        if not issues and not has_compile_fail:
            print(f"OK  {name}")
            continue
        print(f"--- {name} ---")
        print(f"  compile: {bucket}")
        if issues:
            for iss in issues:
                score_buckets[iss[0]] += 1
                print(f"  score: {iss}")
        if "spouse" in err_raw.lower():
            print("  (mentions 'spouse' in log)")

    print("\n=== COMPILE ERROR BUCKETS ===")
    for k, v in compile_buckets.most_common():
        print(f"  {v:3d}  {k}")
    print("\n=== SCORE ISSUE TYPES (completed cells) ===")
    for k, v in score_buckets.most_common():
        print(f"  {v:3d}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
