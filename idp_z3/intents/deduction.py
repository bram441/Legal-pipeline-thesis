# idp_z3/intents/deduction.py

from idp_z3.predicate_solver import evaluate_atom
import idp_z3.predicate_solver as ps




def run(case, base_kb_text, query):
    """
    Generic deduction / entailment-like intent.

    Expects:
      query.predicate: str
      query.args: list[str]

    Returns:
      (ok: bool, payload: dict)
    """
    print("USING predicate_solver from:", ps.__file__)
    predicate = (query.get("predicate") or "").strip()
    if not predicate:
        raise ValueError("deduction intent requires query.predicate")

    args = query.get("args") or []
    if not isinstance(args, list):
        raise ValueError("deduction intent requires query.args as a list")

    # Ensure args are strings (IDs/constants)
    cleaned_args = []
    for a in args:
        if not isinstance(a, str):
            raise ValueError("deduction args must be strings")
        s = a.strip()
        if not s:
            raise ValueError("deduction args may not contain empty strings")
        cleaned_args.append(s)

    out = evaluate_atom(
        case=case,
        base_kb_text=base_kb_text,
        predicate=predicate,
        args=cleaned_args,
    )

    # Keep the same (ok, payload) convention used elsewhere.
    return True, out
