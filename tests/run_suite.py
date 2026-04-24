# tests/run_suite.py
import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on path so 'tests' and 'pipeline' can be imported
_root = Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from tests.metrics import set_equal, any_set_equal, prf1
from tests.report import write_report
from dotenv import load_dotenv
from pipeline.kb.schema import extract_schema_from_kb_fo
from pipeline.app.pipeline import answer_legal_prompt

try:
    from pipeline.kb.cache import get_or_compile_kb
except Exception:
    get_or_compile_kb = None


def read_text(path):
    return Path(path).read_text(encoding="utf-8").strip()

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def discover_cases(suite_dir):
    suite_path = Path(suite_dir)
    for case_dir in sorted(suite_path.iterdir()):
        if not case_dir.is_dir():
            continue

        expected = case_dir / "expected.json"
        if not expected.exists():
            continue

        yield case_dir.name, case_dir, expected

def load_kb_text(case_dir, allow_compile, kb_model):
    kb_path = case_dir / "kb.fo"
    if kb_path.exists():
        return read_text(kb_path), "file"

    law_path = case_dir / "law.txt"
    if not law_path.exists():
        raise RuntimeError("Missing kb.fo and law.txt in " + str(case_dir))

    if not allow_compile:
        raise RuntimeError("No kb.fo provided and --allow-compile-kb is disabled")

    if get_or_compile_kb is None:
        raise RuntimeError("pipeline.kb.cache.get_or_compile_kb not available in this project state")

    law_text = read_text(law_path)

    # Use a deterministic per-case cache folder (so reruns are stable)
    cache_run_dir = Path(".cache") / "tests" / case_dir.name
    cache_run_dir.mkdir(parents=True, exist_ok=True)

    kb_text, kb_schema = get_or_compile_kb(str(cache_run_dir), law_text, model=kb_model)
    return kb_text, "compiled"

def score_boolean(prediction, expected):
    got = prediction.get("label")
    gold = expected.get("label")

    acceptable = expected.get("acceptable_labels")
    if acceptable:
        ok = str(got) in [str(x) for x in acceptable]
    else:
        ok = str(got) == str(gold)

    return {
        "mode": "boolean",
        "got": got,
        "gold": gold,
        "acceptable_labels": acceptable,
        "passed": bool(ok),
    }

def score_set(prediction, expected):
    got_c = prediction.get("certain_set", [])
    got_p = prediction.get("possible_set", [])

    gold_c = expected.get("certain_set", [])
    gold_p = expected.get("possible_set", [])

    acceptable_c = expected.get("acceptable_certain_sets")
    acceptable_p = expected.get("acceptable_possible_sets")

    if acceptable_c:
        ok_c = any_set_equal(got_c, acceptable_c)
    else:
        ok_c = set_equal(got_c, gold_c)

    if acceptable_p:
        ok_p = any_set_equal(got_p, acceptable_p)
    else:
        ok_p = set_equal(got_p, gold_p)

    pc, rc, f1c = prf1(got_c, gold_c)
    pp, rp, f1p = prf1(got_p, gold_p)

    return {
        "mode": "set",
        "got": {"certain_set": got_c, "possible_set": got_p},
        "gold": {"certain_set": gold_c, "possible_set": gold_p},
        "acceptable": {"certain": acceptable_c, "possible": acceptable_p},
        "passed": bool(ok_c and ok_p),
        "prf1": {
            "certain": {"precision": pc, "recall": rc, "f1": f1c},
            "possible": {"precision": pp, "recall": rp, "f1": f1p},
        },
    }

def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True, help="Path to suite folder, e.g. tests/suites/baseline_v1")
    parser.add_argument("--provider", default="openai", help="Extractor provider, e.g. auto/openai")
    parser.add_argument("--model", default=None, help="Extractor model override")
    parser.add_argument("--max-retries", type=int, default=2, help="Extractor max retries")
    parser.add_argument("--out", default="tests/reports", help="Output directory for JSON reports")

    parser.add_argument("--allow-compile-kb", action="store_true",
                        help="If kb.fo is missing, compile from law.txt via KB compiler")
    parser.add_argument("--kb-model", default=None, help="Model for KB compilation when --allow-compile-kb is enabled")

    parser.add_argument("--print-failures", action="store_true", help="Print details for failing cases")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    suite_name = suite_path.name

    run_summary = {
        "suite": suite_name,
        "cases": [],
        "totals": {
            "count": 0,
            "passed": 0,
            "stage_failed": 0,
            "stage_counts": {}
        }
    }

    for case_id, case_dir, expected_path in discover_cases(args.suite):
        expected = read_json(expected_path)

        case_text_path = case_dir / "case.txt"
        question_text_path = case_dir / "question.txt"

        if not case_text_path.exists() or not question_text_path.exists():
            entry = {
                "case_id": case_id,
                "passed": False,
                "error": "Missing case.txt or question.txt",
                "stage": "setup"
            }
            run_summary["cases"].append(entry)
            run_summary["totals"]["count"] += 1
            run_summary["totals"]["stage_failed"] += 1
            run_summary["totals"]["stage_counts"]["setup"] = run_summary["totals"]["stage_counts"].get("setup", 0) + 1
            continue

        case_text = read_text(case_text_path)
        question_text = read_text(question_text_path)

        entry = {
            "case_id": case_id,
            "kb_source": None,
            "stage": "ok",
            "passed": False,
            "prediction": None,
            "score": None,
            "error": None
        }

        try:
            kb_text, kb_source = load_kb_text(case_dir, args.allow_compile_kb, args.kb_model)
            entry["kb_source"] = kb_source
            kb_schema = extract_schema_from_kb_fo(kb_text)

            result = answer_legal_prompt(
                case_text=case_text,
                user_question=question_text,
                base_kb_text=kb_text,
                extractor_provider=args.provider,
                extractor_model=args.model,
                extractor_max_retries=args.max_retries,
                kb_schema=kb_schema,
                debug=False,
            )

            if "error_stage" in result:
                entry["stage"] = result.get("error_stage")
                entry["error"] = result.get("error")
                entry["passed"] = False

            else:
                prediction = result.get("prediction")
                if not isinstance(prediction, dict):
                    entry["stage"] = "scoring"
                    entry["error"] = "Missing structured prediction. Ensure pipeline returns result['prediction']"
                    entry["passed"] = False
                else:
                    entry["prediction"] = prediction

                    if expected.get("smoke"):
                        # KB compiled from law text + full answer; no fixed gold labels (predicate names unknown).
                        entry["score"] = {"mode": "smoke", "passed": True}
                        entry["passed"] = True
                    else:
                        expected_mode = expected.get("query_mode")
                        got_mode = prediction.get("mode")

                        if expected_mode and got_mode and expected_mode != got_mode:
                            entry["stage"] = "scoring"
                            entry["error"] = "Mode mismatch. expected=" + str(expected_mode) + " got=" + str(got_mode)
                            entry["passed"] = False
                        else:
                            if got_mode == "boolean":
                                entry["score"] = score_boolean(prediction, expected)
                                entry["passed"] = bool(entry["score"]["passed"])
                            elif got_mode == "set":
                                entry["score"] = score_set(prediction, expected)
                                entry["passed"] = bool(entry["score"]["passed"])
                            else:
                                entry["stage"] = "scoring"
                                entry["error"] = "Unsupported prediction mode: " + str(got_mode)
                                entry["passed"] = False

        except Exception as e:
            entry["stage"] = "exception"
            entry["error"] = str(e)
            entry["passed"] = False

        run_summary["cases"].append(entry)
        run_summary["totals"]["count"] += 1

        if entry["passed"]:
            run_summary["totals"]["passed"] += 1
        else:
            stage = entry.get("stage") or "unknown"
            run_summary["totals"]["stage_failed"] += 1
            run_summary["totals"]["stage_counts"][stage] = run_summary["totals"]["stage_counts"].get(stage, 0) + 1

            if args.print_failures:
                print("FAIL", case_id, "stage=", stage, "error=", entry.get("error"))

    report_path = write_report(args.out, suite_name, run_summary)

    print("Suite:", suite_name)
    print("Passed:", run_summary["totals"]["passed"], "/", run_summary["totals"]["count"])
    print("Failures by stage:", run_summary["totals"]["stage_counts"])
    print("Report:", report_path)


if __name__ == "__main__":
    main()