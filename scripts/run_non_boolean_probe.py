#!/usr/bin/env python
"""
Run the JSON_IR pipeline on the non_boolean_same_laws_testset without automatic scoring.

This script converts the non-boolean probe format:
  plain_inputs/nb_001.json
  gold/nb_001.gold.json
into temporary pipeline run folders:
  <output-dir>/work/nb_001/run.json

It then calls main.py for each run and writes a manual-review summary.
Gold answers are copied only to the review files, never into run.json/prompts.

Usage from the Legal-pipeline project root:
  python scripts/run_non_boolean_probe.py ^
    --input-dir inputs/non_boolean_same_laws_testset ^
    --output-dir results/final/non_boolean_probe_json_ir_claude ^
    --model anthropic/claude-sonnet-4.6 ^
    --strategy direct_json_ir_no_translate ^
    --config config/heavy.json ^
    --explain
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_inputs(input_dir: Path) -> list[Path]:
    plain_dir = input_dir / "plain_inputs"
    if plain_dir.is_dir():
        return sorted(plain_dir.glob("nb_*.json"))
    return sorted(input_dir.glob("nb_*.json"))


def _load_gold(input_dir: Path, run_id: str) -> dict[str, Any] | None:
    candidates = [
        input_dir / "gold" / f"{run_id}.gold.json",
        input_dir / "gold" / f"{run_id}.json",
    ]
    for p in candidates:
        if p.is_file():
            return _read_json(p)
    return None


def _question_with_explain(question: str, *, explain: bool) -> str:
    q = (question or "").strip()
    if not explain:
        return q
    # Keep the original question primary. This usually sets query.explain=true without
    # replacing the task by a pure explanation intent.
    suffix = "Geef ook kort aan waarom, op basis van de formele redenering."
    if q.endswith("?"):
        return q + " " + suffix
    return q + "? " + suffix


def _make_run_json(src: dict[str, Any], *, explain: bool) -> dict[str, Any]:
    run_id = str(src.get("run_id") or src.get("id") or "").strip()
    if not run_id:
        raise ValueError("input is missing run_id")
    law_text = str(src.get("law_text") or "").strip()
    case_text = str(src.get("case_text") or src.get("case") or "").strip()
    question = str(src.get("question") or "").strip()
    if not law_text:
        raise ValueError(f"{run_id}: missing law_text")
    if not case_text:
        raise ValueError(f"{run_id}: missing case_text")
    if not question:
        raise ValueError(f"{run_id}: missing question")

    # IMPORTANT: no expected answer is included here. The main pipeline will therefore
    # write results.json for inspection, but no meaningful automatic score is produced.
    return {
        "id": run_id,
        "law": {
            "text": law_text,
            "source": src.get("law_source"),
        },
        "case": {
            "text": case_text,
        },
        "questions": [
            {
                "id": "q1",
                "text": _question_with_explain(question, explain=explain),
                "metadata": {
                    "original_question": question,
                    "answer_type": src.get("answer_type"),
                    "non_boolean_probe": True,
                    "automatic_scoring": False,
                },
            }
        ],
        "metadata": {
            "source_dataset": "non_boolean_same_laws_testset",
            "answer_type": src.get("answer_type"),
            "law_source": src.get("law_source"),
        },
    }


def _extract_result_summary(run_dir: Path) -> dict[str, Any]:
    result_path = run_dir / "results.json"
    if not result_path.is_file():
        return {"pipeline_status": "no_results_json"}
    try:
        data = _read_json(result_path)
    except Exception as exc:
        return {"pipeline_status": "bad_results_json", "error": repr(exc)}
    questions = data.get("questions") or []
    if not questions:
        return {"pipeline_status": "no_questions_in_results"}
    item = questions[0]
    pipe = item.get("pipeline") or {}
    sym = pipe.get("symbolic_result") or {}
    query = pipe.get("query") or {}
    out = {
        "pipeline_status": "error" if pipe.get("error_stage") else "ok",
        "error_stage": pipe.get("error_stage"),
        "error": pipe.get("error"),
        "natural_language": pipe.get("natural_language"),
        "explanation": pipe.get("explanation"),
        "query": query,
        "query_type": query.get("query_type") if isinstance(query, dict) else None,
        "internal_intent": query.get("internal_intent") if isinstance(query, dict) else None,
        "query_predicate": query.get("predicate") or query.get("predicate_hint") if isinstance(query, dict) else None,
        "symbolic_status": sym.get("symbolic_status") or sym.get("status") if isinstance(sym, dict) else None,
        "output_kind": sym.get("output_kind") if isinstance(sym, dict) else None,
        "certainty_class": sym.get("certainty_class") if isinstance(sym, dict) else None,
        "symbolic_result": sym,
    }
    return out


def _write_review_files(output_dir: Path, records: list[dict[str, Any]]) -> None:
    jsonl_path = output_dir / "manual_review.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    csv_path = output_dir / "manual_review.csv"
    fields = [
        "run_id",
        "answer_type",
        "law_source",
        "exit_code",
        "pipeline_status",
        "error_stage",
        "query_type",
        "internal_intent",
        "query_predicate",
        "symbolic_status",
        "output_kind",
        "certainty_class",
        "natural_language",
        "explanation",
        "gold_expected",
        "work_dir",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in records:
            w.writerow({k: r.get(k) for k in fields})

    md_path = output_dir / "manual_review.md"
    lines = [
        "# Non-boolean probe manual review",
        "",
        "This is an exploratory run. Gold answers were not included in prompts and no automatic score was computed.",
        "",
    ]
    for r in records:
        lines.extend([
            f"## {r.get('run_id')} ({r.get('answer_type')})",
            "",
            f"- Law source: `{r.get('law_source')}`",
            f"- Pipeline status: `{r.get('pipeline_status')}`",
            f"- Query type / intent: `{r.get('query_type')}` / `{r.get('internal_intent')}`",
            f"- Output kind: `{r.get('output_kind')}`",
            f"- Work dir: `{r.get('work_dir')}`",
            "",
            "**Question**",
            "",
            str(r.get("question") or ""),
            "",
            "**Pipeline answer**",
            "",
            str(r.get("natural_language") or ""),
            "",
            "**Pipeline explanation**",
            "",
            str(r.get("explanation") or ""),
            "",
            "**Gold answer for manual comparison**",
            "",
            str(r.get("gold_expected") or ""),
            "",
        ])
        if r.get("error_stage"):
            lines.extend(["**Error**", "", f"{r.get('error_stage')}: {r.get('error')}", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run non-boolean JSON_IR probe without scoring.")
    parser.add_argument("--input-dir", required=True, help="Folder containing plain_inputs/ and optional gold/.")
    parser.add_argument("--output-dir", required=True, help="Output folder for work dirs and manual review files.")
    parser.add_argument("--strategy", default="direct_json_ir_no_translate")
    parser.add_argument("--config", default="config/heavy.json")
    parser.add_argument("--provider", default="auto", choices=["auto", "openai"])
    parser.add_argument("--model", default=None, help="Optional model id, e.g. anthropic/claude-sonnet-4.6")
    parser.add_argument("--base-url", default="https://openrouter.ai/api/v1")
    parser.add_argument("--llm-provider", default="openrouter")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--runs", default="all", help="all or comma-separated nb ids, e.g. nb_001,nb_002")
    parser.add_argument("--explain", action="store_true", help="Append a short Dutch explanation request to each question.")
    parser.add_argument("--llm-explanations", action="store_true", help="Enable extra LLM paraphrasing for supported symbolic explanations.")
    parser.add_argument("--clean", action="store_true", help="Delete output-dir before running.")
    parser.add_argument("--dry-run", action="store_true", help="Only create work/run.json files and review manifest; do not call main.py.")
    args = parser.parse_args()

    root = _project_root()
    input_dir = Path(args.input_dir)
    if not input_dir.is_absolute():
        input_dir = root / input_dir
    input_dir = input_dir.resolve()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    output_dir = output_dir.resolve()

    if args.clean and output_dir.is_dir():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work_root = output_dir / "work"
    work_root.mkdir(parents=True, exist_ok=True)

    input_files = _discover_inputs(input_dir)
    if args.runs.strip().lower() != "all":
        wanted = {x.strip() for x in args.runs.split(",") if x.strip()}
        input_files = [p for p in input_files if p.stem in wanted]
    if args.limit is not None:
        input_files = input_files[: args.limit]
    if not input_files:
        print("No nb_*.json inputs found under", input_dir, file=sys.stderr)
        return 1

    env = os.environ.copy()
    if args.llm_provider:
        env["LLM_PROVIDER"] = args.llm_provider
    if args.model:
        env["LLM_MODEL"] = args.model
        env["OPENROUTER_MODEL"] = args.model
    if args.base_url:
        env["LLM_BASE_URL"] = args.base_url
        env["OPENROUTER_BASE_URL"] = args.base_url
    if args.llm_explanations:
        env["PIPELINE_USE_LLM_EXPLANATIONS"] = "1"
        env.setdefault("PIPELINE_NL_EXPLAINER_PROVIDER", "openai")

    records: list[dict[str, Any]] = []
    manifest = {
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "strategy": args.strategy,
        "config": args.config,
        "model": args.model,
        "explain_appended_to_questions": bool(args.explain),
        "llm_explanations_enabled": bool(args.llm_explanations),
        "runs": [],
        "note": "Gold answers are used only for manual review, not included in run.json prompts.",
    }

    for src_path in input_files:
        src = _read_json(src_path)
        run_id = str(src.get("run_id") or src_path.stem)
        gold = _load_gold(input_dir, run_id) or {}
        run_dir = work_root / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        run_json = _make_run_json(src, explain=args.explain)
        (run_dir / "run.json").write_text(json.dumps(run_json, indent=2, ensure_ascii=False), encoding="utf-8")
        (run_dir / "gold_for_manual_review.json").write_text(json.dumps(gold, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest["runs"].append(run_id)

        record: dict[str, Any] = {
            "run_id": run_id,
            "answer_type": src.get("answer_type"),
            "law_source": src.get("law_source"),
            "case_text": src.get("case_text"),
            "question": src.get("question"),
            "gold_expected": gold.get("expected_answer"),
            "gold_type": gold.get("gold_type"),
            "work_dir": str(run_dir),
        }

        if args.dry_run:
            record.update({"exit_code": None, "pipeline_status": "dry_run"})
            records.append(record)
            continue

        cmd = [
            sys.executable,
            str(root / "main.py"),
            "--mode",
            "json",
            "--run",
            str(run_dir),
            "--provider",
            args.provider,
            "--kb-strategy",
            args.strategy,
        ]
        if args.config:
            cmd.extend(["--config", args.config])

        print("===", run_id, "===")
        proc = subprocess.run(cmd, cwd=str(root), env=env, text=True)
        record["exit_code"] = proc.returncode
        record.update(_extract_result_summary(run_dir))
        records.append(record)

    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_review_files(output_dir, records)

    print("Wrote:", output_dir / "manifest.json")
    print("Wrote:", output_dir / "manual_review.jsonl")
    print("Wrote:", output_dir / "manual_review.csv")
    print("Wrote:", output_dir / "manual_review.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
