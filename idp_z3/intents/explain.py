"""Explain intent.

In this project, *explanations* are primarily a rendering concern:
the solver returns a structured trace (rule snippet, relevant facts,
constraint, possible/certain), and the renderer formats it.

However, having an explicit 'explain' intent is useful for parity with
the planned Versus-LM style interface.

This implementation is intentionally generic and schema-agnostic:
it computes the same deduction trace as the 'deduction' intent.
"""

from idp_z3.predicate_solver import evaluate_atom


def run(case, base_kb_text, query):
    predicate = (query.get("predicate") or "").strip()
    args = query.get("args") or []
    if not predicate:
        raise ValueError("explain requires query.predicate")
    if not isinstance(args, list) or not args:
        raise ValueError("explain requires query.args as a non-empty list")

    cleaned = []
    for a in args:
        if not isinstance(a, str) or not a.strip():
            raise ValueError("explain args must be non-empty strings")
        cleaned.append(a.strip())

    out = evaluate_atom(case=case, base_kb_text=base_kb_text, predicate=predicate, args=cleaned)
    return True, out
