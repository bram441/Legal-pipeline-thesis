"""
Semantic validation for the KB using IDP-Z3.
Checks that the theory is satisfiable with a minimal structure.
Also checks for circular article-predicate definitions (which cause unsatisfiability).
"""

import re

from pipeline.kb.schema import get_all_types_from_kb


class KBSemanticError(Exception):
    pass


# Pattern: article conclusion predicate used (negated or not) in body of another formula
_ARTICLE_PRED = r"(liableArt\d+|punishedArt\d+)"
_CIRCULARITY_MSG = (
    "Article predicates (e.g. liableArt398, punishedArt399) must be defined using ONLY condition predicates "
    "(e.g. IntentionallyInflictsWoundsOrBlows, CausesIllnessOrIncapacity). "
    "Do NOT reference another article predicate in the body (e.g. ~liableArt399(x) or ~punishedArt398(x))—"
    "that causes circularity and 'no model exists'. Define each article predicate with conditions only."
)


def check_kb_no_circular_article_definitions(kb_text):
    """
    Raise KBSemanticError if any article predicate is used in the definition of another
    (e.g. liableArt398(x) <=> ... & ~liableArt399(x)), which makes the theory unsatisfiable.
    """
    if not kb_text or not kb_text.strip():
        return
    theory_match = re.search(r"theory\s+T\s*:\s*V\s*\{([^}]+)\}", kb_text, re.DOTALL | re.IGNORECASE)
    if not theory_match:
        return
    theory = theory_match.group(1)
    # After "<=>", any occurrence of ~articlePred( or & articlePred( or | articlePred( is circular
    if re.search(r"<=>\s*[\s\S]*?[&\|~]\s*" + _ARTICLE_PRED + r"\s*\(", theory):
        raise KBSemanticError(_CIRCULARITY_MSG)


def _build_minimal_structure(kb_text):
    """Build a minimal structure so the theory can be checked for satisfiability.
    Each domain type gets one dummy element (ASCII-only to avoid encoding issues).
    Predicates/functions are left open (IDP will propagate or expand as needed).

    Uses a distinct constant name per type (elem_TypeName). Reusing ``x`` for every
    ``Type := {x}`` can trigger IDP errors like duplicate 'x' constructor for a type
    when the vocabulary also declares typed constants.
    """
    raw = get_all_types_from_kb(kb_text)
    if not raw:
        return None

    seen = set()
    types = []
    for t in raw:
        if t and t not in seen:
            seen.add(t)
            types.append(t)

    lines = []
    for t in types:
        elem = "elem_" + t
        lines.append("  " + t + " := {" + elem + "}.")
    body = "\n".join(lines)
    return f"""structure S:V {{
{body}
}}
"""


def explain_unsat_fo(fo_code: str):
    """
    If the FO(.) program is UNSAT after propagation, return a human-readable explanation
    from IDP Theory.explain(); otherwise None. Used by KB semantic check and by
    ``scripts/diagnose_unsat.py`` (full KB + case).

    Note: KB-only checks use KB + minimal structure; diagnose_unsat uses KB + case structure.
    """
    return _get_unsat_explanation(fo_code)


def _get_unsat_explanation(fo_code):
    """
    Use IDP Theory.propagate() and Theory.explain() to get structured UNSAT feedback.
    Returns a string describing which facts and formulas conflict, or None if unavailable.
    (Inspired by VERUS-LM explain_unsat_theory.)
    """
    try:
        from idp_engine import IDP, Theory
        kb = IDP.from_str(fo_code)
        T_block, S_block = kb.get_blocks("T, S")
        theory = Theory(T_block, S_block)
        theory.propagate()
        if getattr(theory, "satisfied", True):
            return None
        facts, formulas = theory.explain()
        parts = []
        if facts:
            parts.append("Conflicting assignments/facts:")
            parts.append("\n".join(str(f) for f in facts))
        if formulas:
            formula_codes = [getattr(f, "code", str(f)) for f in formulas]
            parts.append("Conflicting formulas:")
            parts.append("\n".join(str(c) for c in formula_codes))
        if parts:
            return "The following rules led to an inconsistency:\n" + "\n\n".join(parts)
    except Exception:
        pass
    return None


def check_kb_semantic(kb_text, timeout_seconds=5):
    """
    Run IDP model_check with a minimal structure. If unsatisfiable,
    the theory is contradictory (has no model).
    Raises KBSemanticError if the KB is semantically invalid (unsatisfiable).
    On IDP/runtime errors (e.g. encoding), re-raises so the repair loop gets feedback.
    """
    if not kb_text or not kb_text.strip():
        return

    check_kb_no_circular_article_definitions(kb_text)

    struct = _build_minimal_structure(kb_text)
    if not struct:
        return

    fo_code = kb_text.strip() + "\n\n" + struct

    try:
        from idp_z3.idp_backend import run_idp
        result = run_idp(fo_code, max_models=1, timeout_seconds=timeout_seconds)
    except UnicodeEncodeError as e:
        # Windows/environment encoding - skip semantic check to avoid breaking pipeline
        import warnings
        warnings.warn("KB semantic check skipped (encoding issue): " + str(e), stacklevel=1)
        return
    except Exception as e:
        raise KBSemanticError("IDP semantic check failed: " + str(e))

    if not result.get("sat", True):
        explanation = _get_unsat_explanation(fo_code)
        if explanation:
            msg = (
                "KB theory is unsatisfiable. " + explanation + "\n\n"
                "Fix the conflicting rules (e.g. make conditions mutually exclusive, avoid circular article predicates)."
            )
        else:
            msg = (
                "KB theory is unsatisfiable: no model exists. "
                "Common cause: article predicates (liableArt398, punishedArt399, etc.) defined in terms of each other (circular). "
                "Define each article predicate using ONLY condition predicates (e.g. IntentionallyInflictsWoundsOrBlows, CausesIllnessOrIncapacity), never reference another article predicate in the body. "
                "Also check for conflicting implications or impossible conditions."
            )
        raise KBSemanticError(msg)
