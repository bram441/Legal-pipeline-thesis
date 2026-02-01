import json

from debug import debug_log

from pipeline.extraction.extractor import extract_case_and_query, ExtractionError
from pipeline.symbolic.router import run_query
from pipeline.rendering.answer_renderer import render_answer
from pipeline.validation.fo_validation import normalize_and_validate_case, normalize_and_validate_query
from pipeline.utils.prompt_loader import render_prompt
from pipeline.domain.seeding import seed_entities_from_case_text


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
    """Run the full pipeline for a single (case_text, user_question).

    Flow
    1) LLM extraction -> raw {case, query}
    2) normalization + strict schema validation
    3) symbolic reasoning via IDP-Z3 (intent router)
    4) render answer + optional explanation
    """
    debug_log("pipeline.answer_legal_prompt", "start")

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

    extraction_prompt = render_prompt(
        "extraction_debug_prompt.txt",
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

        # optional domain seeding (kept separate from validation)
        if isinstance(case, dict) and "entities" not in case:
            seeded = seed_entities_from_case_text(case_text)

            if seeded:
                types = kb_schema.get("types") or []
                default_type = types[0] if types else None

                if default_type:
                    case["entities"] = {default_type: seeded}
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
