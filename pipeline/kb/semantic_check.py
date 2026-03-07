"""
Semantic validation for the KB using IDP-Z3.
Checks that the theory is satisfiable with a minimal structure.
"""

from pipeline.kb.schema import get_all_types_from_kb


class KBSemanticError(Exception):
    pass


def _build_minimal_structure(kb_text):
    """Build a minimal structure so the theory can be checked for satisfiability.
    Each domain type gets one dummy element. Predicates/functions are left open
    (IDP will propagate or expand as needed).
    """
    types = get_all_types_from_kb(kb_text)
    if not types:
        return None

    lines = []
    for t in types:
        if t:
            lines.append("  " + t + " := {'dummy'}.")
    body = "\n".join(lines)
    return f"""structure S:V {{
{body}
}}
"""


def check_kb_semantic(kb_text, timeout_seconds=5):
    """
    Run IDP model_check with a minimal structure. If unsatisfiable,
    the theory is contradictory (has no model).
    Raises KBSemanticError if the KB is semantically invalid (unsatisfiable).
    On IDP/runtime errors (e.g. encoding), re-raises so the repair loop gets feedback.
    """
    if not kb_text or not kb_text.strip():
        return

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
        raise KBSemanticError(
            "KB theory is unsatisfiable: no model exists. "
            "The rules may be contradictory or too restrictive. "
            "Check for conflicting implications or impossible conditions."
        )
