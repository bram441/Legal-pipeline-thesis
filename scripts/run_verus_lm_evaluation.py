#!/usr/bin/env python3
"""Run VERUS-LM on converted Legal-pipeline test runs.

This runner is deliberately an adapter around VERUS-LM. It does not hardcode legal
answers and it treats generation/parsing/symbolic failures as failures or unknowns
instead of silently scoring them as false.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from dataclasses import dataclass, asdict
from typing import Any, Dict, Iterable, List, Optional


TRUE_STRINGS = {"true", "yes", "ja", "correct", "waar"}
FALSE_STRINGS = {"false", "no", "nee", "incorrect", "onwaar"}
UNKNOWN_STRINGS = {"unknown", "inconclusive", "uncertain", "", "none", "null"}


@dataclass
class RunResult:
    run_id: str
    question_id: str
    status: str
    expected: str
    answer: str = ""
    correct: Optional[bool] = None
    failure_stage: str = ""
    error: str = ""
    inference: str = ""
    provider: str = ""
    model: str = ""
    syntax_refinements: int = 0
    unsat_refinements: int = 0
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def norm_answer(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip().lower()
    text = text.replace(".", "").replace("\n", " ").strip()
    if text in TRUE_STRINGS:
        return "true"
    if text in FALSE_STRINGS:
        return "false"
    if text in UNKNOWN_STRINGS:
        return "unknown"
    return text


def score_answer(answer: Any, expected: Any) -> tuple[str, Optional[bool]]:
    a = norm_answer(answer)
    e = norm_answer(expected)
    if a == "unknown":
        return "inconclusive", None
    if e in {"true", "false"} and a in {"true", "false"}:
        return ("correct_decisive", True) if a == e else ("wrong_decisive", False)
    if a == e:
        return "correct_decisive", True
    return "wrong_decisive", False


def load_manifest(input_dir: Path, subset: Iterable[str] | None) -> List[Dict[str, Any]]:
    manifest_path = input_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest.json in {input_dir}. Run convert_json_final_to_verus_lm.py first.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    subset_set = {s.strip() for s in subset or [] if s.strip()}
    entries = manifest.get("runs", [])
    if subset_set:
        entries = [e for e in entries if e.get("run_id") in subset_set]
    return entries


def configure_env(args: argparse.Namespace) -> None:
    provider = args.provider or os.getenv("LLM_PROVIDER") or os.getenv("VERUS_LM_PROVIDER") or "openrouter"
    model = args.model or os.getenv("LLM_MODEL") or os.getenv("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.6"
    base_url = args.base_url or os.getenv("LLM_BASE_URL") or os.getenv("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
    os.environ["LLM_PROVIDER"] = provider
    os.environ["LLM_MODEL"] = model
    os.environ["LLM_BASE_URL"] = base_url
    if args.api_key_env:
        key = os.getenv(args.api_key_env)
        if key:
            os.environ["LLM_API_KEY"] = key
            if provider == "openrouter":
                os.environ["OPENROUTER_API_KEY"] = key
    # Avoid local Phi startup when the patched VERUS-LM answering service supports it.
    os.environ.setdefault("VERUS_LM_LAZY_SMALL_SERVER", "1")


def import_verus(verus_root: Path):
    sys.path.insert(0, str(verus_root.resolve()))
    kb_mod = importlib.import_module("verus_lm.kb_creation")
    q_mod = importlib.import_module("verus_lm.question")
    ans_mod = importlib.import_module("verus_lm.answering_service")
    llm_mod = importlib.import_module("verus_lm.llm_server")
    return kb_mod, q_mod, ans_mod, llm_mod


def server_stats(server: Any) -> Dict[str, int]:
    return {
        "llm_calls": int(getattr(server, "call_count", 0) or 0),
        "prompt_tokens": int(getattr(server, "prompt_tokens", 0) or 0),
        "completion_tokens": int(getattr(server, "completion_tokens", 0) or 0),
        "total_tokens": int(getattr(server, "total_tokens", 0) or 0),
    }


def run_one_question(entry: Dict[str, Any], input_dir: Path, kb_mod: Any, q_mod: Any, ans_mod: Any, args: argparse.Namespace) -> List[RunResult]:
    run_id = entry["run_id"]
    adapter_path = input_dir / entry["adapter_file"]
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    kb = (input_dir / adapter["kb_file"]).read_text(encoding="utf-8")
    questions = json.loads((input_dir / adapter["questions_file"]).read_text(encoding="utf-8"))
    results: List[RunResult] = []

    try:
        translation = kb_mod.KBTranslation(kb, run_id, sat=not args.no_sat_check, owa=args.owa)
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        for qkey, q in questions.items():
            results.append(RunResult(run_id, qkey, "kb_generation_failure", q.get("answer", ""), failure_stage="kb_generation", error=err, provider=args.provider, model=args.model))
        return results

    for qkey, q in questions.items():
        expected = q.get("answer", "")
        try:
            question = q_mod.Question(q.get("question", ""), translation, truth=expected, id=f"{run_id}_{qkey}", multi_step=bool(q.get("multi", False)))
            response = ans_mod.AnswerQuestion(question, inference=q.get("inference", ""), complex_formula=(q.get("inference") == "entailment"), version=args.version, output=True)
            answer = str(getattr(response, "answer", ""))
            status, correct = score_answer(answer, expected)
            stats = server_stats(getattr(translation, "llm_server", None))
            results.append(RunResult(
                run_id=run_id,
                question_id=qkey,
                status=status,
                expected=expected,
                answer=answer,
                correct=correct,
                inference=str(getattr(response, "inference", "")),
                provider=args.provider,
                model=args.model,
                syntax_refinements=int(getattr(translation, "syntax_refinements", 0) or 0),
                unsat_refinements=int(getattr(translation, "sat_refinements", 0) or 0),
                **stats,
            ))
        except Exception as exc:
            results.append(RunResult(
                run_id=run_id,
                question_id=qkey,
                status="symbolic_execution_failure",
                expected=expected,
                failure_stage="question_answering",
                error=f"{type(exc).__name__}: {exc}",
                provider=args.provider,
                model=args.model,
            ))
    return results


def write_reports(results: List[RunResult], output_dir: Path, args: argparse.Namespace) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(r) for r in results]
    fields = list(rows[0].keys()) if rows else list(RunResult("", "", "", "").__dict__.keys())
    with (output_dir / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    total = len(results)
    correct_decisive = sum(1 for r in results if r.status == "correct_decisive")
    wrong_decisive = sum(1 for r in results if r.status == "wrong_decisive")
    inconclusive = sum(1 for r in results if r.status == "inconclusive")
    kb_fail = sum(1 for r in results if r.status == "kb_generation_failure")
    parse_fail = sum(1 for r in results if r.status == "parsing_failure")
    symbolic_fail = sum(1 for r in results if r.status == "symbolic_execution_failure")
    scored = correct_decisive + wrong_decisive + inconclusive
    decisive = correct_decisive + wrong_decisive
    matrix = {
        "provider": args.provider,
        "model": args.model,
        "version": args.version,
        "total_runs": len({r.run_id for r in results}),
        "total_questions": total,
        "scored": scored,
        "correct_decisive": correct_decisive,
        "wrong_decisive": wrong_decisive,
        "inconclusive_unknown": inconclusive,
        "law_compilation_kb_generation_failures": kb_fail,
        "parsing_failures": parse_fail,
        "symbolic_execution_failures": symbolic_fail,
        "strict_accuracy": (correct_decisive / total) if total else 0.0,
        "coverage": (scored / total) if total else 0.0,
        "decisive_precision": (correct_decisive / decisive) if decisive else 0.0,
        "decisive_wrong_rate": (wrong_decisive / total) if total else 0.0,
        "llm_calls": sum(r.llm_calls for r in results),
        "prompt_tokens": sum(r.prompt_tokens for r in results),
        "completion_tokens": sum(r.completion_tokens for r in results),
        "total_tokens": sum(r.total_tokens for r in results),
        "runs": rows,
    }
    (output_dir / "matrix.json").write_text(json.dumps(matrix, indent=2, ensure_ascii=False), encoding="utf-8")

    md = [
        "# VERUS-LM evaluation report",
        "",
        f"Provider: `{args.provider}`  ",
        f"Model: `{args.model}`  ",
        f"VERUS version mode: `{args.version}`",
        "",
        "## Summary",
        "",
        f"- total runs/questions: {matrix['total_runs']} / {total}",
        f"- scored: {scored}",
        f"- correct decisive: {correct_decisive}",
        f"- wrong decisive: {wrong_decisive}",
        f"- inconclusive/unknown: {inconclusive}",
        f"- law compilation / KB generation failures: {kb_fail}",
        f"- parsing failures: {parse_fail}",
        f"- symbolic execution failures: {symbolic_fail}",
        f"- strict accuracy: {matrix['strict_accuracy']:.4f}",
        f"- coverage: {matrix['coverage']:.4f}",
        f"- decisive precision: {matrix['decisive_precision']:.4f}",
        f"- decisive wrong rate: {matrix['decisive_wrong_rate']:.4f}",
        "",
        "## Fairness notes",
        "",
        "- The adapter preserves the same law text, case text, question text, expected answer, and metadata from the JSON run files.",
        "- Failures during KB generation or symbolic execution are not converted into `False`; they are reported as failure categories.",
        "- The report records provider/model so differences with the JSON_IR-pipeline can be made explicit.",
    ]
    (output_dir / "report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run VERUS-LM over converted Legal-pipeline test runs.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--verus-root", default=os.getenv("VERUS_LM_ROOT", "../Versus-LM/verus-lm"))
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "openrouter"))
    parser.add_argument("--model", default=os.getenv("LLM_MODEL", os.getenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.6")))
    parser.add_argument("--base-url", default=os.getenv("LLM_BASE_URL", os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")))
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--subset", nargs="*")
    parser.add_argument("--version", default="llm", choices=["llm", "slm", "hybrid"], help="VERUS-LM answering mode. Use llm for OpenRouter-only where possible.")
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Validate converted input/report paths without importing VERUS-LM or calling LLMs.")
    parser.add_argument("--no-sat-check", action="store_true")
    parser.add_argument("--owa", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    entries = load_manifest(input_dir, args.subset)
    if not entries:
        raise SystemExit("No runs selected.")

    if args.dry_run:
        dry_results = []
        for e in entries:
            adapter = json.loads((input_dir / e["adapter_file"]).read_text(encoding="utf-8"))
            for q in adapter.get("questions", []):
                dry_results.append(RunResult(e["run_id"], q.get("verus_key", q.get("id", "q")), "dry_run_not_executed", q.get("verus_answer", ""), provider=args.provider, model=args.model))
        write_reports(dry_results, output_dir, args)
        print(f"Dry-run wrote report skeleton to {output_dir}")
        return 0

    configure_env(args)
    verus_root = Path(args.verus_root).resolve()
    kb_mod, q_mod, ans_mod, llm_mod = import_verus(verus_root)

    # Rebind the class-level server after import so the selected provider/model is recorded.
    if hasattr(llm_mod.LLMServer, "from_env"):
        kb_mod.KBTranslation.llm_server = llm_mod.LLMServer.from_env()
    else:
        kb_mod.KBTranslation.llm_server = llm_mod.LLMServer(args.provider)

    all_results: List[RunResult] = []
    for entry in entries:
        try:
            all_results.extend(run_one_question(entry, input_dir, kb_mod, q_mod, ans_mod, args))
        except Exception as exc:
            all_results.append(RunResult(entry.get("run_id", "unknown"), "all", "runner_failure", "", failure_stage="runner", error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}", provider=args.provider, model=args.model))
        write_reports(all_results, output_dir, args)
    print(f"Wrote VERUS-LM evaluation report to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
