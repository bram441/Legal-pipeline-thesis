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


def merge_json_run_file(run_dir, updates):
    """
    Merge ``updates`` into existing run.json (creates nothing if run.json is missing).
    Used to record kb_compile_strategy after a run.
    """
    path = os.path.join(run_dir, "run.json")
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return
    data.update(updates)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
