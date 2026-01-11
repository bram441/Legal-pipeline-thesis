# pipeline/io/json_runs.py

import json
import os


def load_json_run(run_dir):
    """
    Loads a JSON-based run folder containing run.json.

    Returns:
      dict parsed from JSON (must include law.text, case.text, questions[])
    """
    path = os.path.join(run_dir, "run.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_results(run_dir, results_obj):
    """
    Writes results.json in the run folder.
    """
    path = os.path.join(run_dir, "results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results_obj, f, ensure_ascii=False, indent=2)


def write_score(run_dir, score_obj):
    """
    Writes score.json in the run folder.
    """
    path = os.path.join(run_dir, "score.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(score_obj, f, ensure_ascii=False, indent=2)
