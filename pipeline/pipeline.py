# pipeline/pipeline.py

from pipeline.prompts import EXTRACTION_PROMPT_TEMPLATE
from pipeline.schema import normalize_and_validate_case, normalize_and_validate_query
from pipeline.extractors.json_extractor import extract_case_and_query, ExtractionError
from pipeline.symbolic.router import run_query
from pipeline.rendering.answer_renderer import render_answer

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

def answer_legal_prompt(
    case_text,
    user_question,
    base_kb_text,
    extractor_provider="auto",
    extractor_model=None,
    extractor_max_retries=2,
    debug=False,
):
    extraction_prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        case_text=case_text,
        user_question=user_question,
    )

    try:
        raw = extract_case_and_query(
            case_text,
            user_question,
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

    try:
        case = normalize_and_validate_case(raw.get("case"))
        query = normalize_and_validate_query(raw.get("query"), case)
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

    try:
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