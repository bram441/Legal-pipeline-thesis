#!/usr/bin/env python
"""Summarize post-Iteration-6 smoke evaluation work dirs."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

TARGET_RUNS = ("run_006", "run_009", "run_110", "run_117", "run_119", "run_120")
TARGET_STRATEGIES = ("direct_json_ir_translate", "direct_json_ir_no_translate")


def _read_json(p: Path) -> dict | None:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _find_repair_history(work: Path) -> Path | None:
    for p in work.rglob("repair_history.json"):
        return p
    return None


def _find_combined_ir(work: Path) -> Path | None:
    for p in sorted(work.rglob("combined_ir.json")):
        return p
    return None


def _effect_preds(preds: list) -> list[str]:
    from pipeline.kb.legal_effect import predicate_represents_legal_effect_output

    out = []
    for p in preds:
        if not isinstance(p, dict):
            continue
        if predicate_represents_legal_effect_output(
            str(p.get("name") or ""),
            description=str(p.get("description") or ""),
            kind=str(p.get("kind") or ""),
            legal_output=p.get("legal_output") if isinstance(p.get("legal_output"), bool) else None,
            output_category=str(p.get("output_category") or ""),
        ):
            out.append(str(p["name"]))
    return out


def _status_as_type_in_ir(preds: list, types: list) -> bool:
    from pipeline.kb.status_as_type import names_semantically_identical

    type_set = set()
    for t in types or []:
        if isinstance(t, dict):
            type_set.add(str(t.get("name") or ""))
        else:
            type_set.add(str(t))
    for p in preds or []:
        if str(p.get("kind") or "").lower() not in {"derived", "conclusion"}:
            continue
        name = str(p.get("name") or "")
        if not name.startswith("is_"):
            continue
        args = p.get("args") or []
        if len(args) == 1 and args[0] in type_set and names_semantically_identical(str(args[0]), name):
            return True
    return False


def _outer_cache_kb_attempts(work: Path) -> int:
    trace = work / "run_trace.txt"
    if not trace.is_file():
        return 0
    t = trace.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"KB COMPILATION - Attempt \d+", t, re.I))


def _inner_llm_calls_from_trace(work: Path) -> int:
    trace = work / "run_trace.txt"
    if not trace.is_file():
        return 0
    t = trace.read_text(encoding="utf-8", errors="replace")
    sym = len(re.findall(r"\[KB\]\s+Generating from law text", t, re.I))
    rep = len(re.findall(r"\[KB\]\s+Repair attempt \d+", t, re.I))
    # Repair attempt logs are outer cache; inner is in repair_history
    return sym + rep


def _analyze_cell(work: Path) -> dict:
    hist_path = _find_repair_history(work)
    hist = _read_json(hist_path) if hist_path else None
    summary = (hist or {}).get("summary") or _read_json(work / "json_ir_compile" / "repair_summary.json")
    if summary is None and hist_path:
        summary = _read_json(hist_path.parent / "repair_summary.json")

    score = _read_json(work / "score.json")
    combined = _find_combined_ir(work)
    ir = _read_json(combined) if combined else None
    preds = list((ir or {}).get("predicates") or [])
    types = list((ir or {}).get("types") or [])

    items = []
    for it in (score or {}).get("items") or []:
        items.append(
            {
                "id": it.get("id"),
                "query_predicate": it.get("query_predicate"),
                "query_predicate_kind": it.get("query_predicate_kind"),
                "symbolic_status": it.get("symbolic_status"),
                "epistemic_label": it.get("epistemic_label"),
                "gold": it.get("gold"),
                "score": it.get("score"),
            }
        )

    routes = []
    if hist:
        for ev in hist.get("events") or []:
            r = ev.get("repair_route")
            if r and r not in routes:
                routes.append(r)

    blob = ""
    rt = work / "run_trace.txt"
    if rt.is_file():
        blob = rt.read_text(encoding="utf-8", errors="replace")[-8000:]

    compile_ok = "compilation successful" in blob.lower() and "kb compilation failed" not in blob.lower()

    return {
        "work_dir": str(work),
        "compile_ok": compile_ok,
        "score": {
            "accuracy_decisive": score.get("accuracy_decisive") if score else None,
            "correct_decisive": score.get("correct_decisive") if score else None,
            "total": score.get("total") if score else None,
            "items": items,
        }
        if score
        else None,
        "repair_history_path": str(hist_path) if hist_path else None,
        "repair_summary": summary,
        "symbol_version_count": (summary or {}).get("symbol_version_count"),
        "rules_attempt_count": (summary or {}).get("rules_attempt_count"),
        "total_kb_llm_calls": (summary or {}).get("total_kb_llm_calls"),
        "repair_layers_used": (summary or {}).get("repair_layers_used") or routes,
        "final_normalized_error_code": (summary or {}).get("final_normalized_error_code"),
        "final_normalized_error_signature": (summary or {}).get("final_normalized_error_signature"),
        "repair_stalled": (summary or {}).get("repair_stalled"),
        "budget_exhausted": (summary or {}).get("budget_exhausted"),
        "effect_predicates_in_kb": _effect_preds(preds),
        "status_as_type_pattern": _status_as_type_in_ir(preds, types),
        "derived_names": [
            p.get("name")
            for p in preds
            if str(p.get("kind") or "").lower() in {"derived", "conclusion"}
        ],
        "outer_cache_kb_attempts": _outer_cache_kb_attempts(work),
        "combined_ir": str(combined) if combined else None,
    }


def main() -> int:
    eval_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if eval_dir is None:
        reports = _ROOT / "results" / "reports"
        candidates = sorted(reports.glob("evaluation_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        eval_dir = candidates[0] if candidates else None
    if eval_dir is None or not eval_dir.is_dir():
        print("No evaluation directory", file=sys.stderr)
        return 1

    work_root = eval_dir / "work"
    out: dict = {"eval_dir": str(eval_dir), "cells": {}}

    for run in TARGET_RUNS:
        for strat in TARGET_STRATEGIES:
            key = f"{run}__{strat}"
            matches = list(work_root.glob(f"{run}__{strat}__*"))
            if not matches:
                out["cells"][key] = {"error": "work dir not found"}
                continue
            out["cells"][key] = _analyze_cell(matches[0])

    out_path = eval_dir / "smoke_iteration6_analysis.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    # Markdown table
    lines = ["# Smoke Iteration 6 Summary", "", "| Run | Strategy | Compile | Score | SymV | RulesA | LLM | Routes | Final err | Hist |", "|---|---|---|---|---|---|---|---|---|---|"]
    for run in TARGET_RUNS:
        for strat in TARGET_STRATEGIES:
            c = out["cells"].get(f"{run}__{strat}") or {}
            sc = c.get("score") or {}
            acc = sc.get("accuracy_decisive") if sc else "—"
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                % (
                    run,
                    strat.replace("direct_json_ir_", ""),
                    "OK" if c.get("compile_ok") else "FAIL",
                    acc if acc is not None else "—",
                    c.get("symbol_version_count", "—"),
                    c.get("rules_attempt_count", "—"),
                    c.get("total_kb_llm_calls", "—"),
                    ",".join(c.get("repair_layers_used") or [])[:40] or "—",
                    (c.get("final_normalized_error_code") or "—")[:30],
                    "yes" if c.get("repair_history_path") else "no",
                )
            )
    (eval_dir / "smoke_iteration6_report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("\nWrote", out_path, "and smoke_iteration6_report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
