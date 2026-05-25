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
from pipeline.extraction.case_fact_validation import CASE_EXTRACTION_REPAIR_ARTIFACT
from pipeline.extraction.extractor import extract_case_only, ExtractionError
from pipeline.io.text_runs import load_text_run, write_text_results
from pipeline.io.json_runs import load_json_run, write_json_results, write_score, merge_json_run_file
from pipeline.eval.scoring import score_question
from pipeline.kb.cache import get_or_compile_kb
from pipeline.kb.schema_environment import build_schema_environment
from pipeline.kb.compile_strategy import (
    STRATEGY_CHOICES,
    get_strategy_spec,
    kb_run_context,
    resolve_translate,
    strategy_metadata,
    strategy_to_flags,
)
from pipeline.utils.run_trace import trace_enabled
from pipeline.translation.translator import translate_to_english, TranslationError
from pipeline.utils.unicode_sanitize import sanitize_for_output


def run_text_mode(
    run_dir,
    provider,
    *,
    cli_no_translate: bool = False,
    cli_kb_strategy=None,
):
    payload = load_text_run(run_dir)

    law_text = payload["law_text"]
    case_text = payload["case_text"]
    questions = payload["questions"]

    ctx, strategy_label = kb_run_context(cli_strategy=cli_kb_strategy, run_json=None, mode="text")
    ul, tp = strategy_to_flags(strategy_label)
    translate = resolve_translate(strategy_label, cli_no_translate=cli_no_translate)
    spec = get_strategy_spec(strategy_label)

    if translate:
        try:
            status_log("Translation", "Translating law, case, and questions to English")
            law_text = translate_to_english(law_text)
            case_text = translate_to_english(case_text)
            questions = [translate_to_english(q) for q in questions]
        except TranslationError as e:
            print("Translation failed:", e)
            return

    with ExitStack() as stack:
        stack.enter_context(ctx)
        status_log("KB", "Loading or compiling knowledge base")
        kb_text, kb_schema = get_or_compile_kb(run_dir, law_text, cache_subdir="translated" if translate else None)
        schema_environment = build_schema_environment(kb_schema) if kb_schema else None

        out_lines = []
        out_lines.append("=== KB COMPILE STRATEGY ===")
        out_lines.append(strategy_label + " (use_le=" + str(ul) + ")")
        out_lines.append("KB backend: json_ir")
        out_lines.append("Extraction backend: json_ir")
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
            pre_extracted_case = extract_case_only(
                case_text,
                kb_schema=kb_schema,
                schema_environment=schema_environment,
                provider=provider,
                repair_artifact_path=os.path.join(run_dir, CASE_EXTRACTION_REPAIR_ARTIFACT),
            )
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
                schema_environment=schema_environment,
                trace_path=trace_path,
                pre_extracted_case=pre_extracted_case,
                run_artifact_dir=run_dir,
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


def run_json_mode(
    run_dir,
    provider,
    *,
    cli_no_translate: bool = False,
    cli_kb_strategy=None,
):
    run_obj = load_json_run(run_dir)

    try:
        from pipeline.config import save_effective_config

        save_effective_config(os.path.join(run_dir, "effective_config.json"))
    except Exception:
        pass

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
    try:
        from pipeline.utils.llm_call_tracker import set_run_context

        set_run_context(
            run_id=str(run_obj.get("id") or Path(run_dir).name),
            strategy=strategy_label,
            artifact_dir=run_dir,
        )
    except Exception:
        pass
    ul, tp = strategy_to_flags(strategy_label)
    translate = resolve_translate(strategy_label, cli_no_translate=cli_no_translate)
    spec = get_strategy_spec(strategy_label)

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

    smeta = strategy_metadata(
        strategy_label,
        cli_no_translate=cli_no_translate,
        translation_source_prefix="main_",
    )
    warn = smeta.get("translation_override_warning")
    if warn:
        print("Warning:", warn, file=sys.stderr)

    with ExitStack() as stack:
        stack.enter_context(ctx)
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
        schema_environment = build_schema_environment(kb_schema) if kb_schema else None

        fc_diag_src = os.path.join(run_dir, "json_ir_compile", "factual_criteria_mode_diagnostics.json")
        if os.path.isfile(fc_diag_src):
            try:
                import shutil

                shutil.copy2(
                    fc_diag_src,
                    os.path.join(run_dir, "factual_criteria_mode_diagnostics.json"),
                )
            except OSError:
                pass

        results = {
            "id": run_obj.get("id"),
            "law": {"text": law_text},
            "kb_used": {"fo": kb_text},
            "case": {"text": case_text},
            "kb_compile_strategy": strategy_label,
            "kb_compile_backend": "json_ir",
            "extraction_backend": "json_ir",
            "pipeline_backend_mode": "json_ir",
            "kb_compile_flags": {
                "use_le": ul,
                "uses_translation": translate,
                "json_ir_generation": spec.json_ir_generation,
            },
            "strategy_metadata": smeta,
            "questions": [],
        }

        from pipeline.kb.factual_criteria import (
            collect_case_asserted_factual_criteria,
            pragmatic_factual_criteria_mode_enabled,
        )

        score = {
            "id": run_obj.get("id"),
            "pragmatic_factual_criteria_mode": pragmatic_factual_criteria_mode_enabled(),
            "total": 0,
            "correct": 0,
            "correct_decisive": 0,
            "incorrect_decisive": 0,
            "inconclusive": 0,
            "scoring_mode": "decisive",
            "items": [],
            "kb_compile_strategy": strategy_label,
            "pipeline_backend_mode": "json_ir",
            "extraction_backend": "json_ir",
            "strategy_metadata": smeta,
        }

        pre_extracted_case = None
        try:
            status_log("Case", "Extracting case once for all questions")
            pre_extracted_case = extract_case_only(
                case_text,
                kb_schema=kb_schema,
                schema_environment=schema_environment,
                provider=provider,
                repair_artifact_path=os.path.join(run_dir, CASE_EXTRACTION_REPAIR_ARTIFACT),
            )
        except ExtractionError as e:
            print("Case extraction failed:", e)
            return

        for i, q in enumerate(questions):
            qid = q.get("id")
            qtext = q.get("text", "")
            expected = q.get("expected")

            status_log("Question", "Processing {} of {}".format(i + 1, len(questions)))
            trace_path = os.path.join(run_dir, "run_trace.txt") if trace_enabled() else None
            q_artifact = os.path.join(run_dir, "questions", str(qid or "q"))
            result = answer_legal_prompt(
                case_text,
                qtext,
                base_kb_text=kb_text,
                extractor_provider=provider,
                kb_schema=kb_schema,
                schema_environment=schema_environment,
                trace_path=trace_path,
                pre_extracted_case=pre_extracted_case,
                run_artifact_dir=run_dir,
                question_artifact_dir=q_artifact,
                expected_answer=expected,
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
                score_item["pragmatic_factual_criteria_mode"] = pragmatic_factual_criteria_mode_enabled()
                fc_assert = collect_case_asserted_factual_criteria(
                    result.get("case"),
                    kb_schema,
                    case_text=case_text,
                    query_predicate=str((result.get("query") or {}).get("predicate") or ""),
                )
                asserted_preds = [
                    e.get("predicate")
                    for e in (fc_assert.get("asserted") or [])
                    if isinstance(e, dict) and e.get("predicate")
                ]
                score_item["factual_criteria_used"] = bool(asserted_preds)
                score_item["factual_criteria_predicates"] = asserted_preds
                if isinstance(result.get("query"), dict):
                    qmeta = result["query"]
                else:
                    qmeta = result.get("query") or {}
                if isinstance(qmeta, dict):
                    score_item["query_type"] = qmeta.get("query_type")
                    score_item["internal_intent"] = qmeta.get("internal_intent") or (
                        result.get("symbolic_result") or {}
                    ).get("intent")
                sym = result.get("symbolic_result") or {}
                routing = result.get("symbolic_intent_routing") or sym.get("routing") or {}
                if isinstance(sym, dict):
                    score_item["output_kind"] = sym.get("output_kind")
                    score_item["certainty_class"] = sym.get("certainty_class") or score_item.get("certainty_class")
                    score_item["symbolic_status"] = sym.get("symbolic_status") or sym.get("status")
                    score_item["selected_intent"] = sym.get("selected_intent") or routing.get("selected_intent")
                    score_item["detected_question_type"] = sym.get("detected_question_type") or routing.get(
                        "detected_question_type"
                    )
                    sat_chk = sym.get("satisfiability_check") or {}
                    score_item["satisfiability_status"] = sat_chk.get("status")
                    if sym.get("symbolic_status") in ("unsupported",) or sym.get("status") == "unsupported":
                        score_item["unsupported_intent_reason"] = sym.get("message")

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
                "kb_compile_backend": "json_ir",
                "extraction_backend": "json_ir",
                "pipeline_backend_mode": "json_ir",
                "kb_compile_flags": {
                    "use_le": ul,
                    "uses_translation": translate,
                    "json_ir_generation": spec.json_ir_generation,
                },
                "strategy_metadata": smeta,
            },
        )

        print("Wrote:", os.path.join(run_dir, "results.json"))
        print("Wrote:", os.path.join(run_dir, "score.json"))
        print("KB strategy:", strategy_label, "(use_le=" + str(ul) + ")")
        print("Translation:", translate, "| json_ir_generation:", spec.json_ir_generation)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["text", "json"], required=True)
    parser.add_argument("--run", required=True, help="Path to run folder (e.g., inputs/text/run_001)")
    parser.add_argument("--provider", choices=["auto", "openai"], default="auto")
    parser.add_argument(
        "--no-translate",
        action="store_true",
        help="Skip translation to English. Overrides the strategy's translate setting when --kb-strategy is set.",
    )
    parser.add_argument(
        "--kb-strategy",
        metavar="NAME",
        default=None,
        help="KB compilation: one of "
        + ", ".join(STRATEGY_CHOICES)
        + ". Overrides run.json and .env for this process during the run.",
    )
    args = parser.parse_args()

    if args.kb_strategy is not None and args.kb_strategy not in STRATEGY_CHOICES:
        parser.error("--kb-strategy must be one of: " + ", ".join(STRATEGY_CHOICES))

    run_path = Path(args.run)
    if not run_path.is_absolute():
        run_path = _PROJECT_ROOT / run_path
    run_dir = str(run_path.resolve())

    if args.mode == "text":
        run_text_mode(
            run_dir,
            args.provider,
            cli_no_translate=args.no_translate,
            cli_kb_strategy=args.kb_strategy,
        )
    else:
        run_json_mode(
            run_dir,
            args.provider,
            cli_no_translate=args.no_translate,
            cli_kb_strategy=args.kb_strategy,
        )


if __name__ == "__main__":
    from pipeline.utils.llm_call_tracker import LLMBudgetExceeded, apply_budget_from_env

    apply_budget_from_env()
    try:
        main()
    except LLMBudgetExceeded:
        raise SystemExit(1)
