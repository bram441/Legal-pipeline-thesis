# pipeline/eval/scoring.py

def score_question(expected, prediction):
    """
    Compares an expected answer object against the pipeline prediction.

    Supported expected schemas (incremental):

    A) Predicate question (current)
      {
        "predicate": "liable",
        "mode": "set" | "boolean",
        "value": ["alice"] | true,
        "target": "alice"    # optional for boolean
      }

    B) Intent task (NEW)
      {
        "intent": "satisfiable",
        "value": true | false
      }

    prediction is the dict returned under result["symbolic_result"] in your pipeline.

    Returns:
      dict with match bool and details.
    """
    if expected is None:
        return {"match": None, "reason": "no expected provided"}

    if not isinstance(expected, dict):
        return {"match": False, "reason": "expected must be an object"}

    pred = prediction or {}

   
    if expected.get("intent"):
        intent = str(expected.get("intent")).strip().lower()
        if intent == "satisfiable":
            exp_val = bool(expected.get("value"))
            got_val = bool(pred.get("sat"))
            return {"match": exp_val == got_val, "expected": exp_val, "got": got_val}
        return {"match": False, "reason": "unsupported intent: " + str(intent)}

  
    predicate = expected.get("predicate")
    mode = expected.get("mode")

    if predicate != "liable":
        return {"match": False, "reason": "unsupported predicate: " + str(predicate)}

    if mode == "set":
        exp_set = sorted(expected.get("value") or [])
        got_set = sorted(pred.get("liable_set") or pred.get("result_set") or [])
        return {"match": exp_set == got_set, "expected": exp_set, "got": got_set}

    if mode == "boolean":
        exp_val = bool(expected.get("value"))
        got_val = bool(pred.get("is_liable"))
        target = expected.get("target")
        if target and pred.get("target") and target != pred.get("target"):
            return {"match": False, "reason": "target mismatch", "expected_target": target, "got_target": pred.get("target")}
        return {"match": exp_val == got_val, "expected": exp_val, "got": got_val}

    return {"match": False, "reason": "unsupported mode: " + str(mode)}
