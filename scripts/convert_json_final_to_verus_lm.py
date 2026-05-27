#!/usr/bin/env python3
"""Convert the Legal-pipeline JSON testset to a VERUS-LM-friendly layout.

The converter does not change legal content. It copies law text, case text, question
text, expected answers, and metadata into a neutral adapter format and also writes
files shaped like VERUS-LM's custom benchmark directory:

  <out>/runs/<run_id>/kb.txt
  <out>/runs/<run_id>/questions.json
  <out>/verus_lm_custom/kb/<run_id>.txt
  <out>/verus_lm_custom/questions/<run_id>.json
  <out>/manifest.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def resolve_law_text(run: Dict[str, Any], run_path: Path, project_root: Path) -> Tuple[str, Dict[str, Any]]:
    law = run.get("law") or {}
    meta = dict(law)
    if "text" in law and law["text"]:
        return str(law["text"]), meta
    if "path" in law and law["path"]:
        candidates = [
            project_root / law["path"],
            run_path.parent / law["path"],
            run_path.parent / Path(law["path"]).name,
        ]
        for candidate in candidates:
            if candidate.exists():
                meta["resolved_path"] = str(candidate.relative_to(project_root) if candidate.is_relative_to(project_root) else candidate)
                return read_text(candidate), meta
        raise FileNotFoundError(f"Could not resolve law.path={law['path']!r} for {run_path}")
    raise ValueError(f"No law.text or law.path found in {run_path}")


def expected_to_verus_answer(expected: Any) -> str:
    """Map expected answers to VERUS-LM's simple truth field without losing original metadata."""
    if isinstance(expected, dict):
        mode = expected.get("mode")
        value = expected.get("value")
        if mode == "boolean" or isinstance(value, bool):
            return "True" if bool(value) else "False"
        if value is not None:
            return str(value)
        return json.dumps(expected, ensure_ascii=False)
    if isinstance(expected, bool):
        return "True" if expected else "False"
    return "" if expected is None else str(expected)


def iter_run_files(input_dir: Path, subset: Iterable[str] | None = None) -> List[Path]:
    subset_set = {s.strip() for s in subset or [] if s.strip()}
    files = sorted(input_dir.glob("run_*/run.json"))
    if subset_set:
        files = [p for p in files if p.parent.name in subset_set or p.stem in subset_set]
    return files


def convert_run(run_path: Path, project_root: Path, out_dir: Path) -> Dict[str, Any]:
    run = json.loads(run_path.read_text(encoding="utf-8"))
    run_id = run.get("id") or run_path.parent.name
    law_text, law_meta = resolve_law_text(run, run_path, project_root)
    case_text = str((run.get("case") or {}).get("text", ""))
    questions = run.get("questions") or []
    if not questions:
        raise ValueError(f"No questions found in {run_path}")

    kb_text = (
        "The following text contains the applicable legal rules and the concrete case facts.\n\n"
        "LEGAL RULES:\n"
        f"{law_text.strip()}\n\n"
        "CASE FACTS:\n"
        f"{case_text.strip()}\n"
    )

    verus_questions: Dict[str, Dict[str, Any]] = {}
    preserved_questions: List[Dict[str, Any]] = []
    for idx, q in enumerate(questions, start=1):
        qid = q.get("id") or f"q{idx}"
        key = f"Q{idx}"
        expected = q.get("expected")
        verus_questions[key] = {
            "question": q.get("text", ""),
            "answer": expected_to_verus_answer(expected),
            "multi": bool(q.get("multi", False)),
            # Belgian legal yes/no questions are closest to entailment/deduction.
            # The runner may override this, but the converter does not infer legal content.
            "inference": q.get("inference", "entailment"),
            "source_question_id": qid,
        }
        preserved_questions.append({**q, "verus_key": key, "verus_answer": verus_questions[key]["answer"]})

    run_out = out_dir / "runs" / run_id
    custom_kb = out_dir / "verus_lm_custom" / "kb"
    custom_questions = out_dir / "verus_lm_custom" / "questions"
    generated_idp = out_dir / "verus_lm_custom" / "generated_idp"
    for p in [run_out, custom_kb, custom_questions, generated_idp]:
        p.mkdir(parents=True, exist_ok=True)

    (run_out / "kb.txt").write_text(kb_text, encoding="utf-8")
    (run_out / "questions.json").write_text(json.dumps(verus_questions, indent=2, ensure_ascii=False), encoding="utf-8")
    adapter = {
        "run_id": run_id,
        "source_run_json": str(run_path.relative_to(project_root) if run_path.is_relative_to(project_root) else run_path),
        "kb_file": str((run_out / "kb.txt").relative_to(out_dir)),
        "questions_file": str((run_out / "questions.json").relative_to(out_dir)),
        "law": law_meta,
        "case": run.get("case") or {},
        "questions": preserved_questions,
        "metadata": {k: v for k, v in run.items() if k not in {"law", "case", "questions"}},
    }
    (run_out / "verus_input.json").write_text(json.dumps(adapter, indent=2, ensure_ascii=False), encoding="utf-8")

    (custom_kb / f"{run_id}.txt").write_text(kb_text, encoding="utf-8")
    (custom_questions / f"{run_id}.json").write_text(json.dumps(verus_questions, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "run_id": run_id,
        "source_run_json": adapter["source_run_json"],
        "adapter_file": str((run_out / "verus_input.json").relative_to(out_dir)),
        "kb_file": adapter["kb_file"],
        "questions_file": adapter["questions_file"],
        "verus_custom_kb": f"verus_lm_custom/kb/{run_id}.txt",
        "verus_custom_questions": f"verus_lm_custom/questions/{run_id}.json",
        "question_count": len(questions),
        "expected_values": [pq.get("verus_answer") for pq in preserved_questions],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Legal-pipeline JSON runs to VERUS-LM adapter files.")
    parser.add_argument("--input-dir", default="inputs/json_final_clean", help="Directory containing run_*/run.json")
    parser.add_argument("--output-dir", default="inputs/verus_lm_from_json_final_clean_law")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--subset", nargs="*", help="Optional run ids, e.g. run_001 run_002")
    parser.add_argument("--clean", action="store_true", help="Delete the output directory first")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    input_dir = (project_root / args.input_dir).resolve()
    out_dir = (project_root / args.output_dir).resolve()

    if args.clean and out_dir.exists():
        import shutil
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    run_files = iter_run_files(input_dir, args.subset)
    if not run_files:
        raise SystemExit(f"No run.json files found in {input_dir}")

    entries = [convert_run(p, project_root, out_dir) for p in run_files]
    manifest = {
        "source_input_dir": str(input_dir.relative_to(project_root) if input_dir.is_relative_to(project_root) else input_dir),
        "output_dir": str(out_dir.relative_to(project_root) if out_dir.is_relative_to(project_root) else out_dir),
        "runs": entries,
        "total_runs": len(entries),
        "total_questions": sum(e["question_count"] for e in entries),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Converted {manifest['total_runs']} runs / {manifest['total_questions']} questions to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
