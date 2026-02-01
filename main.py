import argparse
import os

from dotenv import load_dotenv

from pipeline.app.pipeline import answer_legal_prompt
from pipeline.io.text_runs import load_text_run, write_text_results
from pipeline.io.json_runs import load_json_run, write_json_results, write_score
from pipeline.eval.scoring import score_question
from pipeline.kb.cache import get_or_compile_kb


def run_text_mode(run_dir, provider):
    payload = load_text_run(run_dir)

    law_text = payload["law_text"]
    case_text = payload["case_text"]
    questions = payload["questions"]

    # Compile (or reuse cached) KB once per run
    kb_text, kb_schema = get_or_compile_kb(run_dir, law_text)

    out_lines = []
    out_lines.append("=== LAW (plain text input) ===")
    out_lines.append(law_text)
    out_lines.append("")
    out_lines.append("=== KB USED (kb.fo) ===")
    out_lines.append(kb_text)
    out_lines.append("")
    out_lines.append("=== CASE ===")
    out_lines.append(case_text)
    out_lines.append("")

    for q in questions:
        out_lines.append("---")
        out_lines.append("Q: " + q)

        result = answer_legal_prompt(
            case_text,
            q,
            base_kb_text=kb_text,
            extractor_provider=provider,
            kb_schema=kb_schema,
        )

        if result.get("error_stage"):
            out_lines.append("ERROR STAGE: " + str(result.get("error_stage")))
            out_lines.append("ERROR: " + str(result.get("error")))
            continue

        out_lines.append("SAT? " + str(result["sat"]))
        out_lines.append("Case: " + str(result["case"]))
        out_lines.append("Query: " + str(result["query"]))
        out_lines.append("Answer: " + str(result["natural_language"]))
        if result.get("explanation"):
            out_lines.append("Explanation:")
            out_lines.append(str(result["explanation"]))

    results_text = "\n".join(out_lines) + "\n"
    write_text_results(run_dir, results_text)
    print("Wrote:", os.path.join(run_dir, "results.txt"))


def run_json_mode(run_dir, provider):
    run_obj = load_json_run(run_dir)

    law_text = (run_obj.get("law") or {}).get("text", "")
    case_text = (run_obj.get("case") or {}).get("text", "")
    questions = run_obj.get("questions") or []

    kb_text, kb_schema = get_or_compile_kb(run_dir, law_text)

    results = {
        "id": run_obj.get("id"),
        "law": {"text": law_text},
        "kb_used": {"fo": kb_text},
        "case": {"text": case_text},
        "questions": [],
    }

    score = {
        "id": run_obj.get("id"),
        "total": 0,
        "correct": 0,
        "items": [],
    }

    for q in questions:
        qid = q.get("id")
        qtext = q.get("text", "")
        expected = q.get("expected")

        result = answer_legal_prompt(
            case_text,
            qtext,
            base_kb_text=kb_text,
            extractor_provider=provider,
            kb_schema=kb_schema,
        )

        item = {
            "id": qid,
            "text": qtext,
            "expected": expected,
            "pipeline": result,
        }
        results["questions"].append(item)

        if expected is not None and not result.get("error_stage"):
            score_item = score_question(expected, result.get("symbolic_result"))
            score_item["id"] = qid
            score_item["text"] = qtext

            score["total"] += 1
            if score_item.get("match"):
                score["correct"] += 1

            score["items"].append(score_item)

    if score["total"] > 0:
        score["accuracy"] = score["correct"] / score["total"]
    else:
        score["accuracy"] = None

    write_json_results(run_dir, results)
    write_score(run_dir, score)

    print("Wrote:", os.path.join(run_dir, "results.json"))
    print("Wrote:", os.path.join(run_dir, "score.json"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["text", "json"], required=True)
    parser.add_argument("--run", required=True, help="Path to run folder (e.g., inputs/text/run_001)")
    parser.add_argument("--provider", choices=["auto", "openai"], default="auto")
    args = parser.parse_args()

    if args.mode == "text":
        run_text_mode(args.run, args.provider)
    else:
        run_json_mode(args.run, args.provider)


if __name__ == "__main__":
    load_dotenv()
    main()
