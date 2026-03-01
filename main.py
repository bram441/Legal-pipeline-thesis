import argparse
import io
import os
import sys

from dotenv import load_dotenv

# Use UTF-8 for stdout/stderr on Windows to avoid UnicodeEncodeError from IDP/Z3 output
if sys.platform == "win32" and hasattr(sys.stdout, "fileno"):
    try:
        enc = (sys.stdout.encoding or "").lower()
        if enc and "utf" not in enc:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)
    except (AttributeError, OSError):
        pass

from debug import status_log
from pipeline.app.pipeline import answer_legal_prompt
from pipeline.io.text_runs import load_text_run, write_text_results
from pipeline.io.json_runs import load_json_run, write_json_results, write_score
from pipeline.eval.scoring import score_question
from pipeline.kb.cache import get_or_compile_kb
from pipeline.translation.translator import translate_to_english, TranslationError
from pipeline.utils.unicode_sanitize import sanitize_for_output


def run_text_mode(run_dir, provider, translate=True):
    payload = load_text_run(run_dir)

    law_text = payload["law_text"]
    case_text = payload["case_text"]
    questions = payload["questions"]

    if translate:
        try:
            status_log("Translation", "Translating law, case, and questions to English")
            law_text = translate_to_english(law_text)
            case_text = translate_to_english(case_text)
            questions = [translate_to_english(q) for q in questions]
        except TranslationError as e:
            print("Translation failed:", e)
            return

    # Compile (or reuse cached) KB once per run; use separate cache when translated
    status_log("KB", "Loading or compiling knowledge base")
    kb_text, kb_schema = get_or_compile_kb(run_dir, law_text, cache_subdir="translated" if translate else None)

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

    for i, q in enumerate(questions):
        out_lines.append("---")
        out_lines.append("Q: " + q)

        status_log("Question", "Processing {} of {}".format(i + 1, len(questions)))
        result = answer_legal_prompt(
            case_text,
            q,
            base_kb_text=kb_text,
            extractor_provider=provider,
            kb_schema=kb_schema,
        )

        if result.get("error_stage"):
            out_lines.append("ERROR STAGE: " + sanitize_for_output(str(result.get("error_stage"))))
            out_lines.append("ERROR: " + sanitize_for_output(str(result.get("error"))))
            continue

        out_lines.append("SAT? " + sanitize_for_output(str(result["sat"])))
        out_lines.append("Case: " + sanitize_for_output(str(result["case"])))
        out_lines.append("Query: " + sanitize_for_output(str(result["query"])))
        out_lines.append("Answer: " + sanitize_for_output(str(result["natural_language"])))
        if result.get("explanation"):
            out_lines.append("Explanation:")
            out_lines.append(sanitize_for_output(str(result["explanation"])))

    results_text = "\n".join(out_lines) + "\n"
    write_text_results(run_dir, results_text)
    print("Wrote:", os.path.join(run_dir, "results.txt"))


def run_json_mode(run_dir, provider, translate=True):
    run_obj = load_json_run(run_dir)

    law_text = (run_obj.get("law") or {}).get("text", "")
    case_text = (run_obj.get("case") or {}).get("text", "")
    questions = run_obj.get("questions") or []

    if translate:
        try:
            status_log("Translation", "Translating law, case, and questions to English")
            law_text = translate_to_english(law_text)
            case_text = translate_to_english(case_text)
            for i, q in enumerate(questions):
                if isinstance(q, dict) and "text" in q:
                    questions[i] = {**q, "text": translate_to_english(q.get("text", ""))}
                elif isinstance(q, str):
                    questions[i] = translate_to_english(q)
        except TranslationError as e:
            print("Translation failed:", e)
            return

    status_log("KB", "Loading or compiling knowledge base")
    kb_text, kb_schema = get_or_compile_kb(run_dir, law_text, cache_subdir="translated" if translate else None)

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

    for i, q in enumerate(questions):
        qid = q.get("id")
        qtext = q.get("text", "")
        expected = q.get("expected")

        status_log("Question", "Processing {} of {}".format(i + 1, len(questions)))
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
    parser.add_argument("--no-translate", action="store_true", help="Skip translation to English (input already in English)")
    args = parser.parse_args()

    translate = not args.no_translate
    if args.mode == "text":
        run_text_mode(args.run, args.provider, translate=translate)
    else:
        run_json_mode(args.run, args.provider, translate=translate)


if __name__ == "__main__":
    load_dotenv()
    main()
