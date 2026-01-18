# pipeline/symbolic/router.py

from importlib import import_module


def _run_intent(case, query, base_kb_text):
    intent = (query.get("intent") or "").strip().lower()
    if not intent:
        raise ValueError("Intent query missing 'intent'")

    try:
        mod = import_module("idp_z3.intents." + intent)
    except Exception as e:
        raise ValueError("Unsupported intent: " + intent + " (" + str(e) + ")")

    run_fn = getattr(mod, "run", None)
    if run_fn is None:
        raise ValueError("Intent handler has no run(): " + intent)

    return run_fn(case=case, base_kb_text=base_kb_text, query=query)


def _normalize_predicate_query_to_intent(query):
    """
    Predicate queries are just a UI-friendly surface form.

    We translate them to a symbolic *intent* so the backend remains generic:
      - mode == "boolean"  -> intent "deduction" (entailment-like)
      - mode == "set"      -> intent "deduction_set" (extension of predicate)

    This keeps strict validation and avoids per-predicate handlers.
    """
    pred = (query.get("predicate") or "").strip()
    if not pred:
        raise ValueError("Predicate query missing 'predicate'")

    mode = (query.get("mode") or "").strip().lower()
    explain = bool(query.get("explain", False))
    args = query.get("args") or []
    if not isinstance(args, list):
        raise ValueError("query.args must be a list")

    if mode == "boolean":
        if len(args) < 1:
            raise ValueError("Boolean predicate query requires at least 1 argument")
        # Deduction intent will interpret (predicate,args)
        return {
            "type": "intent",
            "intent": "deduction",
            "explain": explain,
            "predicate": pred,
            "mode": "boolean",
            "args": args,
        }

    if mode == "set":
        return {
            "type": "intent",
            "intent": "deduction_set",
            "explain": explain,
            "predicate": pred,
            "mode": "set",
            "args": [],
        }


    raise ValueError("Unsupported predicate query mode: " + str(mode))


def run_query(case, query, base_kb_text):
    q_type = (query.get("type") or "").strip().lower()

    if q_type == "intent":
        return _run_intent(case, query, base_kb_text)

    if q_type == "predicate":
        normalized = _normalize_predicate_query_to_intent(query)
        return _run_intent(case, normalized, base_kb_text)

    raise ValueError("Unsupported query.type: " + str(q_type))
