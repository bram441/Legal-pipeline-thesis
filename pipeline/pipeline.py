# pipeline/pipeline.py

from pipeline.prompts import EXTRACTION_PROMPT_TEMPLATE
from pipeline.schema import normalize_and_validate_case, normalize_and_validate_query
from pipeline.extractors.json_extractor import extract_case_and_query, ExtractionError
from pipeline.symbolic.router import run_query
from pipeline.rendering.answer_renderer import render_answer
from debug import debug_log
import json

# Orchestrates the end-to-end pipeline for a single (case_text, user_question):
#   1) builds an extraction prompt (for traceability/debugging),
#   2) extracts a structured case+query object (dummy or LLM-backed),
#   3) normalizes and validates the extracted objects (schema enforcement),
#   4) runs symbolic inference via the router,
#   5) renders a natural-language answer (and optional explanation).
#
# Params:
#   case_text (str): Natural-language description of the case facts.
#   user_question (str): Natural-language user question about the case.
#
# Returns:
#   dict: A result object containing:
#     - "sat" (bool): satisfiable or not (symbolic core result)
#     - "case" (dict): normalized case facts used for inference
#     - "query" (dict): normalized query used for inference
#     - "symbolic_result" (dict): structured symbolic output from the router
#     - "natural_language" (str): final answer text
#     - "explanation" (str | None): optional explanation text
#     - "extraction_prompt" (str): prompt used for extraction (debug/trace)
#     - "raw_extracted" (dict): raw extracted JSON before normalization
#
# Raises:
#   ValueError / ExtractionError may propagate depending on your current error-handling strategy.

def _seed_party_entities_from_case_text(case_text):
    if not isinstance(case_text, str):
        return []

    tokens = []
    for raw in case_text.replace("\n", " ").split(" "):
        w = raw.strip(".,;:!?()[]{}\"'")
        if len(w) >= 2 and w[0].isupper() and w[1:].islower():
            tokens.append(w.lower())

    # unique preserving order
    seen = set()
    out = []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def answer_legal_prompt(
    case_text,
    user_question,
    base_kb_text,
    extractor_provider="auto",
    extractor_model=None,
    extractor_max_retries=2,
    kb_schema=None,
    debug=False,
):
    debug_log("pipeline.answer_legal_prompt", "start")
   # --- Text-mode directive support (deterministic intent forcing) ---
    # Allows questions.txt lines like:
    #   @intent satisfiable
    # to force an intent query without relying on the extractor (LLM or dummy)
    # to interpret the question correctly.
    #
    # We still extract/normalize the *case* from case_text as usual, but we
    # override the extracted query with the forced intent.
    forced_query = None
    original_question = user_question or ""
    q_strip = original_question.strip()
    if q_strip.lower().startswith("@intent"):
        # Support: "@intent satisfiable" and "@intent: satisfiable"
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

        # Important: don't let the extractor hallucinate a predicate called "satisfiable".
        # We only need the extractor for the case extraction in this directive mode.
        user_question = "(intent directive)"
    extraction_prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        case_text=case_text,
        user_question=user_question,
        kb_schema_json=json.dumps(kb_schema, ensure_ascii=False, indent=2),
    )


    debug_log("pipeline.answer_legal_prompt", "extraction_provider=" + str(extractor_provider))
    try:
        raw = extract_case_and_query(
            case_text,
            user_question,
            kb_schema=kb_schema,
            provider=extractor_provider,
            model=extractor_model,
            max_retries=extractor_max_retries,
        )

    except ExtractionError as e:
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

    debug_log("pipeline.answer_legal_prompt", "normalize+validate")
    try:
        case = normalize_and_validate_case(raw.get("case"), kb_schema=kb_schema)
        if isinstance(case, dict) and "entities" not in case:
            seeded = _seed_party_entities_from_case_text(case_text)
            if seeded:
                case["entities"] = {"Party": seeded}

        if forced_query is not None:
            raw["query"] = forced_query
        query = normalize_and_validate_query(raw.get("query"), case, kb_schema=kb_schema)
        debug_log("pipeline.answer_legal_prompt", "validation ok")
    except ValueError as e:
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

    debug_log("pipeline.answer_legal_prompt", "symbolic.run_query")
    try:
        debug_log("pipeline.answer_legal_prompt", "symbolic route")
        sat, result = run_query(case, query, base_kb_text=base_kb_text)
    except Exception as e:
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
            "error": str(e),
        }

    rendered = render_answer(case, query, sat, result, base_kb_text=base_kb_text)

    if debug:
        # Backwards compatible explicit flag.
        debug_log("pipeline.answer_legal_prompt", "debug flag enabled")
        print("DEBUG case:", case)
        print("DEBUG query:", query)
        print("DEBUG symbolic_result:", result)

    return {
        "sat": sat,
        "case": case,
        "query": query,
        "symbolic_result": result,
        "natural_language": rendered.get("answer"),
        "explanation": rendered.get("explanation"),
        "extraction_prompt": extraction_prompt,
        "raw_extracted": raw,
    }