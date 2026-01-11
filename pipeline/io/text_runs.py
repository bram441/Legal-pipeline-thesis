# pipeline/io/text_runs.py

import os


def load_text_run(run_dir):
    """
    Loads a text-based run folder:
      - law.txt
      - case.txt
      - questions.txt

    Returns:
      dict with keys: law_text, case_text, questions (list[str])
    """
    law_path = os.path.join(run_dir, "law.txt")
    case_path = os.path.join(run_dir, "case.txt")
    questions_path = os.path.join(run_dir, "questions.txt")

    with open(law_path, "r", encoding="utf-8") as f:
        law_text = f.read().strip()

    with open(case_path, "r", encoding="utf-8") as f:
        case_text = f.read().strip()

    with open(questions_path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines()]

    questions = [ln for ln in lines if ln]

    return {
        "law_text": law_text,
        "case_text": case_text,
        "questions": questions,
    }


def write_text_results(run_dir, results_text):
    """
    Writes results.txt in the run folder.
    """
    out_path = os.path.join(run_dir, "results.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(results_text)
