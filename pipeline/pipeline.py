from pipeline.prompts import EXTRACTION_PROMPT_TEMPLATE
from pipeline.schema import normalize_and_validate_case, normalize_and_validate_query
from pipeline.extractors.dummy_extractor import extract_case_and_query_dummy
from pipeline.symbolic.router import run_query
from pipeline.rendering.answer_renderer import render_answer


def answer_legal_prompt(case_text, user_question):
    extraction_prompt = EXTRACTION_PROMPT_TEMPLATE.format(case_text=case_text, user_question=user_question)

    raw = extract_case_and_query_dummy(case_text, user_question)

    case = normalize_and_validate_case(raw.get("case"))
    query = normalize_and_validate_query(raw.get("query"), case)

    sat, result = run_query(case, query)
    rendered = render_answer(case, query, sat, result)

    return {
        "sat": sat,
        "case": case,
        "query": query,
        "symbolic_result": result,
        "natural_language": rendered["answer"],
        "explanation": rendered["explanation"],
        "extraction_prompt": extraction_prompt,
        "raw_extracted": raw,
    }
