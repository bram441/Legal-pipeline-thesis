# idp_z3/tasks.py

import re

from .idp_backend import run_idp
from .case_structure import build_structure_block_from_facts
from debug import debug_enabled, debug_log


def _primary_type_from_kb(kb_text):
    """Extract first-declared type from vocabulary for structure domain alignment."""
    try:
        from pipeline.kb.schema import get_primary_type_from_kb
        return get_primary_type_from_kb(kb_text or "")
    except Exception:
        return None


def _all_types_from_kb(kb_text):
    """Extract all types from vocabulary for complete structure interpretation."""
    try:
        from pipeline.kb.schema import get_all_types_from_kb
        return get_all_types_from_kb(kb_text or "")
    except Exception:
        return []


def _predicate_names_from_kb(kb_text):
    """Extract predicate names for closing open predicates in structure."""
    try:
        from pipeline.kb.schema import get_predicate_names_from_kb
        return get_predicate_names_from_kb(kb_text or "")
    except Exception:
        return []


def _predicate_kinds_from_schema(kb_schema):
    """Map predicate name -> kind from JSON-IR kb_schema."""
    if not isinstance(kb_schema, dict):
        return None
    kinds: dict[str, str] = {}
    for p in kb_schema.get("predicates") or []:
        if isinstance(p, dict) and p.get("name"):
            kinds[str(p["name"])] = str(p.get("kind") or "unknown").strip().lower()
    return kinds or None


def _compose_program(case, base_kb_text, base_kb_for_schema=None):
    """Compose KB + structure. Use base_kb_for_schema (default: base_kb_text) for extracting
    types and predicate names - important when base_kb_text has been augmented with aux symbols
    like __sel0, to avoid adding those to the structure and causing duplicates."""
    if not base_kb_text:
        raise ValueError("base_kb_text is required")
    if not isinstance(case, dict) or "facts" not in case:
        raise ValueError("case must be a dict with 'facts' (schema-driven case format)")

    schema_kb = base_kb_for_schema if base_kb_for_schema is not None else base_kb_text
    kb_primary = _primary_type_from_kb(schema_kb)
    kb_types = _all_types_from_kb(schema_kb)
    kb_preds = _predicate_names_from_kb(schema_kb)
    kb_schema = case.get("kb_schema") if isinstance(case, dict) else None
    pred_kinds = _predicate_kinds_from_schema(kb_schema)
    try:
        structure = build_structure_block_from_facts(
            case["facts"],
            entities=case.get("entities"),
            kb_primary_type=kb_primary,
            kb_types=kb_types,
            kb_predicate_names=kb_preds,
            predicate_kinds=pred_kinds,
            kb_schema=kb_schema,
        )
    except TypeError:
        structure = build_structure_block_from_facts(case["facts"])

    if not structure:
        raise ValueError("Failed to build structure block")

    return base_kb_text.strip() + "\n\n" + structure + "\n"



def _find_matching_brace(text, open_brace_index):
    """
    Given an index of a '{', find the matching '}' by counting nested braces.
    This is required because structures contain set literals like {a,b}.
    """
    if open_brace_index < 0 or open_brace_index >= len(text) or text[open_brace_index] != "{":
        raise ValueError("open_brace_index must point to '{'")

    depth = 0
    for i in range(open_brace_index, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _inject_into_vocabulary(base_kb_text, extra_vocab_lines):
    """
    Insert extra predicate declarations into 'vocabulary V { ... }'
    using brace matching (safe even if future vocab contains set literals).
    """
    if not extra_vocab_lines:
        return base_kb_text

    s = base_kb_text
    m = re.search(r"\bvocabulary\s+V\s*\{", s)
    if not m:
        raise ValueError("Cannot inject into vocabulary: missing 'vocabulary V {'")

    # index of the '{' that starts the vocabulary block
    vocab_open = s.find("{", m.start())
    if vocab_open < 0:
        raise ValueError("Cannot inject into vocabulary: missing '{'")

    vocab_close = _find_matching_brace(s, vocab_open)
    if vocab_close < 0:
        raise ValueError("Cannot inject into vocabulary: unmatched '{'")

    before = s[:vocab_close].rstrip()
    after = s[vocab_close:]

    insert = "\n  " + "\n  ".join(extra_vocab_lines) + "\n"
    return before + insert + after


def _inject_into_structure(fo_code, extra_struct_lines):
    """
    Insert extra interpretations into 'structure S:V { ... }'
    using brace matching (critical due to set literals inside).
    """
    if not extra_struct_lines:
        return fo_code

    s = fo_code
    m = re.search(r"\bstructure\s+S\s*:\s*V\s*\{", s)
    if not m:
        raise ValueError("Cannot inject into structure: missing 'structure S:V {'")

    struct_open = s.find("{", m.start())
    if struct_open < 0:
        raise ValueError("Cannot inject into structure: missing '{'")

    struct_close = _find_matching_brace(s, struct_open)
    if struct_close < 0:
        raise ValueError("Cannot inject into structure: unmatched '{'")

    before = s[:struct_close].rstrip()
    after = s[struct_close:]

    insert = "\n  " + "\n  ".join(extra_struct_lines) + "\n"
    return before + insert + after


def satisfiable_check(case, base_kb_text):
    fo_code = _compose_program(case, base_kb_text)
    debug_log("tasks.satisfiable_check", "theory=T")
    result = run_idp(fo_code, max_models=1)
    return {"sat": bool(result.get("sat"))}


def satisfiable_check_with_constraint(case, base_kb_text, constraint_fo, extra_vocab_lines=None, extra_struct_lines=None):
    """
    Checks satisfiable(base_kb + case + extra helpers + constraint).

    IMPORTANT:
    - We append the constraint as a separate theory Q:V { ... }.
    - We must then call run_idp(..., theory_name="Q") because the backend defaults to "T".
    """
    if not isinstance(constraint_fo, str) or not constraint_fo.strip():
        raise ValueError("constraint_fo must be a non-empty string")

    extra_vocab_lines = extra_vocab_lines or []
    extra_struct_lines = extra_struct_lines or []

    kb_with_aux = _inject_into_vocabulary(base_kb_text, extra_vocab_lines)

    # Use original base_kb_text for schema extraction so aux symbols (e.g. __sel0) are not
    # added to the structure, which would cause "Duplicate '__sel0' in interpretations"
    fo_code = _compose_program(case, kb_with_aux, base_kb_for_schema=base_kb_text)
    fo_code = _inject_into_structure(fo_code, extra_struct_lines)

    constraint = constraint_fo.strip()
    if not constraint.endswith("."):
        constraint = constraint + "."

    fo_code = fo_code + "\n" + (
        "theory Q:V {\n"
        "  " + constraint + "\n"
        "}\n"
    )
    debug_log("tasks.satisfiable_check_with_constraint", "theories=[T,Q] constraint=" + constraint)
    if debug_enabled():
        # Optional: show the actual FO program sent to IDP (critical for sanity checks).
        debug_log("tasks.satisfiable_check_with_constraint", "fo_code:\n" + fo_code)

    debug_log("tasks.satisfiable_check_with_constraint", "theories=T+Q")
    result = run_idp(fo_code, theory_name=["T", "Q"], max_models=1)
    out = {"sat": bool(result.get("sat"))}
    if debug_enabled():
        # Large, but extremely useful while debugging symbolic behavior.
        out["fo_code"] = fo_code
    return out
