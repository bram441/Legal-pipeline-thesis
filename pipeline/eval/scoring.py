# pipeline/eval/scoring.py

def score_question(expected, prediction):
    """
    Compares an expected answer object against the pipeline prediction.

    expected schema (minimal):
      - predicate: str
      - mode: "set" | "boolean"
      - value: list[str] (for set) OR bool (for boolean)
      - target: str (optional, for boolean)

    prediction is the dict returned under result["symbolic_result"] in your pipeline.

    Returns:
      dict with match bool and details.
    """
    pred = prediction or {}

    predicate = expected.get("predicate")
    mode = expected.get("mode")

    if predicate != "liable":
        return {"match": False, "reason": "unsupported predicate in scoring: " + str(predicate)}

    if mode == "set":
        exp_set = sorted(expected.get("value") or [])
        got_set = sorted(pred.get("liable_set") or pred.get("result_set") or [])
        return {"match": exp_set == got_set, "expected": exp_set, "got": got_set}

    if mode == "boolean":
        exp_val = bool(expected.get("value"))
        got_val = bool(pred.get("is_liable"))
        # Optional target consistency check
        target = expected.get("target")
        if target and pred.get("target") and target != pred.get("target"):
            return {"match": False, "reason": "target mismatch", "expected_target": target, "got_target": pred.get("target")}
        return {"match": exp_val == got_val, "expected": exp_val, "got": got_val}

    return {"match": False, "reason": "unsupported mode: " + str(mode)}
