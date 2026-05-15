import argparse
from contextlib import ExitStack
import io
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root so it works when run from any directory
_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")

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
from pipeline.extraction.extractor import (
    extract_case_only,
    ExtractionError,
    extraction_backend_env_override,
    get_extraction_backend_from_env,
)
from pipeline.io.text_runs import load_text_run, write_text_results
from pipeline.io.json_runs import load_json_run, write_json_results, write_score, merge_json_run_file
from pipeline.eval.scoring import score_question
from pipeline.kb.cache import get_or_compile_kb
from pipeline.kb.compile_backend import KB_BACKEND_CHOICES, get_kb_backend_from_env, kb_backend_env_override
from pipeline.kb.compile_strategy import kb_run_context, strategy_to_flags, STRATEGY_CHOICES
from pipeline.utils.run_trace import trace_enabled
from pipeline.translation.translator import translate_to_english, TranslationError
from pipeline.utils.unicode_sanitize import sanitize_for_output


def _resolve_backends(cli_pipeline_backend=None, cli_kb_backend=None):
    """
    Unified backend mode:
      - pipeline_backend=legacy -> kb=legacy_fo, extraction=legacy
      - pipeline_backend=json_ir -> kb=json_ir, extraction=json_ir
    When pipeline is unset and --kb-backend is unset, KB and extraction follow
    environment (defaults: both json_ir; set PIPELINE_*_BACKEND to override).
    """
    if cli_pipeline_backend is None:
        if cli_kb_backend is None:
            return get_kb_backend_from_env(), get_extraction_backend_from_env()
        if cli_kb_backend == "legacy_fo":
            return "legacy_fo", "legacy"
        if cli_kb_backend == "json_ir":
            return "json_ir", "json_ir"
        raise ValueError("Unknown kb backend: " + str(cli_kb_backend))
    if cli_pipeline_backend == "legacy":
        return "legacy_fo", "legacy"
    if cli_pipeline_backend == "json_ir":
        return "json_ir", "json_ir"
    raise ValueError("Unknown pipeline backend: " + str(cli_pipeline_backend))


def _effective_pipeline_backend_label(cli_pipeline_backend, resolved_kb_backend, resolved_extraction_backend):
    if cli_pipeline_backend in ("legacy", "json_ir"):
        return cli_pipeline_backend
    # If both were explicitly resolved together by other means, infer a clean label.
    if resolved_kb_backend == "legacy_fo" and resolved_extraction_backend == "legacy":
        return "legacy"
    if resolved_kb_backend == "json_ir" and resolved_extraction_backend == "json_ir":
        return "json_ir"
    # Environment/default/manual mix (still useful to expose explicitly).
    return "mixed"


def _warn_cli_backend_mismatch(cli_pipeline_backend, cli_kb_backend):
    """When both CLI flags are set, ``--pipeline-backend`` wins; warn if they disagree."""
    if not cli_pipeline_backend or cli_kb_backend is None:
        return
    implied = "json_ir" if cli_pipeline_backend == "json_ir" else "legacy_fo"
    if cli_kb_backend != implied:
        print(
            "Warning: --kb-backend %r is ignored when --pipeline-backend %r is set "
            "(effective KB backend is %r)."
            % (cli_kb_backend, cli_pipeline_backend, implied),
            file=sys.stderr,
        )


def run_text_mode(run_dir, provider, translate=True, cli_kb_strategy=None, cli_kb_backend=None, cli_pipeline_backend=None):
    payload = load_text_run(run_dir)

    law_text = payload["law_text"]
    case_text = payload["case_text"]
    questions = payload["questions"]

    ctx, strategy_label = kb_run_context(cli_strategy=cli_kb_strategy, run_json=None, mode="text")
    ul, tp = strategy_to_flags(strategy_label)

    if translate:
        try:
            status_log("Translation", "Translating law, case, and questions to English")
            law_text = translate_to_english(law_text)
            case_text = translate_to_english(case_text)
            questions = [translate_to_english(q) for q in questions]
        except TranslationError as e:
            print("Translation failed:", e)
            return

    resolved_kb_backend, resolved_extraction_backend = _resolve_backends(
        cli_pipeline_backend=cli_pipeline_backend,
        cli_kb_backend=cli_kb_backend,
    )
    _warn_cli_backend_mismatch(cli_pipeline_backend, cli_kb_backend)
    pipeline_backend_label = _effective_pipeline_backend_label(
        cli_pipeline_backend, resolved_kb_backend, resolved_extraction_backend
    )

    with ExitStack() as stack:
        stack.enter_context(ctx)
        stack.enter_context(kb_backend_env_override(resolved_kb_backend))
        stack.enter_context(extraction_backend_env_override(resolved_extraction_backend))
        status_log("KB", "Loading or compiling knowledge base")
        kb_text, kb_schema = get_or_compile_kb(run_dir, law_text, cache_subdir="translated" if translate else None)
        backend_label = get_kb_backend_from_env()

        out_lines = []
        out_lines.append("=== KB COMPILE STRATEGY ===")
        out_lines.append(strategy_label + " (use_le=" + str(ul) + ", two_phase=" + str(tp) + ")")
        out_lines.append("KB backend: " + backend_label)
        out_lines.append("Extraction backend: " + resolved_extraction_backend)
        out_lines.append("Pipeline backend mode: " + pipeline_backend_label)
        out_lines.append("")
        out_lines.append("=== LAW (plain text input) ===")
        out_lines.append(law_text)
        out_lines.append("")
        out_lines.append("=== KB USED (kb.fo) ===")
        out_lines.append(kb_text)
        out_lines.append("")
        out_lines.append("=== CASE ===")
        out_lines.append(case_text)
        out_lines.append("")

        pre_extracted_case = None
        try:
            status_log("Case", "Extracting case once for all questions")
            pre_extracted_case = extract_case_only(case_text, kb_schema=kb_schema, provider=provider)
        except ExtractionError as e:
            print("Case extraction failed:", e)
            return

        for i, q in enumerate(questions):
            out_lines.append("---")
            out_lines.append("Q: " + q)

            status_log("Question", "Processing {} of {}".format(i + 1, len(questions)))
            trace_path = os.path.join(run_dir, "run_trace.txt") if trace_enabled() else None
            result = answer_legal_prompt(
                case_text,
                q,
                base_kb_text=kb_text,
                extractor_provider=provider,
                kb_schema=kb_schema,
                trace_path=trace_path,
                pre_extracted_case=pre_extracted_case,
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


def run_json_mode(run_dir, provider, translate=True, cli_kb_strategy=None, cli_kb_backend=None, cli_pipeline_backend=None):
    run_obj = load_json_run(run_dir)

    law_obj = run_obj.get("law") or {}
    law_text = (law_obj.get("text") or "").strip()
    law_path = law_obj.get("path")
    if not law_text and law_path:
        lp = (_PROJECT_ROOT / str(law_path).replace("\\", "/")).resolve()
        if not lp.is_file():
            print("Law file not found:", lp)
            return
        law_text = lp.read_text(encoding="utf-8")
    case_text = (run_obj.get("case") or {}).get("text", "")
    questions = run_obj.get("questions") or []

    ctx, strategy_label = kb_run_context(cli_strategy=cli_kb_strategy, run_json=run_obj, mode="json")
    ul, tp = strategy_to_flags(strategy_label)

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

    resolved_kb_backend, resolved_extraction_backend = _resolve_backends(
        cli_pipeline_backend=cli_pipeline_backend,
        cli_kb_backend=cli_kb_backend,
    )
    _warn_cli_backend_mismatch(cli_pipeline_backend, cli_kb_backend)
    pipeline_backend_label = _effective_pipeline_backend_label(
        cli_pipeline_backend, resolved_kb_backend, resolved_extraction_backend
    )

    with ExitStack() as stack:
        stack.enter_context(ctx)
        stack.enter_context(kb_backend_env_override(resolved_kb_backend))
        stack.enter_context(extraction_backend_env_override(resolved_extraction_backend))
        status_log("KB", "Loading or compiling knowledge base")
        q_text = ""
        if questions:
            q0 = questions[0]
            q_text = (q0.get("text", "") if isinstance(q0, dict) else str(q0)) or ""
        kb_text, kb_schema = get_or_compile_kb(
            run_dir,
            law_text,
            cache_subdir="translated" if translate else None,
            question_text=q_text,
            case_text=case_text,
        )
        backend_label = get_kb_backend_from_env()

        results = {
            "id": run_obj.get("id"),
            "law": {"text": law_text},
            "kb_used": {"fo": kb_text},
            "case": {"text": case_text},
            "kb_compile_strategy": strategy_label,
            "kb_compile_backend": backend_label,
            "extraction_backend": resolved_extraction_backend,
            "pipeline_backend_mode": pipeline_backend_label,
            "kb_compile_flags": {"use_le": ul, "two_phase": tp},
            "questions": [],
        }

        score = {
            "id": run_obj.get("id"),
            "total": 0,
            "correct": 0,
            "correct_decisive": 0,
            "incorrect_decisive": 0,
            "inconclusive": 0,
            "scoring_mode": "decisive",
            "items": [],
            "kb_compile_strategy": strategy_label,
            "pipeline_backend_mode": pipeline_backend_label,
            "extraction_backend": resolved_extraction_backend,
        }

        pre_extracted_case = None
        try:
            status_log("Case", "Extracting case once for all questions")
            pre_extracted_case = extract_case_only(case_text, kb_schema=kb_schema, provider=provider)
        except ExtractionError as e:
            print("Case extraction failed:", e)
            return

        for i, q in enumerate(questions):
            qid = q.get("id")
            qtext = q.get("text", "")
            expected = q.get("expected")

            status_log("Question", "Processing {} of {}".format(i + 1, len(questions)))
            trace_path = os.path.join(run_dir, "run_trace.txt") if trace_enabled() else None
            result = answer_legal_prompt(
                case_text,
                qtext,
                base_kb_text=kb_text,
                extractor_provider=provider,
                kb_schema=kb_schema,
                trace_path=trace_path,
                pre_extracted_case=pre_extracted_case,
            )

            item = {
                "id": qid,
                "text": qtext,
                "expected": expected,
                "pipeline": result,
            }
            results["questions"].append(item)

            if expected is not None and not result.get("error_stage"):
                score_item = score_question(
                    expected,
                    result.get("symbolic_result"),
                    query=result.get("query"),
                    kb_schema=kb_schema,
                    user_question=qtext,
                )
                score_item["id"] = qid
                score_item["text"] = qtext

                score["total"] += 1
                if score_item.get("inconclusive"):
                    score["inconclusive"] += 1
                elif score_item.get("match"):
                    score["correct"] += 1
                    score["correct_decisive"] += 1
                else:
                    score["incorrect_decisive"] += 1

                score["items"].append(score_item)

        if any(it.get("scoring_mode") == "belief" or it.get("belief_scored") for it in score["items"]):
            score["scoring_mode"] = "belief"

        decisive_answered = score["total"] - score["inconclusive"]
        score["decisive"] = decisive_answered
        if score["total"] > 0:
            score["accuracy_decisive"] = score["correct"] / score["total"]
            score["accuracy"] = score["accuracy_decisive"]
        else:
            score["accuracy_decisive"] = None
            score["accuracy"] = None
        if decisive_answered > 0:
            score["accuracy_on_decisive_only"] = score["correct"] / decisive_answered
        else:
            score["accuracy_on_decisive_only"] = None

        write_json_results(run_dir, results)
        write_score(run_dir, score)

        merge_json_run_file(
            run_dir,
            {
                "kb_compile_strategy": strategy_label,
                "kb_compile_backend": backend_label,
                "extraction_backend": resolved_extraction_backend,
                "pipeline_backend_mode": pipeline_backend_label,
                "kb_compile_flags": {"use_le": ul, "two_phase": tp},
            },
        )

        print("Wrote:", os.path.join(run_dir, "results.json"))
        print("Wrote:", os.path.join(run_dir, "score.json"))
        print("KB strategy:", strategy_label, "(use_le=" + str(ul) + ", two_phase=" + str(tp) + ")")
        print("KB backend:", backend_label)
        print("Extraction backend:", resolved_extraction_backend)
        print("Pipeline backend mode:", pipeline_backend_label)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["text", "json"], required=True)
    parser.add_argument("--run", required=True, help="Path to run folder (e.g., inputs/text/run_001)")
    parser.add_argument("--provider", choices=["auto", "openai"], default="auto")
    parser.add_argument("--no-translate", action="store_true", help="Skip translation to English (input already in English)")
    parser.add_argument(
        "--kb-strategy",
        metavar="NAME",
        default=None,
        help="KB compilation: one of "
        + ", ".join(STRATEGY_CHOICES)
        + ". Overrides run.json and .env for this process during the run.",
    )
    parser.add_argument(
        "--kb-backend",
        metavar="NAME",
        default=None,
        help="KB compiler backend: one of "
        + ", ".join(KB_BACKEND_CHOICES)
        + ". Default: from PIPELINE_KB_BACKEND or json_ir.",
    )
    parser.add_argument(
        "--pipeline-backend",
        metavar="NAME",
        default=None,
        help="Unified pipeline backend: 'legacy' (legacy KB + legacy extraction) or "
        "'json_ir' (JSON-IR KB + JSON-IR extraction). When omitted, KB and extraction "
        "follow env (defaults: json_ir).",
    )
    args = parser.parse_args()

    if args.kb_strategy is not None and args.kb_strategy not in STRATEGY_CHOICES:
        parser.error("--kb-strategy must be one of: " + ", ".join(STRATEGY_CHOICES))
    if args.kb_backend is not None and args.kb_backend not in KB_BACKEND_CHOICES:
        parser.error("--kb-backend must be one of: " + ", ".join(KB_BACKEND_CHOICES))
    if args.pipeline_backend is not None and args.pipeline_backend not in ("legacy", "json_ir"):
        parser.error("--pipeline-backend must be one of: legacy, json_ir")

    run_path = Path(args.run)
    if not run_path.is_absolute():
        run_path = _PROJECT_ROOT / run_path
    run_dir = str(run_path.resolve())

    translate = not args.no_translate
    if args.mode == "text":
        run_text_mode(
            run_dir,
            args.provider,
            translate=translate,
            cli_kb_strategy=args.kb_strategy,
            cli_kb_backend=args.kb_backend,
            cli_pipeline_backend=args.pipeline_backend,
        )
    else:
        run_json_mode(
            run_dir,
            args.provider,
            translate=translate,
            cli_kb_strategy=args.kb_strategy,
            cli_kb_backend=args.kb_backend,
            cli_pipeline_backend=args.pipeline_backend,
        )


if __name__ == "__main__":
    main()
