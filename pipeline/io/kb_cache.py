import os
import re

from pipeline.law.law_compiler import compile_law_to_kb_fo, LawCompilationError
from pipeline.kb_schema import extract_schema_from_kb_fo, load_kb_schema, save_kb_schema


class KBCacheError(Exception):
    pass


def _validate_kb_fo_text(kb_text):
    s = kb_text.strip()

    if "vocabulary V" not in s:
        raise KBCacheError("KB FO text missing 'vocabulary V'")
    if "theory T:V" not in s:
        raise KBCacheError("KB FO text missing 'theory T:V'")
    if "structure" in s:
        raise KBCacheError("KB FO text must not contain 'structure' blocks")

    return s


def _sanitize_common_llm_syntax(kb_text):
    s = kb_text
    s = re.sub(r'!\s*([A-Za-z_]\w*)\s*\[\s*Party\s*\]\s*:', r'! \1 in Party:', s)
    s = re.sub(r'\bforall\s+([A-Za-z_]\w*)\s+in\s+Party\s*:', r'! \1 in Party:', s, flags=re.IGNORECASE)
    return s


def _idp_parse_check(kb_text):
    try:
        from idp_engine import IDP
        IDP.from_str(kb_text)
    except Exception as e:
        raise KBCacheError("IDP failed to parse compiled KB: " + str(e))


def get_or_compile_kb(run_dir, law_text, model=None, log_filename="kb_compile.log"):
    kb_path = os.path.join(run_dir, "kb.fo")
    schema_path = os.path.join(run_dir, "kb_schema.json")
    log_path = os.path.join(run_dir, log_filename)

    if os.path.exists(kb_path):
        with open(kb_path, "r", encoding="utf-8") as f:
            kb_text = f.read()
        kb_text = _validate_kb_fo_text(kb_text)
        _idp_parse_check(kb_text)

        if os.path.exists(schema_path):
            kb_schema = load_kb_schema(run_dir)
        else:
            kb_schema = extract_schema_from_kb_fo(kb_text)
            save_kb_schema(run_dir, kb_schema)

        return kb_text, kb_schema

    try:
        raw_kb_text = compile_law_to_kb_fo(law_text, model=model)
    except LawCompilationError as e:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("KB compilation FAILED (LLM call).\n")
            f.write(str(e) + "\n")
        raise KBCacheError("Law compilation failed: " + str(e))

    try:
        kb_text = _validate_kb_fo_text(raw_kb_text)
        kb_text = _sanitize_common_llm_syntax(kb_text)
        _idp_parse_check(kb_text)
        kb_schema = extract_schema_from_kb_fo(kb_text)
    except Exception as e:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("KB compilation FAILED (invalid FO syntax).\n\n")
            f.write("Error:\n" + str(e) + "\n\n")
            f.write("=== RAW KB (from LLM) ===\n")
            f.write(raw_kb_text.strip() + "\n")
            f.write("\n=== AFTER SANITIZE ===\n")
            f.write(kb_text.strip() + "\n")
        raise

    with open(kb_path, "w", encoding="utf-8") as f:
        f.write(kb_text.strip() + "\n")

    save_kb_schema(run_dir, kb_schema)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("KB compiled successfully.\n")

    return kb_text, kb_schema
