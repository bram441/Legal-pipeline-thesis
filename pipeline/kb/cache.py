import os
import re

from debug import status_log
from pipeline.kb.compiler import compile_law_to_kb_fo
from pipeline.kb.exceptions import LawCompilationError
from pipeline.kb.schema import _VOCAB_RE, extract_schema_from_kb_fo, load_kb_schema, save_kb_schema
from pipeline.kb.semantic_check import check_kb_semantic, KBSemanticError
from pipeline.utils.run_trace import trace_enabled, RunTraceWriter


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


def _fix_vocab_markdown_bullet_merges(kb_text):
    """
    LLMs often paste markdown bullets into FO: `pred1: Bool   *pred2: ...` on one line.
    IDP then parses `*` as a type constructor and fails (Expected '->' at ... *pred2).
    Split into two declarations. Repeat to unwrap chains.
    """
    lines = kb_text.splitlines()
    out = []
    # After Bool / Int / Real, spurious `* nextName` (LLM often omits space: `Bool*foo`)
    pat_simple = re.compile(
        r"^(\s*)([A-Za-z_]\w*)\s*:\s*(Bool|Int|Real)\s*\*\s*([A-Za-z_]\w*)(.*)$"
    )
    # After `... -> Bool`, same bullet mistake
    pat_arrow_bool = re.compile(
        r"^(\s*)([A-Za-z_]\w*)\s*:\s*"
        r"((?:[A-Za-z_]\w*(?:\s*\*\s*[A-Za-z_]\w*)*)\s*->\s*Bool)\s*\*\s*"
        r"([A-Za-z_]\w*)(.*)$"
    )
    for line in lines:
        m = pat_simple.match(line)
        if not m:
            m = pat_arrow_bool.match(line)
        if m:
            indent, first, typ_or_sig, second, rest = (
                m.group(1),
                m.group(2),
                m.group(3),
                m.group(4),
                m.group(5),
            )
            rest = rest.strip()
            out.append(indent + first + ": " + typ_or_sig)
            if rest.startswith(":"):
                out.append(indent + "  " + second + rest)
            else:
                out.append(indent + "  " + second + ": Bool" + ((" " + rest) if rest else ""))
        else:
            out.append(line)
    return "\n".join(out)


_CO_DOMAIN_TYPES = frozenset({"Bool", "Int", "Real"})


def _normalize_vocab_curried_domain(kb_text: str) -> str:
    """
    LLMs often declare binary (or n-ary) predicates as curried arrows:
      foo: Person -> Goods -> Bool
    IDP FO(.) expects a product domain:
      foo: Person * Goods -> Bool
    """
    m = _VOCAB_RE.search(kb_text or "")
    if not m:
        return kb_text
    inner = m.group(1)
    out_lines: list[str] = []
    for raw in inner.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("#"):
            out_lines.append(raw)
            continue
        if re.match(r"^\s*type\s+", raw, re.IGNORECASE):
            out_lines.append(raw)
            continue
        sm = re.match(r"^(\s*)([A-Za-z_]\w*)\s*:\s*(.+)$", raw.rstrip())
        if not sm:
            out_lines.append(raw)
            continue
        indent, sym, rhs = sm.group(1), sm.group(2), sm.group(3).strip()
        parts = re.split(r"\s*->\s*", rhs)
        if len(parts) >= 3 and parts[-1] in _CO_DOMAIN_TYPES:
            domain = " * ".join(parts[:-1])
            out_lines.append(indent + sym + ": " + domain + " -> " + parts[-1])
        else:
            out_lines.append(raw)
    new_inner = "\n".join(out_lines)
    start, end = m.span(1)
    return kb_text[:start] + new_inner + kb_text[end:]


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
    # Markdown bullets merged between vocabulary lines (see _fix_vocab_markdown_bullet_merges)
    prev = None
    while prev != s:
        prev = s
        s = _fix_vocab_markdown_bullet_merges(s)
    s = _normalize_vocab_curried_domain(s)
    return s


def _fix_sentence_equivalence(kb_text):
    """
    Convert function-assignment rules from <=> to => to avoid UNSAT.
    Rules like 'imprisonmentMinDays(p) = 180 <=> cond' create conflicts when
    multiple rules constrain the same function for the same person; use => instead.
    """
    def repl(m):
        lhs, val, cond = m.group(1), m.group(2), m.group(3)
        cond = cond.strip().rstrip(".")
        return "(" + cond + ") => " + lhs + " = " + val + "."

    return re.sub(
        r"(\w+\([^)]+\))\s*=\s*(-?\d+)\s*<=>\s*(.+?)\.\s*$",
        repl,
        kb_text,
        flags=re.MULTILINE,
    )


def _idp_parse_check(kb_text):
    try:
        from idp_engine import IDP
        IDP.from_str(kb_text)
    except Exception as e:
        raise KBCacheError("IDP failed to parse compiled KB: " + str(e))


def _use_le_enabled():
    try:
        from pipeline.le import use_le_enabled
        return use_le_enabled()
    except ImportError:
        return False


def get_or_compile_kb(run_dir, law_text, model=None, log_filename="kb_compile.log", max_repair_attempts=8, cache_subdir=None):
    """Compile or load KB. When cache_subdir is set (e.g. 'translated'), use run_dir/cache_subdir/ for cache.
    When PIPELINE_USE_LE=1, appends 'le' to cache path so LE and non-LE KBs are cached separately.
    When PIPELINE_TRACE=1, writes all steps to run_dir/run_trace.txt for debugging.
    Override attempt count with env ``PIPELINE_KB_MAX_REPAIR_ATTEMPTS`` (integer >= 1)."""
    env_attempts = os.getenv("PIPELINE_KB_MAX_REPAIR_ATTEMPTS")
    if env_attempts:
        try:
            max_repair_attempts = max(1, int(env_attempts.strip()))
        except ValueError:
            pass

    base_run_dir = run_dir
    trace_path = os.path.join(base_run_dir, "run_trace.txt") if trace_enabled() else None

    parts = []
    if cache_subdir:
        parts.append(cache_subdir)
    if _use_le_enabled():
        parts.append("le")
    if parts:
        run_dir = os.path.join(run_dir, *parts)
        os.makedirs(run_dir, exist_ok=True)
    kb_path = os.path.join(run_dir, "kb.fo")
    schema_path = os.path.join(run_dir, "kb_schema.json")
    log_path = os.path.join(run_dir, log_filename)

    repair_feedback = None
    last_raw = None

    trace = RunTraceWriter(trace_path) if trace_path else None
    if trace:
        trace.section("RUN TRACE")
        trace.log("Run dir", base_run_dir)
        trace.log("Cache subdir (effective)", run_dir)

    if os.path.exists(kb_path):
        status_log("KB", "Loading from cache")
        with open(kb_path, "r", encoding="utf-8") as f:
            cached_kb = f.read()
        try:
            kb_text = _sanitize_common_llm_syntax(cached_kb)
            kb_text = _fix_sentence_equivalence(kb_text)
            if kb_text != cached_kb:
                with open(kb_path, "w", encoding="utf-8") as f:
                    f.write(kb_text.strip() + "\n")
            kb_text = _validate_kb_fo_text(kb_text)
            try:
                from pipeline.kb.kb_lint import lint_kb_fo_text

                lint_kb_fo_text(kb_text)
            except Exception as lint_exc:
                raise KBCacheError("KB lint: " + str(lint_exc)) from lint_exc
            _idp_parse_check(kb_text)
            check_kb_semantic(kb_text)
            if os.path.exists(schema_path):
                kb_schema = load_kb_schema(run_dir)
            else:
                kb_schema = extract_schema_from_kb_fo(kb_text)
                save_kb_schema(run_dir, kb_schema)
            if trace:
                trace.section("KB LOADED FROM CACHE")
                trace.log("Status", "OK (syntax and semantic checks passed)")
                trace.close()
            return kb_text, kb_schema
        except Exception as e:
            status_log("KB", "Cached KB invalid, recompiling with repair")
            if trace:
                trace.section("CACHED KB INVALID - RECOMPILING")
                trace.log_error("Validation failed", e)
                trace.log("Cached KB (that failed)", cached_kb.strip())
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
        if trace:
            trace.section("KB COMPILATION - Attempt {}".format(attempt + 1))
            trace.log("Law text", law_text)
            if repair_feedback:
                trace.log("Repair feedback (from previous attempt)", repair_feedback.get("error_message", ""))
                trace.log("Previous output (sent to repair prompt)", repair_feedback.get("previous_output", "")[:3000] + ("..." if len(repair_feedback.get("previous_output", "")) > 3000 else ""))

        if attempt == 0:
            status_log("KB", "Generating from law text (Logical English)" if _use_le_enabled() else "Generating from law text")
        else:
            status_log("KB", "Repair attempt {}".format(attempt))

        try:
            raw_kb_text = compile_law_to_kb_fo(law_text, model=model, repair_feedback=repair_feedback)
        except LawCompilationError as e:
            if trace:
                trace.log_error("LLM call failed", e)
                trace.close()
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("KB compilation FAILED (LLM call).\n")
                f.write(str(e) + "\n")
                if last_raw:
                    f.write("\n=== LAST RAW KB ===\n" + last_raw.strip() + "\n")
            raise KBCacheError("Law compilation failed: " + str(e))

        last_raw = raw_kb_text
        if trace:
            trace.log("LLM response (raw)", raw_kb_text)

        try:
            status_log("KB", "Checking syntax validity")
            kb_text = _sanitize_common_llm_syntax(raw_kb_text)
            kb_text = _fix_sentence_equivalence(kb_text)
            if trace:
                trace.log("After sanitization", kb_text[:2000] + ("..." if len(kb_text) > 2000 else ""))
            try:
                from pipeline.kb.kb_lint import lint_kb_fo_text

                lint_kb_fo_text(kb_text)
            except Exception as lint_exc:
                raise KBCacheError("KB lint: " + str(lint_exc)) from lint_exc
            kb_text = _validate_kb_fo_text(kb_text)
            _idp_parse_check(kb_text)
            if trace:
                trace.log("Syntax validation", "OK (vocabulary+theory present, IDP parse OK)")
            kb_schema = extract_schema_from_kb_fo(kb_text)
            status_log("KB", "Checking semantic validity (satisfiability)")
            check_kb_semantic(kb_text)
            if trace:
                trace.log("Semantic validation", "OK (theory satisfiable)")
        except (KBCacheError, KBSemanticError, Exception) as e:
            if trace:
                trace.log_error("Validation failed", e)
            repair_feedback = {
                "error_message": str(e),
                "previous_output": raw_kb_text.strip(),
            }
            if attempt < max_repair_attempts - 1:
                continue
            if trace:
                trace.section("KB COMPILATION FAILED")
                trace.log("Final error", str(e))
                trace.close()
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("KB compilation FAILED (invalid FO syntax after {} repair attempts).\n\n".format(max_repair_attempts))
                f.write("Error:\n" + str(e) + "\n\n")
                f.write("=== LAST RAW KB ===\n")
                f.write(raw_kb_text.strip() + "\n")
            raise KBCacheError("KB compilation failed after {} repair attempts: {}".format(max_repair_attempts, e))

        break

    if trace:
        trace.section("KB COMPILATION SUCCESS")
        trace.log("Final KB", kb_text)
        trace.close()

    with open(kb_path, "w", encoding="utf-8") as f:
        f.write(kb_text.strip() + "\n")

    save_kb_schema(run_dir, kb_schema)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("KB compiled successfully.\n")

    status_log("KB", "Compilation successful")
    return kb_text, kb_schema
