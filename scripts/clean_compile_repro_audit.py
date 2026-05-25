#!/usr/bin/env python
"""Clean-compile reproducibility audit for direct_json_ir_translate runs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_es_path = _ROOT / "scripts" / "clean_generated_artifacts.py"
_spec = importlib.util.spec_from_file_location("clean_generated_artifacts", _es_path)
_clean_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_clean_mod)


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _find_repair_history(run_dir: Path) -> Path | None:
    for rel in ("json_ir_compile/repair_history.json", "translated/json_ir/repair_history.json"):
        p = run_dir / rel
        if p.is_file():
            return p
    for p in run_dir.rglob("repair_history.json"):
        return p
    return None


def _compress_sequence(events: list[dict]) -> list[str]:
    out: list[str] = []
    last_key = None
    for ev in events:
        sv = ev.get("symbol_version") or 0
        ra = ev.get("rules_attempt") or 0
        code = ev.get("normalized_error_code") or ev.get("error_kind") or ""
        action = ev.get("action") or ev.get("phase") or ""
        status = ev.get("status") or ""
        card = ev.get("repair_card_id") or ""
        route = ev.get("repair_route") or ""
        if status in {"ok", "success"} and not code:
            continue
        key = (sv, ra, code, action, status)
        if key == last_key:
            continue
        last_key = key
        parts = [f"symbol_v{sv:02d}"]
        if ra:
            parts.append(f"rules_a{ra:02d}")
        if action:
            parts.append(str(action))
        if code:
            parts.append(str(code))
        elif status and status not in {"ok"}:
            parts.append(str(status))
        if card:
            parts.append(f"card={card}")
        if route:
            parts.append(f"route={route}")
        out.append(" ".join(parts))
    return out


def _repair_cards_used(events: list[dict]) -> list[str]:
    cards: list[str] = []
    for ev in events:
        c = ev.get("repair_card_id")
        if c and c not in cards:
            cards.append(str(c))
    return cards


def _classify_failure(summary: dict, events: list[dict], compile_ok: bool) -> str:
    if compile_ok:
        return "success"
    if summary.get("budget_exhausted"):
        return "total_llm_budget_exhausted"
    if summary.get("symbol_budget_exhausted"):
        return "symbol_budget_exhausted"
    if summary.get("repair_stalled"):
        return "repeated_error_stall"
    codes = [ev.get("normalized_error_code") for ev in events if ev.get("normalized_error_code")]
    if any(c in {"invalid_json", "json_parse_error"} for c in codes):
        return "invalid_json_or_schema"
    if summary.get("final_failure_category") == "validation_exhausted":
        return "non_repairable_validation_or_rule_budget"
    ra = summary.get("rules_attempt_count") or 0
    sv = summary.get("symbol_version_count") or 0
    if ra >= 3 and sv >= 3:
        return "rule_and_symbol_budget_exhausted"
    return str(summary.get("final_failure_category") or "unknown")


def _initial_symbols_audit(run_dir: Path) -> dict[str, Any]:
    from pipeline.kb.legal_effect import predicate_represents_legal_effect_output
    from pipeline.kb.status_as_type import names_semantically_identical

    sym_path = run_dir / "json_ir_compile" / "symbol_v01" / "symbols.normalized.json"
    if not sym_path.is_file():
        for p in sorted(run_dir.rglob("symbols.normalized.json")):
            if "symbol_v01" in str(p):
                sym_path = p
                break
    sym = _read_json(sym_path) or {}
    preds = list(sym.get("predicates") or [])
    types = list(sym.get("types") or [])
    type_names = {str(t.get("name") if isinstance(t, dict) else t) for t in types}

    effect_preds = []
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
            effect_preds.append(str(p["name"]))

    temporal_missing = False
    try:
        from pipeline.kb.temporal_support import assess_temporal_support

        run_json = _read_json(run_dir / "run.json") or {}
        law_path = run_json.get("law", {}).get("path")
        law_text = ""
        if law_path:
            lp = _ROOT / law_path if not Path(law_path).is_absolute() else Path(law_path)
            if lp.is_file():
                law_text = lp.read_text(encoding="utf-8")
        qtext = ""
        qs = run_json.get("questions") or []
        if qs:
            qtext = str(qs[0].get("text") or "")
        det = assess_temporal_support(
            sym,
            law_text=law_text,
            question_text=qtext,
        )
        temporal_missing = det.requires_temporal_support and not det.has_temporal_support_symbols
    except Exception as exc:
        temporal_missing = f"audit_error:{exc}"

    helpers_without_rules_hint = [
        str(p.get("name"))
        for p in preds
        if isinstance(p, dict)
        and str(p.get("kind") or "").lower() == "helper"
    ]
    computed_observables = [
        str(p.get("name"))
        for p in preds
        if isinstance(p, dict)
        and str(p.get("kind") or "").lower() == "observable"
        and any(
            tok in (str(p.get("name") or "") + " " + str(p.get("description") or "")).lower()
            for tok in ("exceed", "threshold", "criterion", "criteria", "more_than_one")
        )
    ]
    status_as_type = False
    for p in preds:
        if str(p.get("kind") or "").lower() not in {"derived", "conclusion"}:
            continue
        name = str(p.get("name") or "")
         # status-as-type pattern
        if name.startswith("is_") and len(p.get("args") or []) == 1:
            arg0 = str((p.get("args") or [""])[0])
            if arg0 in type_names and names_semantically_identical(arg0, name):
                status_as_type = True

    return {
        "initial_symbols_path": str(sym_path) if sym_path.is_file() else None,
        "legal_output_predicates": effect_preds,
        "missing_temporal_support_on_initial_symbols": temporal_missing,
        "helper_predicates_in_initial_symbols": helpers_without_rules_hint,
        "computed_composite_marked_observable": computed_observables,
        "status_as_type_pattern": status_as_type,
        "predicate_count": len(preds),
        "function_count": len(sym.get("functions") or []),
    }


def _analyze_cell(run_dir: Path, budget: int, exit_code: int, duration_s: float) -> dict[str, Any]:
    hist_path = _find_repair_history(run_dir)
    hist = _read_json(hist_path) if hist_path else None
    summary = (hist or {}).get("summary") or _read_json(run_dir / "json_ir_compile" / "repair_summary.json") or {}
    events = list((hist or {}).get("events") or [])

    kb_candidates = [
        run_dir / "translated" / "json_ir" / "kb.fo",
        run_dir / "translated" / "json_ir" / "kb_schema.json",
    ]
    compile_ok = any(p.is_file() for p in kb_candidates)

    score = _read_json(run_dir / "score.json")
    effective = _read_json(run_dir / "effective_config.json")

    items = []
    for it in (score or {}).get("items") or []:
        items.append(
            {
                "id": it.get("id"),
                "decisive": it.get("decisive"),
                "match": it.get("match"),
                "got": it.get("got"),
                "expected": it.get("expected"),
                "query_predicate": it.get("query_predicate"),
                "symbolic_status": it.get("symbolic_status"),
                "epistemic_label": it.get("epistemic_label"),
            }
        )

    failure_class = _classify_failure(summary, events, compile_ok and exit_code == 0)

    return {
        "run_id": run_dir.name,
        "budget_max_kb_llm_calls": budget,
        "duration_seconds": round(duration_s, 1),
        "main_exit_code": exit_code,
        "kb_compile_succeeded": compile_ok and exit_code == 0,
        "pipeline_completed": exit_code == 0,
        "final_normalized_error_code": summary.get("final_normalized_error_code"),
        "final_normalized_error_signature": summary.get("final_normalized_error_signature"),
        "symbol_version_count": summary.get("symbol_version_count"),
        "rules_attempt_count": summary.get("rules_attempt_count"),
        "total_kb_llm_calls": summary.get("total_kb_llm_calls"),
        "final_failure_category": summary.get("final_failure_category"),
        "failure_classification": failure_class,
        "repair_stalled": summary.get("repair_stalled"),
        "budget_exhausted": summary.get("budget_exhausted"),
        "symbol_budget_exhausted": summary.get("symbol_budget_exhausted"),
        "repeated_error_detected": summary.get("repeated_error_detected"),
        "distinct_errors": summary.get("distinct_errors") or [],
        "repair_layers_used": summary.get("repair_layers_used") or [],
        "repair_cards_used": _repair_cards_used(events),
        "compressed_repair_sequence": _compress_sequence(events),
        "repair_history_path": str(hist_path) if hist_path else None,
        "effective_config": effective,
        "score_summary": {
            "decisive": score.get("decisive") if score else None,
            "correct_decisive": score.get("correct_decisive") if score else None,
            "inconclusive": score.get("inconclusive") if score else None,
            "items": items,
        }
        if score
        else None,
        "initial_generation_audit": _initial_symbols_audit(run_dir),
    }


def _run_clean_compile(run_dir: Path, budget: int) -> tuple[int, float]:
    _clean_mod.clean_run_dir(run_dir, dry_run=False)
    env = os.environ.copy()
    env["JSON_IR_MAX_KB_LLM_CALLS"] = str(budget)
    env["SCORE_TREAT_OPEN_WITH_BELIEF"] = "0"
    t0 = time.time()
    code = subprocess.call(
        [
            sys.executable,
            str(_ROOT / "main.py"),
            "--mode",
            "json",
            "--run",
            str(run_dir),
            "--kb-strategy",
            "direct_json_ir_translate",
            "--pipeline-backend",
            "json_ir",
        ],
        cwd=str(_ROOT),
        env=env,
    )
    return code, time.time() - t0


def _compare_budgets(cells: list[dict]) -> dict[str, Any]:
    by_run: dict[str, list[dict]] = {}
    for c in cells:
        by_run.setdefault(c["run_id"], []).append(c)
    out: dict[str, Any] = {}
    for run_id, rows in by_run.items():
        rows = sorted(rows, key=lambda r: r["budget_max_kb_llm_calls"])
        low = rows[0] if rows else None
        high = rows[-1] if len(rows) > 1 else None
        if low and high and low["budget_max_kb_llm_calls"] != high["budget_max_kb_llm_calls"]:
            if not low["kb_compile_succeeded"] and high["kb_compile_succeeded"]:
                out[run_id] = {
                    "classification": "budget_insufficiency",
                    "failed_budget": low["budget_max_kb_llm_calls"],
                    "succeeded_budget": high["budget_max_kb_llm_calls"],
                    "calls_needed": high.get("total_kb_llm_calls"),
                    "recommendation": "Raise eval max_kb_llm_calls to at least "
                    + str(high.get("total_kb_llm_calls") or high["budget_max_kb_llm_calls"]),
                }
            elif not low["kb_compile_succeeded"] and not high["kb_compile_succeeded"]:
                out[run_id] = {
                    "classification": "not_budget_limited",
                    "dominant_failure": high.get("failure_classification"),
                    "final_error": high.get("final_normalized_error_code"),
                    "repair_stalled": high.get("repair_stalled"),
                }
            elif low["kb_compile_succeeded"] and high["kb_compile_succeeded"]:
                out[run_id] = {"classification": "compiles_at_both_budgets"}
        elif rows:
            r = rows[0]
            out[run_id] = {
                "classification": "single_budget_trial",
                "kb_compile_succeeded": r["kb_compile_succeeded"],
                "failure_classification": r.get("failure_classification"),
            }
    return out


def _write_md(path: Path, report: dict) -> None:
    lines = [
        "# Clean compile reproducibility audit",
        "",
        f"Generated: {report.get('generated_at')}",
        "",
        "## Summary",
        "",
    ]
    for c in report.get("cells") or []:
        ok = "OK" if c.get("kb_compile_succeeded") else "FAIL"
        lines.append(
            f"- **{c['run_id']}** budget={c['budget_max_kb_llm_calls']}: {ok} "
            f"(calls={c.get('total_kb_llm_calls')}, sv={c.get('symbol_version_count')}, "
            f"ra={c.get('rules_attempt_count')}, error={c.get('final_normalized_error_code')})"
        )
    lines.extend(["", "## Budget comparison", ""])
    for run_id, cmp in (report.get("budget_comparison") or {}).items():
        lines.append(f"### {run_id}")
        for k, v in cmp.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    lines.extend(["", "## Per-cell detail", ""])
    for c in report.get("cells") or []:
        lines.extend(
            [
                f"### {c['run_id']} @ budget {c['budget_max_kb_llm_calls']}",
                "",
                f"- kb_compile_succeeded: {c.get('kb_compile_succeeded')}",
                f"- failure_classification: {c.get('failure_classification')}",
                f"- final_error: {c.get('final_normalized_error_code')}",
                f"- repair_stalled: {c.get('repair_stalled')}",
                f"- budget_exhausted: {c.get('budget_exhausted')}",
                f"- repair_cards: {', '.join(c.get('repair_cards_used') or []) or '(none)'}",
                "",
                "Compressed sequence:",
                "",
            ]
        )
        for step in c.get("compressed_repair_sequence") or []:
            lines.append(f"- {step}")
        init = c.get("initial_generation_audit") or {}
        lines.extend(
            [
                "",
                "Initial generation:",
                f"- legal_output_predicates: {init.get('legal_output_predicates')}",
                f"- missing_temporal_support: {init.get('missing_temporal_support_on_initial_symbols')}",
                f"- computed_composite_observable: {init.get('computed_composite_marked_observable')}",
                f"- status_as_type: {init.get('status_as_type_pattern')}",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="Clean compile reproducibility audit")
    p.add_argument("--runs", default="run_006,run_009,run_117", help="Comma-separated run folder names")
    p.add_argument("--budgets", default="10,16", help="Comma-separated max_kb_llm_calls values")
    p.add_argument("--runs-root", default="inputs/json", help="Root containing run folders")
    p.add_argument("--output-dir", default=None, help="Report output directory")
    args = p.parse_args()

    runs = [x.strip() for x in str(args.runs).split(",") if x.strip()]
    budgets = [int(x.strip()) for x in str(args.budgets).split(",") if x.strip()]

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output_dir) if args.output_dir else _ROOT / "results" / "reports" / f"clean_compile_repro_{ts}"
    if not out_dir.is_absolute():
        out_dir = _ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    cells: list[dict] = []
    for run_name in runs:
        run_dir = (_ROOT / args.runs_root / run_name).resolve()
        if not (run_dir / "run.json").is_file():
            print("Skip missing run:", run_dir, file=sys.stderr)
            continue
        for budget in budgets:
            print(f"\n=== {run_name} budget={budget} ===", flush=True)
            code, dur = _run_clean_compile(run_dir, budget)
            cell = _analyze_cell(run_dir, budget, code, dur)
            cells.append(cell)
            snap = out_dir / f"{run_name}_budget{budget}.json"
            snap.write_text(json.dumps(cell, ensure_ascii=False, indent=2), encoding="utf-8")
            print(
                f"  -> compile_ok={cell['kb_compile_succeeded']} "
                f"calls={cell.get('total_kb_llm_calls')} error={cell.get('final_normalized_error_code')}",
                flush=True,
            )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strategy": "direct_json_ir_translate",
        "runs": runs,
        "budgets": budgets,
        "cells": cells,
        "budget_comparison": _compare_budgets(cells),
    }
    json_path = out_dir / "clean_compile_repro_report.json"
    md_path = out_dir / "clean_compile_repro_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_md(md_path, report)
    # Stable symlink-style copies for benchmark gate
    stable_root = _ROOT / "results" / "reports"
    stable_root.mkdir(parents=True, exist_ok=True)
    (stable_root / "clean_compile_repro_report.json").write_text(
        json_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (stable_root / "clean_compile_repro_report.md").write_text(
        md_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    print("\nWrote", json_path)
    print("Wrote", md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
