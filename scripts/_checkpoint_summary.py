#!/usr/bin/env python
"""Summarize checkpoint evaluation matrix for agent/user review."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "reports" / "evaluation_checkpoint_direct_json_ir_after_repairs"


def _load_matrix() -> dict:
    p = OUT / "matrix.json"
    if not p.is_file():
        raise SystemExit("matrix.json not found at %s" % p)
    return json.loads(p.read_text(encoding="utf-8"))


def _repair_info(work_rel: str | None) -> dict:
    if not work_rel:
        return {}
    rh = OUT / work_rel / "json_ir_compile" / "repair_summary.json"
    if not rh.is_file():
        return {}
    try:
        return json.loads(rh.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _symbols_check(work_rel: str | None, run_id: str) -> dict:
    out: dict = {}
    if not work_rel:
        return out
    base = OUT / work_rel / "json_ir_compile"
    if not base.is_dir():
        return out
    versions = sorted(base.glob("symbol_v*/symbols.normalized.json"), reverse=True)
    if not versions:
        return out
    try:
        st = json.loads(versions[0].read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return out
    preds = {p.get("name"): p for p in (st.get("predicates") or []) if isinstance(p, dict)}
    if run_id == "run_005":
        for name, p in preds.items():
            if name and "definition" in (name or "").lower():
                out["run_005_predicate"] = {"name": name, "kind": p.get("kind")}
    if run_id in ("run_119", "run_120"):
        legal = [
            {
                "name": p.get("name"),
                "kind": p.get("kind"),
                "legal_output": p.get("legal_output"),
            }
            for p in preds.values()
            if p.get("legal_output") or (
                p.get("kind") == "derived"
                and any(
                    x in (p.get("name") or "").lower()
                    for x in ("consequence", "effect", "apply", "timing")
                )
            )
        ]
        out["legal_effect_predicates"] = legal[:6]
    if run_id == "run_110":
        status_types = [
            t.get("name")
            for t in (st.get("types") or [])
            if isinstance(t, dict) and "status" in (t.get("name") or "").lower()
        ]
        out["status_like_types"] = status_types
    if run_id == "run_006":
        temporal = [
            f.get("name")
            for f in (st.get("functions") or [])
            if isinstance(f, dict)
            and any(
                x in (f.get("name") or "").lower()
                for x in ("prior", "previous", "following", "next")
            )
        ]
        out["temporal_functions"] = temporal
    return out


def main() -> int:
    m = _load_matrix()
    runs = m.get("runs") or []
    strategies = m.get("strategies") or []
    cells = m.get("cells") or {}

    print("=== MATRIX (compile | score | epistemic) ===\n")
    header = "%-12s" % "run/strategy" + "".join("%-28s" % s[:26] for s in strategies)
    print(header)
    for run in runs:
        row = "%-12s" % run
        for strat in strategies:
            c = cells.get("%s|%s" % (run, strat)) or {}
            comp = "OK" if c.get("compile_ok") else "FAIL"
            score = c.get("score")
            score_s = "" if score is None else "%.2f" % float(score)
            ep = c.get("epistemic_label") or c.get("label") or ""
            row += "%-28s" % ("%s|%s|%s" % (comp, score_s, ep)[:26])
        print(row)

    print("\n=== FAILURES ===\n")
    fail_cats: Counter[str] = Counter()
    for run in runs:
        for strat in strategies:
            key = "%s|%s" % (run, strat)
            c = cells.get(key) or {}
            if c.get("compile_ok"):
                continue
            fc = c.get("failure_category") or classify_failure_local(c)
            fail_cats[fc] += 1
            rs = _repair_info(c.get("work_dir"))
            print(
                "%s / %s: category=%s final_error=%s route=%s llm=%s"
                % (
                    run,
                    strat,
                    fc,
                    rs.get("final_normalized_error_code") or c.get("failure_detail", "")[:60],
                    ",".join(rs.get("repair_layers_used") or [])[:80] or "?",
                    rs.get("total_kb_llm_calls", "?"),
                )
            )

    print("\n=== WRONG / INCONCLUSIVE (compiled) ===\n")
    for run in runs:
        for strat in strategies:
            c = cells.get("%s|%s" % (run, strat)) or {}
            if not c.get("compile_ok"):
                continue
            score = c.get("score")
            if score is None:
                continue
            if float(score) >= 0.999:
                continue
            q = c.get("query_targets") or {}
            print("%s / %s: score=%.3f items=%s" % (run, strat, float(score), json.dumps(q)[:200]))

    print("\n=== SPECIFIC CHECKS ===\n")
    for run_check in ("run_009", "run_117", "run_006", "run_005", "run_110", "run_119", "run_120"):
        print("--- %s ---" % run_check)
        for strat in strategies:
            c = cells.get("%s|%s" % (run_check, strat)) or {}
            if not c.get("compile_ok"):
                rs = _repair_info(c.get("work_dir"))
                ev = OUT / (c.get("work_dir") or "") / "json_ir_compile"
                ve_path = None
                if ev.is_dir():
                    for p in sorted(ev.rglob("validation_evidence.json"), reverse=True):
                        ve_path = p
                        break
                ve_snip = ""
                if ve_path and ve_path.is_file():
                    try:
                        ve = json.loads(ve_path.read_text(encoding="utf-8"))
                        mh = ve.get("missing_helper") or {}
                        ve_snip = " helper=%s temporal=%s" % (
                            mh.get("helper_kind_hint"),
                            mh.get("missing_temporal_support_symbol"),
                        )
                    except (json.JSONDecodeError, OSError):
                        pass
                print(
                    "  %s: FAIL err=%s%s"
                    % (
                        strat,
                        rs.get("final_normalized_error_code", "?"),
                        ve_snip,
                    )
                )
            else:
                sc = c.get("score")
                ep = c.get("epistemic_label") or ""
                items = (c.get("score_detail") or {}).get("items") or []
                decisive_false = [
                    it
                    for it in items
                    if it.get("expected") is False and it.get("decisive") is True
                ]
                print(
                    "  %s: score=%.3f epistemic=%s decisive_false=%d"
                    % (strat, float(sc or 0), ep, len(decisive_false))
                )
        extra = _symbols_check(
            (cells.get("%s|%s" % (run_check, strategies[0])) or {}).get("work_dir"),
            run_check,
        )
        if extra:
            print("  artifacts: %s" % json.dumps(extra)[:300])

    meta = m.get("meta") or {}
    print("\n=== RUNTIME ===\n")
    print("total_seconds: %s" % meta.get("total_duration_seconds"))
    print("cells: %s" % len(cells))
    timings = OUT / "timings.csv"
    if timings.is_file():
        lines = timings.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) > 1:
            total = sum(float(l.split(",")[-1]) for l in lines[1:] if l.split(",")[-1])
            print("timings.csv sum: %.1fs" % total)

    print("\n=== TOP FAILURE CATEGORIES ===\n")
    for cat, n in fail_cats.most_common(5):
        print("  %d  %s" % (n, cat))
    return 0


def classify_failure_local(c: dict) -> str:
    fd = (c.get("failure_detail") or "").lower()
    if "law compilation" in fd or "json ir compilation" in fd:
        return "law_compilation"
    if "query" in fd and "extract" in fd:
        return "query_extraction"
    if "case" in fd and "extract" in fd:
        return "case_extraction"
    return c.get("failure_category") or "other"


if __name__ == "__main__":
    sys.exit(main())
