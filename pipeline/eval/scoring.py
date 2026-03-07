# pipeline/eval/scoring.py

import re


def _normalize_range_for_compare(range_str, entity=None):
    """Extract a single numeric value from get_range output for comparison."""
    if range_str is None:
        return None
    s = str(range_str).strip()
    if not s or "no model" in s.lower() or "unsatisfiable" in s.lower() or "not found" in s.lower():
        return None
    # Single number
    m = re.search(r"^(-?\d+)", s)
    if m:
        return m.group(1)
    # Mapping like {'pieter' -> 8} or 'pieter' -> 8
    if entity:
        entity_clean = str(entity).strip().lower().replace("'", "")
        for pattern in [
            r"['\"]?" + re.escape(entity_clean) + r"['\"]?\s*->\s*(-?\d+)",
            r"->\s*(-?\d+)",
        ]:
            m = re.search(pattern, s, re.IGNORECASE)
            if m:
                return m.group(1)
    return None


def score_question(expected, symbolic_result):
    """
    Compares an expected answer object against the pipeline symbolic_result.

    Supported expected schemas:

    A) Predicate question
      {
        "predicate": "liable",  # or any predicate; used for documentation
        "mode": "set" | "boolean",
        "value": ["alice"] | true,   # gold answer
        "target": "alice"            # optional for boolean
      }

    B) Intent task
      {
        "intent": "satisfiable",
        "value": true | false
      }

    symbolic_result is the dict from run_query (e.g. deduction returns
    {certain, possible}; deduction_set returns {certain, possible} as lists).
    """
    if expected is None:
        return {"match": None, "reason": "no expected provided"}

    if not isinstance(expected, dict):
        return {"match": False, "reason": "expected must be an object"}

    pred = symbolic_result or {}

    if expected.get("intent"):
        intent = str(expected.get("intent")).strip().lower()
        if intent == "satisfiable":
            exp_val = bool(expected.get("value"))
            got_val = bool(pred.get("sat"))
            return {"match": exp_val == got_val, "expected": exp_val, "got": got_val}
        if intent == "get_range":
            exp_val = expected.get("value")
            got_raw = pred.get("range")
            # Normalize: range can be "8", "{'pieter' -> 8}", or "No model exists"
            got_val = _normalize_range_for_compare(got_raw, pred.get("entity"))
            exp_norm = str(exp_val).strip() if exp_val is not None else None
            match = (exp_norm is not None and got_val is not None and exp_norm == got_val)
            return {"match": match, "expected": exp_val, "got": got_val, "raw_range": got_raw}
        return {"match": False, "reason": "unsupported intent: " + str(intent)}

    predicate = expected.get("predicate")
    mode = expected.get("mode")

    if mode == "set":
        exp_set = sorted(str(x).strip().lower() for x in (expected.get("value") or []))
        got_set = sorted(
            str(x).strip().lower()
            for x in (pred.get("certain") or pred.get("certain_set") or [])
        )
        return {"match": exp_set == got_set, "expected": exp_set, "got": got_set}

    if mode == "boolean":
        exp_val = bool(expected.get("value"))
        got_val = bool(pred.get("certain"))
        target = expected.get("target")
        if target and pred.get("target") and str(target).lower() != str(pred.get("target")).lower():
            return {
                "match": False,
                "reason": "target mismatch",
                "expected_target": target,
                "got_target": pred.get("target"),
            }
        return {"match": exp_val == got_val, "expected": exp_val, "got": got_val}

    return {"match": False, "reason": "unsupported mode: " + str(mode)}
