#!/usr/bin/env python
"""
Run plain LLM baseline on legal true/false/unknown questions.

The model receives only:
- law text
- case text
- question

It must answer exactly one of:
TRUE
FALSE
UNKNOWN

No expected/gold label is included in the prompt.
No repair retry is performed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from openai import OpenAI

# Absolute repo root for resolving paths from anywhere.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Load environment variables from project .env (e.g., OPENROUTER_API_KEY).
load_dotenv(_PROJECT_ROOT / ".env")


LABELS = {"TRUE", "FALSE", "UNKNOWN"}


LAW_KEYS = [
    "law_text",
    "selected_law_text",
    "scoped_law_text",
    "article_text",
    "legal_text",
    "law",
    "text_law",
]

CASE_KEYS = [
    "case_text",
    "case",
    "facts",
    "fact_text",
    "case_facts",
    "case_facts_text",
    "narrative",
]

QUESTION_KEYS = [
    "question",
    "question_text",
    "query",
    "legal_question",
]

GOLD_KEYS = [
    "expected",
    "expected_answer",
    "expected_label",
    "gold",
    "gold_label",
    "answer",
    "label",
]


@dataclass
class PlainLLMTask:
    run_id: str
    law_text: str
    case_text: str
    question: str
    gold_label: str | None = None
    source_file: str | None = None


def normalize_label(value: Any) -> str | None:
    if value is None:
        return None

    text = str(value).strip().upper()

    mapping = {
        "YES": "TRUE",
        "Y": "TRUE",
        "TRUE": "TRUE",
        "T": "TRUE",
        "ENTAILS": "TRUE",
        "ENTAILED": "TRUE",
        "NO": "FALSE",
        "N": "FALSE",
        "FALSE": "FALSE",
        "F": "FALSE",
        "NOT ENTAILED": "FALSE",
        "UNKNOWN": "UNKNOWN",
        "INCONCLUSIVE": "UNKNOWN",
        "UNDETERMINED": "UNKNOWN",
        "UNSUPPORTED": "UNKNOWN",
        "UNSURE": "UNKNOWN",
    }

    return mapping.get(text)


def parse_model_answer(text: str) -> str | None:
    """
    Strict parser: accept only outputs that clearly contain one of the allowed labels.
    No repair is attempted.
    """
    if not text:
        return None

    cleaned = text.strip().upper()

    if cleaned in LABELS:
        return cleaned

    # Allow accidental final-answer formatting, but no semantic repair.
    match = re.search(r"\bFINAL\s+ANSWER\s*:\s*(TRUE|FALSE|UNKNOWN)\b", cleaned)
    if match:
        return match.group(1)

    # If the whole output is short and contains exactly one label, accept it.
    found = re.findall(r"\b(TRUE|FALSE|UNKNOWN)\b", cleaned)
    if len(set(found)) == 1 and len(cleaned) <= 80:
        return found[0]

    return None


def iter_json_files(path: Path) -> Iterable[Path]:
    if path.is_file() and path.suffix.lower() == ".json":
        yield path
        return

    for p in sorted(path.rglob("*.json")):
        # Skip known result/artifact files if a user accidentally points to a result folder.
        lowered = str(p).lower()
        if any(skip in lowered for skip in ["results", "report", "prediction", "summary"]):
            continue
        yield p


def flatten_json(obj: Any, prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}

    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out[key] = v
            out.update(flatten_json(v, key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            key = f"{prefix}[{i}]"
            out[key] = v
            out.update(flatten_json(v, key))

    return out


def find_string(flat: dict[str, Any], wanted_keys: list[str]) -> str | None:
    """
    Find a string value by exact last-key match first, then by fuzzy path ending.
    """
    # Exact last segment match.
    for wanted in wanted_keys:
        for path, value in flat.items():
            last = path.split(".")[-1].lower()
            if last == wanted.lower() and isinstance(value, str) and value.strip():
                return value.strip()

    # Fuzzy contains match.
    for wanted in wanted_keys:
        for path, value in flat.items():
            if wanted.lower() in path.lower() and isinstance(value, str) and value.strip():
                return value.strip()

    return None


def find_gold(flat: dict[str, Any]) -> str | None:
    for wanted in GOLD_KEYS:
        for path, value in flat.items():
            last = path.split(".")[-1].lower()
            if last == wanted.lower():
                label = normalize_label(value)
                if label:
                    return label

    for wanted in GOLD_KEYS:
        for path, value in flat.items():
            if wanted.lower() in path.lower():
                label = normalize_label(value)
                if label:
                    return label

    return None





def _first_nonempty_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _candidate_project_roots(json_file: Path) -> list[Path]:
    """Return likely roots from which law.path can be resolved."""
    roots: list[Path] = []
    for parent in [json_file.parent, *json_file.parents]:
        roots.append(parent)
    roots.extend([Path.cwd(), _PROJECT_ROOT])

    # De-duplicate while preserving order.
    out: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root.resolve()) if root.exists() else str(root)
        if key not in seen:
            seen.add(key)
            out.append(root)
    return out


def resolve_law_text(data: Any, flat: dict[str, Any], json_file: Path) -> tuple[str | None, str | None]:
    """
    Resolve law text robustly.

    The project input format usually stores only a law path, e.g.
    {"law": {"path": "example_laws_clean/erfrecht_clean.txt"}}.
    The earlier generic key search accidentally used that path string as the law text,
    which made models answer UNKNOWN. This function prefers actual text and otherwise
    loads the referenced law file.
    """
    # 1. Explicit embedded law text variants.
    if isinstance(data, dict):
        law_obj = data.get("law")
        if isinstance(law_obj, dict):
            embedded = _first_nonempty_string(
                law_obj.get("text"),
                law_obj.get("law_text"),
                law_obj.get("selected_law_text"),
                law_obj.get("scoped_law_text"),
                law_obj.get("article_text"),
                law_obj.get("legal_text"),
            )
            if embedded:
                return embedded, "embedded:law.*text"

            law_path = _first_nonempty_string(law_obj.get("path"), law_obj.get("file"), law_obj.get("filename"))
            if law_path:
                law_path_obj = Path(law_path)
                candidates: list[Path] = []
                if law_path_obj.is_absolute():
                    candidates.append(law_path_obj)
                else:
                    for root in _candidate_project_roots(json_file):
                        candidates.append(root / law_path_obj)

                for candidate in candidates:
                    if candidate.exists() and candidate.is_file():
                        return candidate.read_text(encoding="utf-8").strip(), f"file:{candidate}"

                raise FileNotFoundError(
                    f"Could not resolve law.path={law_path!r} from {json_file}. Tried: "
                    + "; ".join(str(c) for c in candidates[:8])
                )

        embedded = _first_nonempty_string(
            data.get("law_text"),
            data.get("selected_law_text"),
            data.get("scoped_law_text"),
            data.get("article_text"),
            data.get("legal_text"),
        )
        if embedded:
            return embedded, "embedded:top-level"

    # 2. Generic fallback, but do NOT accept path-like fields as law text.
    for key in ["law_text", "selected_law_text", "scoped_law_text", "article_text", "legal_text", "text_law"]:
        for path, value in flat.items():
            if path.lower().endswith(key.lower()) and isinstance(value, str) and value.strip():
                if not path.lower().endswith(".path") and not path.lower().endswith(".file"):
                    return value.strip(), f"flat:{path}"

    return None, None


def resolve_case_text(data: Any, flat: dict[str, Any]) -> tuple[str | None, str | None]:
    if isinstance(data, dict):
        case_obj = data.get("case")
        if isinstance(case_obj, dict):
            text = _first_nonempty_string(case_obj.get("text"), case_obj.get("case_text"), case_obj.get("facts"), case_obj.get("narrative"))
            if text:
                return text, "embedded:case.text"
        text = _first_nonempty_string(data.get("case_text"), data.get("facts"), data.get("case_facts"), data.get("narrative"))
        if text:
            return text, "embedded:top-level"
    return find_string(flat, CASE_KEYS), "flat:fallback"


def resolve_question_and_gold(data: Any, flat: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    if isinstance(data, dict):
        questions = data.get("questions")
        if isinstance(questions, list) and questions:
            q0 = questions[0]
            if isinstance(q0, dict):
                question = _first_nonempty_string(q0.get("text"), q0.get("question"), q0.get("question_text"), q0.get("query"))
                gold = None
                expected = q0.get("expected")
                if isinstance(expected, dict):
                    gold = normalize_label(expected.get("value")) or normalize_label(expected.get("label")) or normalize_label(expected.get("answer"))
                gold = gold or normalize_label(q0.get("expected")) or normalize_label(q0.get("gold")) or normalize_label(q0.get("answer"))
                if question:
                    return question, gold, "embedded:questions[0]"
        question = _first_nonempty_string(data.get("question"), data.get("question_text"), data.get("query"), data.get("legal_question"))
        if question:
            return question, find_gold(flat), "embedded:top-level"
    return find_string(flat, QUESTION_KEYS), find_gold(flat), "flat:fallback"


def load_task_from_run(run_path: Path) -> PlainLLMTask:
    run_id = run_path.stem if run_path.is_file() else run_path.name

    best: PlainLLMTask | None = None
    errors: list[str] = []

    for json_file in iter_json_files(run_path):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{json_file}: {exc}")
            continue

        flat = flatten_json(data)

        try:
            law_text, law_source = resolve_law_text(data, flat, json_file)
        except Exception as exc:
            errors.append(f"{json_file}: law resolution failed: {exc}")
            law_text, law_source = None, None

        case_text, case_source = resolve_case_text(data, flat)
        question, gold, question_source = resolve_question_and_gold(data, flat)

        if law_text and case_text and question:
            task = PlainLLMTask(
                run_id=run_id,
                law_text=law_text,
                case_text=case_text,
                question=question,
                gold_label=gold,
                source_file=str(json_file),
            )
            # Attach debug metadata dynamically; dataclass output remains unchanged.
            task.debug_sources = {  # type: ignore[attr-defined]
                "law_source": law_source,
                "case_source": case_source,
                "question_source": question_source,
            }
            return task

        if any([law_text, case_text, question]):
            best = PlainLLMTask(
                run_id=run_id,
                law_text=law_text or "",
                case_text=case_text or "",
                question=question or "",
                gold_label=gold,
                source_file=str(json_file),
            )

    if best:
        missing = []
        if not best.law_text:
            missing.append("law_text")
        if not best.case_text:
            missing.append("case_text")
        if not best.question:
            missing.append("question")
        raise ValueError(
            f"{run_id}: found partial task in {best.source_file}, missing {missing}. Errors: {errors[:3]}"
        )

    raise ValueError(f"{run_id}: could not find task JSON. Errors: {errors[:5]}")

def discover_runs(runs_dir: Path, runs: str) -> list[Path]:
    if runs.strip().lower() == "all":
        candidates = []
        for p in sorted(runs_dir.iterdir()):
            if p.name.startswith("run_"):
                candidates.append(p)
        return candidates

    wanted = [r.strip() for r in runs.split(",") if r.strip()]
    out = []
    for run_id in wanted:
        p_dir = runs_dir / run_id
        p_json = runs_dir / f"{run_id}.json"

        if p_dir.exists():
            out.append(p_dir)
        elif p_json.exists():
            out.append(p_json)
        else:
            raise FileNotFoundError(f"Could not find {run_id} in {runs_dir}")

    return out


def build_prompt(task: PlainLLMTask) -> list[dict[str, str]]:
    # Keep the prompt intentionally strict. Some reasoning models consume
    # completion tokens internally before emitting visible content, so the
    # caller should still provide a generous max_tokens budget.
    system = (
        "You are a strict label classifier for legal true/false/unknown questions.\n"
        "Use only the provided law text and case facts.\n"
        "Do not use outside legal knowledge.\n"
        "Do not assume facts that are not stated in the case.\n"
        "If the provided information is insufficient to determine the answer, answer UNKNOWN.\n"
        "Your entire visible response must be exactly one of these three labels:\n"
        "TRUE\n"
        "FALSE\n"
        "UNKNOWN\n"
        "Do not explain. Do not add punctuation. Do not output markdown."
    )

    user = (
        "Classify the legal question below. Think internally if needed, but output only the final label.\n\n"
        "LAW TEXT:\n"
        f"{task.law_text}\n\n"
        "CASE FACTS:\n"
        f"{task.case_text}\n\n"
        "QUESTION:\n"
        f"{task.question}\n\n"
        "Return exactly one word and nothing else: TRUE, FALSE, or UNKNOWN."
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def call_model(
    client: OpenAI,
    model: str,
    task: PlainLLMTask,
    temperature: float,
    max_tokens: int,
) -> tuple[str, str | None, dict[str, Any]]:
    messages = build_prompt(task)

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    raw_text = response.choices[0].message.content or ""
    parsed = parse_model_answer(raw_text)

    usage = {
        "finish_reason": getattr(response.choices[0], "finish_reason", None),
        "response_id": getattr(response, "id", None),
    }
    if getattr(response, "usage", None):
        usage.update({
            "prompt_tokens": getattr(response.usage, "prompt_tokens", None),
            "completion_tokens": getattr(response.usage, "completion_tokens", None),
            "total_tokens": getattr(response.usage, "total_tokens", None),
        })

    return raw_text, parsed, usage


def safe_model_dir_name(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "__", model)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", required=True, help="Input runs directory.")
    parser.add_argument("--runs", default="all", help="'all' or comma-separated run IDs.")
    parser.add_argument("--models", required=True, help="Comma-separated OpenRouter model IDs.")
    parser.add_argument("--output-dir", required=True, help="Output directory.")
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"))
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--sleep-seconds", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug-dump-tasks", type=int, default=0, help="Write the first N resolved tasks/prompts to debug_tasks.jsonl.")
    parser.add_argument("--save-prompts", action="store_true", help="Store the exact prompt messages in predictions.jsonl for auditing.")
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env) or os.getenv("OPENAI_API_KEY")
    if not api_key and not args.dry_run:
        raise RuntimeError(
            f"No API key found. Set {args.api_key_env} or OPENAI_API_KEY."
        )

    runs_dir = Path(args.runs_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_paths = discover_runs(runs_dir, args.runs)
    if args.limit is not None:
        run_paths = run_paths[: args.limit]

    tasks: list[PlainLLMTask] = []
    for run_path in run_paths:
        task = load_task_from_run(run_path)
        tasks.append(task)

    models = [m.strip() for m in args.models.split(",") if m.strip()]

    manifest = {
        "runs_dir": str(runs_dir),
        "runs": [t.run_id for t in tasks],
        "models": models,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "note": "Plain LLM baseline. Prompt contains law text, case text, and question only. No gold label included.",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )



    if args.debug_dump_tasks:
        debug_path = output_dir / "debug_tasks.jsonl"
        with debug_path.open("w", encoding="utf-8") as dbg:
            for t in tasks[: args.debug_dump_tasks]:
                dbg.write(json.dumps({
                    "run_id": t.run_id,
                    "source_file": t.source_file,
                    "debug_sources": getattr(t, "debug_sources", {}),
                    "gold_label": t.gold_label,
                    "law_preview": t.law_text[:1000],
                    "law_length": len(t.law_text),
                    "case_text": t.case_text,
                    "question": t.question,
                    "prompt": build_prompt(t),
                }, ensure_ascii=False) + "\n")
        print(f"Wrote debug task dump to {debug_path}")

    if args.dry_run:
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        for t in tasks[:3]:
            print("\n---", t.run_id, "---")
            print("DEBUG SOURCES:", getattr(t, "debug_sources", {}))
            print("LAW LENGTH:", len(t.law_text))
            print("LAW:", t.law_text[:300].replace("\n", " "))
            print("CASE:", t.case_text[:200].replace("\n", " "))
            print("QUESTION:", t.question)
            print("GOLD FOUND:", t.gold_label)
        return 0

    client = OpenAI(api_key=api_key, base_url=args.base_url)

    for model in models:
        model_dir = output_dir / safe_model_dir_name(model)
        model_dir.mkdir(parents=True, exist_ok=True)

        pred_path = model_dir / "predictions.jsonl"
        summary_path = model_dir / "summary.json"

        counts = {
            "total": 0,
            "valid_output": 0,
            "invalid_output": 0,
            "gold_available": 0,
            "correct": 0,
            "wrong": 0,
            "unknown_predicted": 0,
            "true_predicted": 0,
            "false_predicted": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        with pred_path.open("w", encoding="utf-8") as f:
            for task in tasks:
                counts["total"] += 1
                record: dict[str, Any] = {
                    "run_id": task.run_id,
                    "model": model,
                    "gold_label": task.gold_label,
                    "source_file": task.source_file,
                    "debug_sources": getattr(task, "debug_sources", {}),
                }
                if args.save_prompts:
                    record["prompt"] = build_prompt(task)

                try:
                    raw, parsed, usage = call_model(
                        client=client,
                        model=model,
                        task=task,
                        temperature=args.temperature,
                        max_tokens=args.max_tokens,
                    )

                    record["raw_response"] = raw
                    record["predicted_label"] = parsed
                    record["valid_output"] = parsed in LABELS
                    record["usage"] = usage

                    if parsed in LABELS:
                        counts["valid_output"] += 1
                        if parsed == "UNKNOWN":
                            counts["unknown_predicted"] += 1
                        elif parsed == "TRUE":
                            counts["true_predicted"] += 1
                        elif parsed == "FALSE":
                            counts["false_predicted"] += 1
                    else:
                        counts["invalid_output"] += 1

                    for k in ["prompt_tokens", "completion_tokens", "total_tokens"]:
                        if usage.get(k) is not None:
                            counts[k] += usage[k]

                    if task.gold_label:
                        counts["gold_available"] += 1
                        if parsed == task.gold_label:
                            counts["correct"] += 1
                            record["score"] = "correct"
                        elif parsed in LABELS:
                            counts["wrong"] += 1
                            record["score"] = "wrong"
                        else:
                            record["score"] = "invalid_output"

                except Exception as exc:
                    counts["errors"] += 1
                    record["error"] = repr(exc)

                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()

                if args.sleep_seconds:
                    time.sleep(args.sleep_seconds)

        total = counts["total"] or 1
        gold_available = counts["gold_available"] or 1

        summary = {
            "model": model,
            "counts": counts,
            "valid_output_rate": counts["valid_output"] / total,
            "accuracy_if_gold_available": (
                counts["correct"] / gold_available if counts["gold_available"] else None
            ),
            "wrong_rate_if_gold_available": (
                counts["wrong"] / gold_available if counts["gold_available"] else None
            ),
        }

        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("\n===", model, "===")
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())