# idp_z3/intents/deduction_set.py

from idp_z3.predicate_solver import evaluate_set

def run(case, base_kb_text, query):
    predicate = (query.get("predicate") or "").strip()
    if not predicate:
        raise ValueError("deduction_set requires query.predicate")

    out = evaluate_set(
        case=case,
        base_kb_text=base_kb_text,
        predicate=predicate,
    )

    return True, out
