import os
import re

from debug import status_log
from pipeline.kb.compiler import compile_law_to_kb_fo, LawCompilationError
from pipeline.kb.schema import extract_schema_from_kb_fo, load_kb_schema, save_kb_schema
from pipeline.kb.semantic_check import check_kb_semantic, KBSemanticError


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
    # LLM often outputs "theory T: V" (space after colon); IDP expects "theory T:V"
    s = re.sub(r'theory\s+T\s*:\s*V\b', 'theory T:V', s, flags=re.IGNORECASE)
    # FO(.) requires capitalized built-in types: Bool, Int, Real
    s = re.sub(r'\b->\s*bool\b', ' -> Bool', s)
    s = re.sub(r'\b->\s*int\b', ' -> Int', s)
    s = re.sub(r'\b->\s*real\b', ' -> Real', s)
    # Equivalence: IDP expects <=> , not <-> (Prolog/math style)
    s = re.sub(r'<->', '<=>', s)
    return s


def _idp_parse_check(kb_text):
    try:
        from idp_engine import IDP
        IDP.from_str(kb_text)
    except Exception as e:
        raise KBCacheError("IDP failed to parse compiled KB: " + str(e))


def get_or_compile_kb(run_dir, law_text, model=None, log_filename="kb_compile.log", max_repair_attempts=6, cache_subdir=None):
    """Compile or load KB. When cache_subdir is set (e.g. 'translated'), use run_dir/cache_subdir/ for cache."""
    if cache_subdir:
        run_dir = os.path.join(run_dir, cache_subdir)
        os.makedirs(run_dir, exist_ok=True)
    kb_path = os.path.join(run_dir, "kb.fo")
    schema_path = os.path.join(run_dir, "kb_schema.json")
    log_path = os.path.join(run_dir, log_filename)

    repair_feedback = None
    last_raw = None

    if os.path.exists(kb_path):
        status_log("KB", "Loading from cache")
        with open(kb_path, "r", encoding="utf-8") as f:
            cached_kb = f.read()
        try:
            kb_text = _validate_kb_fo_text(cached_kb)
            _idp_parse_check(kb_text)
            check_kb_semantic(kb_text)
            if os.path.exists(schema_path):
                kb_schema = load_kb_schema(run_dir)
            else:
                kb_schema = extract_schema_from_kb_fo(kb_text)
                save_kb_schema(run_dir, kb_schema)
            return kb_text, kb_schema
        except Exception as e:
            status_log("KB", "Cached KB invalid, recompiling with repair")
            try:
                os.remove(kb_path)
            except OSError:
                pass
            if os.path.exists(schema_path):
                try:
                    os.remove(schema_path)
                except OSError:
                    pass
            repair_feedback = {
                "error_message": str(e),
                "previous_output": cached_kb.strip(),
            }
            last_raw = cached_kb

    for attempt in range(max_repair_attempts):
        if attempt == 0:
            status_log("KB", "Generating from law text")
        else:
            status_log("KB", "Repair attempt {}".format(attempt))

        try:
            raw_kb_text = compile_law_to_kb_fo(law_text, model=model, repair_feedback=repair_feedback)
        except LawCompilationError as e:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("KB compilation FAILED (LLM call).\n")
                f.write(str(e) + "\n")
                if last_raw:
                    f.write("\n=== LAST RAW KB ===\n" + last_raw.strip() + "\n")
            raise KBCacheError("Law compilation failed: " + str(e))

        last_raw = raw_kb_text

        try:
            status_log("KB", "Checking syntax validity")
            kb_text = _sanitize_common_llm_syntax(raw_kb_text)
            kb_text = _validate_kb_fo_text(kb_text)
            _idp_parse_check(kb_text)
            kb_schema = extract_schema_from_kb_fo(kb_text)
            status_log("KB", "Checking semantic validity (satisfiability)")
            check_kb_semantic(kb_text)
        except (KBCacheError, KBSemanticError, Exception) as e:
            repair_feedback = {
                "error_message": str(e),
                "previous_output": raw_kb_text.strip(),
            }
            if attempt < max_repair_attempts - 1:
                continue
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("KB compilation FAILED (invalid FO syntax after {} repair attempts).\n\n".format(max_repair_attempts))
                f.write("Error:\n" + str(e) + "\n\n")
                f.write("=== LAST RAW KB ===\n")
                f.write(raw_kb_text.strip() + "\n")
            raise KBCacheError("KB compilation failed after {} repair attempts: {}".format(max_repair_attempts, e))

        break

    with open(kb_path, "w", encoding="utf-8") as f:
        f.write(kb_text.strip() + "\n")

    save_kb_schema(run_dir, kb_schema)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("KB compiled successfully.\n")

    status_log("KB", "Compilation successful")
    return kb_text, kb_schema
