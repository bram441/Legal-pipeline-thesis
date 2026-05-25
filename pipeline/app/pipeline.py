import json
import re

from debug import debug_log, status_log

from pipeline.eval.boolean_belief import summarize_boolean_symbolic
from pipeline.extraction.extractor import extract_case_and_query, extract_case_only, extract_query_only, ExtractionError
from pipeline.symbolic.router import run_query
from pipeline.rendering.answer_renderer import render_answer
from pipeline.validation.fo_validation import normalize_and_validate_case, normalize_and_validate_query
from pipeline.validation.pre_solver_validation import (
    CaseSchemaValidationError,
    PreSolverDomainValidationError,
    prepare_case_for_symbolic,
)
from pipeline.utils.prompt_loader import render_prompt
from pipeline.utils.run_trace import RunTraceWriter
from pipeline.domain.seeding import seed_entities_from_case_text

_ENTITY_NOISE_TOKENS = frozenset({"bv", "nv", "sa", "llc", "ltd", "inc"})

def _build_prediction_summary(query, symbolic_result):
    """Machine-readable prediction summary for evaluation traces."""
    if not isinstance(query, dict) or not isinstance(symbolic_result, dict):
        return None
    intent = symbolic_result.get("intent") or query.get("internal_intent") or query.get("intent")
    base = {
        "query_type": query.get("query_type"),
        "internal_intent": intent,
        "output_kind": symbolic_result.get("output_kind"),
        "status": symbolic_result.get("status", "ok"),
        "certainty_class": symbolic_result.get("certainty_class"),
    }
    ok = symbolic_result.get("status", "ok") == "ok"
    if not ok:
        base["message"] = symbolic_result.get("message")
        return base

    if symbolic_result.get("output_kind") == "epistemic_boolean" or query.get("mode") == "boolean":
        summ = summarize_boolean_symbolic(symbolic_result)
        base.update(
            {
                "mode": "boolean",
                "label": symbolic_result.get("label") or summ["label"],
                "belief_yes": summ["p_yes"],
                "credence_yes_pct": summ["credence_yes_pct"],
                "verdict_strength_pct": summ["verdict_strength_pct"],
            }
        )
        return base

    if symbolic_result.get("output_kind") == "entity_set" or query.get("mode") == "set":
        base.update(
            {
                "mode": "set",
                "certain_set": symbolic_result.get("entailed") or symbolic_result.get("certain", []),
                "possible_set": symbolic_result.get("unknown") or symbolic_result.get("possible", []),
            }
        )
        return base

    if intent == "propagation":
        base["certain_true_count"] = len(symbolic_result.get("certain_true") or [])
        return base
    if intent == "model_expansion":
        base["model_count"] = len(symbolic_result.get("models") or [])
        base["certainty_class"] = "possible_model"
        return base
    if intent == "get_range":
        base["values"] = symbolic_result.get("values") or []
        return base
    if intent == "satisfiable":
        base["satisfiable"] = symbolic_result.get("satisfiable")
        return base

    return base


def answer_legal_prompt(
    case_text,
    user_question,
    base_kb_text,
    extractor_provider="auto",
    extractor_model=None,
    extractor_max_retries=6,
    kb_schema=None,
    schema_environment=None,
    debug=False,
    trace_path=None,
    pre_extracted_case=None,
    run_artifact_dir=None,
):
    """Run the full pipeline for a single (case_text, user_question).

    Flow
    1) LLM extraction -> raw {case, query}
    2) normalization + strict schema validation
    3) symbolic reasoning via IDP-Z3 (intent router)
    4) render answer + optional explanation
    """
    debug_log("pipeline.answer_legal_prompt", "start")

    if run_artifact_dir:
        try:
            import os

            from pipeline.config import save_effective_config

            save_effective_config(os.path.join(run_artifact_dir, "effective_config.json"))
        except Exception:
            pass

    # --- deterministic intent forcing for text-mode experiments ---
    forced_query = None
    original_question = user_question or ""
    q_strip = original_question.strip()
    if q_strip.lower().startswith("@intent"):
        rest = q_strip[len("@intent"):].strip()
        if rest.startswith(":"):
            rest = rest[1:].strip()
        intent_name = rest.split()[0].strip() if rest else ""
        if not intent_name:
            return {
                "sat": None,
                "case": None,
                "query": None,
                "symbolic_result": None,
                "natural_language": None,
                "explanation": None,
                "extraction_prompt": None,
                "raw_extracted": None,
                "error_stage": "validation",
                "error": "Intent directive missing intent name. Use '@intent satisfiable'.",
            }

        forced_query = {
            "type": "intent",
            "intent": intent_name.lower(),
            "explain": False,
        }
        user_question = "(intent directive)"

    # For result metadata/debugging only. Actual extraction uses
    # prompts/extraction/openai_extract_{case,query}_prompt.txt (see openai_extractor.py).
    extraction_prompt = render_prompt(
        "extraction/extraction_debug_prompt.txt",
        case_text=case_text,
        user_question=user_question,
        kb_schema_json=json.dumps(kb_schema, ensure_ascii=False, indent=2),
    )

    trace = RunTraceWriter(trace_path, append=True) if trace_path else None

    if pre_extracted_case is not None:
        status_log("Extraction", "Using pre-extracted case, extracting query only")
        raw = {"case": dict(pre_extracted_case), "query": None}
        try:
            raw["query"] = extract_query_only(
                user_question,
                raw["case"],
                kb_schema=kb_schema,
                schema_environment=schema_environment,
                provider=extractor_provider,
                model=extractor_model,
                max_retries=extractor_max_retries,
                case_text=case_text,
            )
        except ExtractionError as e:
            if trace:
                trace.section("QUESTION: " + (user_question[:60] + "..." if len(user_question) > 60 else user_question))
                trace.log_error("Query extraction failed", e)
                trace.close()
            return {
                "sat": None,
                "case": raw["case"],
                "query": None,
                "symbolic_result": None,
                "natural_language": None,
                "explanation": None,
                "extraction_prompt": None,
                "raw_extracted": raw,
                "error_stage": "extraction",
                "error": str(e),
            }
    else:
        status_log("Extraction", "Extracting case and query")
        debug_log("pipeline.answer_legal_prompt", "extraction_provider=" + str(extractor_provider))
        try:
            raw = extract_case_and_query(
                case_text,
                user_question,
                kb_schema=kb_schema,
                schema_environment=schema_environment,
                provider=extractor_provider,
                model=extractor_model,
                max_retries=extractor_max_retries,
                run_artifact_dir=run_artifact_dir,
            )
        except ExtractionError as e:
            if trace:
                trace.section("QUESTION: " + (user_question[:60] + "..." if len(user_question) > 60 else user_question))
                trace.log_error("Extraction failed", e)
                trace.close()
            return {
                "sat": None,
                "case": None,
                "query": None,
                "symbolic_result": None,
                "natural_language": None,
                "explanation": None,
                "extraction_prompt": extraction_prompt,
                "raw_extracted": None,
                "error_stage": "extraction",
                "error": str(e),
            }

    if trace:
        trace.section("QUESTION: " + (user_question[:80] + "..." if len(user_question) > 80 else user_question))
        trace.log("Raw extracted (case)", json.dumps(raw.get("case"), indent=2, ensure_ascii=False))
        trace.log("Raw extracted (query)", json.dumps(raw.get("query"), indent=2, ensure_ascii=False))

    debug_log("pipeline.answer_legal_prompt", "normalize+validate")
    try:
        from pipeline.kb.case_given_bridge import augment_kb_for_case_given
        from pipeline.kb.schema_environment import build_schema_environment

        raw_case = raw.get("case")
        if (
            kb_schema
            and isinstance(raw_case, dict)
            and raw_case.get("case_given_factual_inputs")
        ):
            base_kb_text, kb_schema = augment_kb_for_case_given(
                base_kb_text,
                kb_schema,
                raw_case,
            )
            if schema_environment:
                schema_environment = build_schema_environment(kb_schema)

        case = normalize_and_validate_case(raw_case, kb_schema=kb_schema)

        # optional domain seeding (kept separate from validation)
        if isinstance(case, dict) and "entities" not in case:
            seeded = seed_entities_from_case_text(case_text)
            if seeded and kb_schema:
                # Use primary (first-declared) type from KB for domain alignment
                from pipeline.kb.schema import get_primary_type_from_kb
                primary = get_primary_type_from_kb(base_kb_text)
                if primary:
                    case["entities"] = {primary: seeded}
        # filter entities from extractor if present (remove common non-entity words)
        if isinstance(case, dict) and "entities" in case and isinstance(case["entities"], dict):
            from pipeline.domain.seeding import _NON_ENTITY_WORDS
            filtered = {}
            for t, vals in case["entities"].items():
                if isinstance(vals, list):
                    filtered[t] = [v for v in vals if isinstance(v, str) and v.strip().lower() not in _NON_ENTITY_WORDS]
                else:
                    filtered[t] = vals
            for t, vals in list(filtered.items()):
                if isinstance(vals, list):
                    filtered[t] = [
                        v
                        for v in vals
                        if isinstance(v, str)
                        and v.strip()
                        and v.strip().lower() not in _ENTITY_NOISE_TOKENS
                        and not re.fullmatch(r"[a-z]{1,2}", v.strip().lower())
                    ]
            case["entities"] = {k: v for k, v in filtered.items() if v}

        if forced_query is not None:
            raw["query"] = forced_query

        query = normalize_and_validate_query(raw.get("query"), case, kb_schema=kb_schema)

        from pipeline.extraction.case_fact_validation import (
            build_factual_case_input_diagnostics,
            validate_case_facts_not_query_target,
        )

        validate_case_facts_not_query_target(case, query, kb_schema=kb_schema)
        if run_artifact_dir:
            try:
                import os

                diag_path = os.path.join(run_artifact_dir, "case_factual_input_diagnostics.json")
                diag = build_factual_case_input_diagnostics(
                    case,
                    case_text=case_text,
                    query_predicate=str(query.get("predicate") or ""),
                    kb_schema=kb_schema,
                )
                with open(diag_path, "w", encoding="utf-8") as f:
                    json.dump(diag, f, ensure_ascii=False, indent=2)
                    f.write("\n")
            except OSError:
                pass

        if schema_environment:
            case, _mapping, _diag = prepare_case_for_symbolic(
                case,
                query,
                schema_environment,
                artifact_dir=run_artifact_dir,
            )

        debug_log("pipeline.answer_legal_prompt", "validation ok")
    except (ValueError, CaseSchemaValidationError, PreSolverDomainValidationError) as e:
        if trace:
            trace.log_error("Validation failed (case/query)", e)
            trace.close()
        return {
            "sat": None,
            "case": raw.get("case"),
            "query": raw.get("query"),
            "symbolic_result": None,
            "natural_language": None,
            "explanation": None,
            "extraction_prompt": extraction_prompt,
            "raw_extracted": raw,
            "error_stage": "validation",
            "error": str(e),
        }

    if trace:
        trace.log("Case (normalized)", json.dumps(case, indent=2, ensure_ascii=False))
        trace.log("Query (normalized)", json.dumps(query, indent=2, ensure_ascii=False))

    status_log("Reasoning", "Running symbolic reasoning (IDP-Z3)")
    debug_log("pipeline.answer_legal_prompt", "symbolic.run_query")
    try:
        sat, result = run_query(
            case,
            query,
            base_kb_text=base_kb_text,
            kb_schema=kb_schema,
            user_question=original_question,
        )
    except Exception as e:
        from pipeline.utils.unicode_sanitize import sanitize_for_output
        err_msg = sanitize_for_output(str(e))
        if trace:
            trace.log_error("Symbolic reasoning failed", err_msg)
            trace.close()
        return {
            "sat": None,
            "case": case,
            "query": query,
            "symbolic_result": None,
            "natural_language": None,
            "explanation": None,
            "extraction_prompt": extraction_prompt,
            "raw_extracted": raw,
            "error_stage": "symbolic",
            "error": err_msg,
        }

    if trace:
        trace.log("Symbolic result", json.dumps(result, indent=2, ensure_ascii=False, default=str))
        trace.log("Prediction", json.dumps(_build_prediction_summary(query, result), indent=2))
        trace.close()

    rendered = render_answer(case, query, sat, result, base_kb_text=base_kb_text, kb_schema=kb_schema)

    if debug:
        debug_log("pipeline.answer_legal_prompt", "debug flag enabled")
        print("DEBUG case:", case)
        print("DEBUG query:", query)
        print("DEBUG symbolic_result:", result)

    prediction = _build_prediction_summary(query, result)

    if run_artifact_dir and kb_schema:
        try:
            from pipeline.diagnostics.symbolic_proof_gap import (
                build_symbolic_proof_gap_report,
                save_symbolic_proof_gap_report,
            )

            gap_report = build_symbolic_proof_gap_report(
                case=case,
                query=query,
                kb_schema=kb_schema,
                schema_environment=schema_environment,
                symbolic_result=result,
                case_text=case_text,
                user_question=original_question,
            )
            save_symbolic_proof_gap_report(run_artifact_dir, gap_report)
        except Exception:
            pass

    return {
        "sat": sat,
        "case": case,
        "query": query,
        "symbolic_result": result,
        "prediction": prediction,          # ← NEW (for tests)
        "natural_language": rendered.get("answer"),
        "explanation": rendered.get("explanation"),
        "extraction_prompt": extraction_prompt,
        "raw_extracted": raw,
    }

