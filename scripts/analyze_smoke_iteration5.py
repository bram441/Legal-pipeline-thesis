#!/usr/bin/env python
"""Summarize post-Iteration-5 smoke evaluation work dirs."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
TARGET_RUNS = ("run_006", "run_009", "run_110", "run_117", "run_119", "run_120")
TARGET_STRATEGIES = ("direct_json_ir_translate", "direct_json_ir_no_translate")


def _read_text(p: Path, limit: int = 12000) -> str:
    if not p.is_file():
        return ""
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
        return t[:limit] if len(t) > limit else t
    except OSError:
        return ""


def _classify_validator(msg: str) -> str:
    ml = (msg or "").lower()
    if "computed-looking observable" in ml or "looks computed/composite" in ml:
        return "composite_helper"
    if "at-most-one" in ml or "more-than-one criteria" in ml or "simple or over individual" in ml:
        return "threshold_cardinality"
    if "semantically identical to the status" in ml or "status or classification encoded as a primitive type" in ml:
        return "status_as_type"
    if "legal-effect or timing language" in ml or "no derived legal-output predicate" in ml:
        return "legal_effect_missing"
    if "json_ir_schema_design_error" in ml:
        return "schema_design_other"
    if "json_ir_rule_design_error" in ml:
        return "rule_design_other"
    if "idp failed to parse" in ml or "failed to parse compiled kb" in ml:
        return "idp_parse"
    if "kb lint" in ml:
        return "kb_lint"
    if "theory is unsatisfiable" in ml or "kbsemanticerror" in ml:
        return "kb_semantic"
    if "validation failed (case/query)" in ml or "legal consequences or timing" in ml:
        return "query_target"
    if "compilation failed" in ml or "law compilation failed" in ml:
        return "compile_other"
    return "other"


def _repair_layers(blob: str) -> list[str]:
    layers: list[str] = []
    if "symbols repair" in blob.lower() or "repair layer: symbols" in blob.lower():
        layers.append("symbols")
    if "rules repair" in blob.lower() or "repair layer: rules" in blob.lower():
        layers.append("rules")
    if "[kb] repair attempt" in blob.lower():
        layers.append("kb_repair_attempted")
    return layers


def _find_combined_ir(work: Path) -> Path | None:
    for p in sorted(work.rglob("combined_ir.json")):
        return p
    return None


def _kb_predicates(ir_path: Path) -> list[dict]:
    try:
        ir = json.loads(ir_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return list(ir.get("predicates") or [])


def _effect_preds(preds: list[dict]) -> list[str]:
    from pipeline.kb.legal_effect import predicate_represents_legal_effect_output

    out = []
    for p in preds:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "")
        if predicate_represents_legal_effect_output(
            name,
            description=str(p.get("description") or ""),
            kind=str(p.get("kind") or ""),
            legal_output=p.get("legal_output") if isinstance(p.get("legal_output"), bool) else None,
            output_category=str(p.get("output_category") or ""),
        ):
            out.append(name)
    return out


def _status_as_type_hits(preds: list[dict], types: list) -> bool:
    from pipeline.kb.status_as_type import names_semantically_identical

    type_set = set()
    for t in types or []:
        if isinstance(t, dict):
            type_set.add(str(t.get("name") or ""))
        else:
            type_set.add(str(t))
    for p in preds:
        if str(p.get("kind") or "").lower() not in {"derived", "conclusion"}:
            continue
        name = str(p.get("name") or "")
        if not name.startswith("is_"):
            continue
        args = p.get("args") or []
        if len(args) != 1:
            continue
        if args[0] in type_set and names_semantically_identical(str(args[0]), name):
            return True
    return False


def _analyze_cell(work: Path) -> dict:
    blob = _read_text(work / "run_trace.txt", 50000)
    for log in sorted(work.rglob("kb_compile.log")):
        blob += "\n" + _read_text(log, 8000)

    val_errs: list[str] = []
    compile_root = work / "json_ir_compile"
    if compile_root.is_dir():
        for vf in sorted(compile_root.rglob("validation_error.txt")):
            val_errs.append(_read_text(vf, 4000))

    validators = [_classify_validator(v) for v in val_errs if v.strip()]
    validators = list(dict.fromkeys(validators))

    repair_count = len(re.findall(r"\[KB\]\s+Repair attempt", blob, re.I))
    kb_ok = "compilation successful" in blob.lower()
    kb_fail = "kb compilation failed" in blob.lower() or "law compilation failed" in blob.lower()

    combined = _find_combined_ir(work)
    preds: list[dict] = []
    types: list = []
    if combined:
        try:
            ir = json.loads(combined.read_text(encoding="utf-8"))
            preds = list(ir.get("predicates") or [])
            types = list(ir.get("types") or [])
        except (json.JSONDecodeError, OSError):
            pass

    score = None
    sp = work / "score.json"
    if sp.is_file():
        try:
            score = json.loads(sp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    items = []
    for it in (score or {}).get("items") or []:
        items.append(
            {
                "id": it.get("id"),
                "query_predicate": it.get("query_predicate"),
                "query_predicate_kind": it.get("query_predicate_kind"),
                "symbolic_status": it.get("symbolic_status"),
                "epistemic_label": it.get("epistemic_label"),
                "score": it.get("score"),
                "gold": it.get("gold"),
                "warnings": it.get("warnings") or [],
            }
        )

    # Predicate metadata from combined_ir
    pred_meta = {}
    for p in preds:
        n = p.get("name")
        if n:
            pred_meta[n] = {
                "kind": p.get("kind"),
                "legal_output": p.get("legal_output"),
                "output_category": p.get("output_category"),
            }

    for it in items:
        pm = pred_meta.get(it.get("query_predicate") or "")
        if pm:
            it["legal_output"] = pm.get("legal_output")
            it["output_category"] = pm.get("output_category")

    return {
        "work_dir": str(work),
        "kb_compile_ok": kb_ok and not kb_fail,
        "kb_compile_failed": kb_fail or (not kb_ok and repair_count > 0),
        "repair_attempts": repair_count,
        "repair_layers": _repair_layers(blob),
        "validators_fired": validators,
        "last_validation_snippet": (val_errs[-1][:500] if val_errs else ""),
        "effect_predicates_in_kb": _effect_preds(preds),
        "status_as_type_pattern_in_kb": _status_as_type_hits(preds, types),
        "derived_names": [
            p.get("name")
            for p in preds
            if str(p.get("kind") or "").lower() in {"derived", "conclusion"}
        ],
        "score_items": items,
        "combined_ir": str(combined) if combined else None,
    }


def main() -> int:
    eval_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if eval_dir is None:
        reports = _ROOT / "results" / "reports"
        candidates = sorted(reports.glob("evaluation_*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("No evaluation_* directory found", file=sys.stderr)
            return 1
        eval_dir = candidates[0]

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

    summary_path = eval_dir / "smoke_iteration5_analysis.json"
    summary_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(out, indent=2, ensure_ascii=False))
    print("\nWrote", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
