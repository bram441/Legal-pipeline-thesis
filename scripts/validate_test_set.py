#!/usr/bin/env python
"""
Static validator for a tiered JSON benchmark directory (default: inputs/json_final).

Does not call OpenAI, IDP-Z3, KB compilation, extraction, or run_evaluation.py.

Usage (from project root):
  python scripts/validate_test_set.py --input-dir inputs/json_final
  python scripts/validate_test_set.py --input-dir inputs/json_final --strict
  python scripts/validate_test_set.py --input-dir inputs/json_final --json-output reports/validation_summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

VALID_GROUPS = frozenset({"core", "challenge", "stress", "external_verus_lm"})
VALID_DIFFICULTIES = frozenset({"basic", "intermediate", "hard"})
VALID_DOMAINS = frozenset({"inheritance", "immigration", "company"})
VALID_PHENOMENA = frozenset(
    {
        "classification",
        "definition",
        "legal_effect",
        "temporal",
        "numeric_threshold",
        "negative_exclusion",
        "structural_exclusion",
        "case_given_criteria",
        "open_world",
    }
)
VALID_MODES = frozenset({"boolean", "set", "range", "explanation"})
MODES_REQUIRING_VALUE = frozenset({"boolean", "set", "range"})

FORBIDDEN_ARTIFACT_NAMES = frozenset(
    {
        "results.json",
        "score.json",
        "run_trace.txt",
        "effective_config.json",
        "schema_environment.json",
        "case_entity_type_mapping.json",
        "pre_solver_domain_validation.json",
        "symbolic_proof_gap.json",
        "factual_criteria_mode_diagnostics.json",
        "case_factual_input_diagnostics.json",
        "case_extraction_repair.json",
        "threshold_exclusion_gap.json",
        "threshold_numeric_helper_gap.json",
        "llm_calls.jsonl",
        "llm_call_summary.json",
        "kb.fo",
        "kb_schema.json",
    }
)
FORBIDDEN_ARTIFACT_DIRS = frozenset(
    {
        "translated",
        "json_ir_compile",
        "kb_strategy_compare",
        "work",
    }
)


def _err(errors: list[str], msg: str) -> None:
    errors.append(msg)


def _warn(warnings: list[str], msg: str) -> None:
    warnings.append(msg)


def _load_manifest(input_dir: Path) -> dict | None:
    path = input_dir / "manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError("Invalid manifest.json: " + str(e)) from e


def _discover_run_dirs(input_dir: Path) -> list[Path]:
    out = []
    for p in sorted(input_dir.iterdir()):
        if p.is_dir() and p.name.startswith("run_") and (p / "run.json").is_file():
            out.append(p)
    return out


def _validate_question(q: dict, run_id: str, qi: int, errors: list[str]) -> None:
    prefix = "%s question[%d]" % (run_id, qi)
    if not isinstance(q, dict):
        _err(errors, prefix + ": must be an object")
        return
    qid = q.get("id")
    if not (isinstance(qid, str) and qid.strip()):
        _err(errors, prefix + ": missing question id")
    text = q.get("text")
    if not (isinstance(text, str) and text.strip()):
        _err(errors, prefix + ": missing question text")
    expected = q.get("expected")
    if not isinstance(expected, dict):
        _err(errors, prefix + ": missing expected object")
        return
    mode = expected.get("mode")
    if mode not in VALID_MODES:
        _err(errors, prefix + ": expected.mode must be one of " + ", ".join(sorted(VALID_MODES)))
    else:
        if mode in MODES_REQUIRING_VALUE and "value" not in expected:
            _err(errors, prefix + ": expected.value required for mode=%r" % mode)
    reason = expected.get("reason")
    if not (isinstance(reason, str) and reason.strip()):
        _err(errors, prefix + ": missing expected.reason")


def _validate_run_json(run_dir: Path, errors: list[str], warnings: list[str]) -> dict | None:
    path = run_dir / "run.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        _err(errors, "%s: cannot read run.json: %s" % (run_dir.name, e))
        return None
    if not isinstance(data, dict):
        _err(errors, "%s: run.json root must be an object" % run_dir.name)
        return None
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        _err(errors, "%s: questions must be a non-empty list" % run_dir.name)
        return data
    for i, q in enumerate(questions):
        _validate_question(q, run_dir.name, i, errors)
    return data


def _scan_generated_artifacts(input_dir: Path, errors: list[str]) -> None:
    for run_dir in _discover_run_dirs(input_dir):
        for name in FORBIDDEN_ARTIFACT_NAMES:
            p = run_dir / name
            if p.is_file():
                _err(errors, "%s: forbidden generated file %s" % (run_dir.name, name))
        for sub in run_dir.rglob("*"):
            if sub.is_file() and sub.name in FORBIDDEN_ARTIFACT_NAMES:
                rel = sub.relative_to(run_dir)
                _err(errors, "%s: forbidden generated file %s" % (run_dir.name, rel.as_posix()))
        for dname in FORBIDDEN_ARTIFACT_DIRS:
            p = run_dir / dname
            if p.is_dir():
                _err(errors, "%s: forbidden generated directory %s/" % (run_dir.name, dname))


def _validate_manifest_entry(entry: dict, errors: list[str], warnings: list[str]) -> None:
    rid = entry.get("id") or "?"
    for key in ("law_domain", "evaluation_group", "difficulty", "phenomena"):
        if key not in entry:
            _err(errors, "manifest %s: missing %s" % (rid, key))
    domain = entry.get("law_domain")
    if domain not in VALID_DOMAINS:
        _err(
            errors,
            "manifest %s: law_domain %r not in %s"
            % (rid, domain, ", ".join(sorted(VALID_DOMAINS))),
        )
    group = entry.get("evaluation_group")
    if group not in VALID_GROUPS:
        _err(
            errors,
            "manifest %s: evaluation_group %r not in %s"
            % (rid, group, ", ".join(sorted(VALID_GROUPS))),
        )
    diff = entry.get("difficulty")
    if diff not in VALID_DIFFICULTIES:
        _err(
            errors,
            "manifest %s: difficulty %r not in %s"
            % (rid, diff, ", ".join(sorted(VALID_DIFFICULTIES))),
        )
    phen = entry.get("phenomena")
    if not isinstance(phen, list) or not phen:
        _err(errors, "manifest %s: phenomena must be a non-empty list" % rid)
    elif isinstance(phen, list):
        for p in phen:
            if p not in VALID_PHENOMENA:
                _err(
                    errors,
                    "manifest %s: unknown phenomenon %r" % (rid, p),
                )


def validate_test_set(
    input_dir: Path,
    *,
    strict: bool = False,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if not input_dir.is_dir():
        _err(errors, "Not a directory: " + str(input_dir))
        return _summary(input_dir, errors, warnings, strict, manifest=None, run_dirs=[])

    readme = input_dir / "README_TEST_SET.md"
    if not readme.is_file():
        _err(errors, "Missing README_TEST_SET.md")

    try:
        manifest = _load_manifest(input_dir)
    except ValueError as e:
        _err(errors, str(e))
        manifest = None

    if manifest is None:
        _err(errors, "Missing manifest.json")
        return _summary(input_dir, errors, warnings, strict, manifest=None, run_dirs=[])

    runs_list = manifest.get("runs")
    if not isinstance(runs_list, list):
        _err(errors, "manifest.json: runs must be a list")
        runs_list = []

    manifest_ids: list[str] = []
    seen_ids: set[str] = set()
    for entry in runs_list:
        if not isinstance(entry, dict):
            _err(errors, "manifest runs: each entry must be an object")
            continue
        rid = entry.get("id")
        if not isinstance(rid, str) or not rid.strip():
            _err(errors, "manifest entry missing id")
            continue
        if rid in seen_ids:
            _err(errors, "Duplicate manifest id: " + rid)
        seen_ids.add(rid)
        manifest_ids.append(rid)
        _validate_manifest_entry(entry, errors, warnings)
        rel = entry.get("path") or (rid + "/run.json")
        run_path = input_dir / str(rel).replace("\\", "/")
        if not run_path.is_file():
            _err(errors, "manifest %s: missing file %s" % (rid, rel))

    run_dirs = _discover_run_dirs(input_dir)
    disk_ids = {p.name for p in run_dirs}
    manifest_id_set = set(manifest_ids)
    for rid in sorted(manifest_id_set - disk_ids):
        _err(errors, "manifest lists %s but folder is missing" % rid)
    for rid in sorted(disk_ids - manifest_id_set):
        _err(errors, "folder %s exists but is not listed in manifest" % rid)

    for run_dir in run_dirs:
        _validate_run_json(run_dir, errors, warnings)

    _scan_generated_artifacts(input_dir, errors)

    return _summary(input_dir, errors, warnings, strict, manifest, run_dirs)


def _summary(
    input_dir: Path,
    errors: list[str],
    warnings: list[str],
    strict: bool,
    manifest: dict | None,
    run_dirs: list[Path],
) -> dict:
    group_c = Counter()
    diff_c = Counter()
    domain_c = Counter()
    phen_c = Counter()

    if manifest and isinstance(manifest.get("runs"), list):
        for entry in manifest["runs"]:
            if not isinstance(entry, dict):
                continue
            group_c[entry.get("evaluation_group") or "?"] += 1
            diff_c[entry.get("difficulty") or "?"] += 1
            domain_c[entry.get("law_domain") or "?"] += 1
            for p in entry.get("phenomena") or []:
                phen_c[p] += 1

    all_issues = list(errors)
    if strict:
        all_issues.extend(warnings)

    out = {
        "input_dir": str(input_dir.resolve()),
        "valid": len(all_issues) == 0,
        "strict": strict,
        "run_count": len(run_dirs) if run_dirs else len(manifest.get("runs", [])) if manifest else 0,
        "counts_by_evaluation_group": dict(sorted(group_c.items())),
        "counts_by_difficulty": dict(sorted(diff_c.items())),
        "counts_by_law_domain": dict(sorted(domain_c.items())),
        "counts_by_phenomenon": dict(sorted(phen_c.items())),
        "errors": errors,
        "warnings": warnings,
    }
    return out


def _print_report(summary: dict) -> None:
    print("Test set:", summary["input_dir"])
    print("Runs:", summary["run_count"])
    print("By evaluation_group:", summary["counts_by_evaluation_group"])
    print("By difficulty:", summary["counts_by_difficulty"])
    print("By law_domain:", summary["counts_by_law_domain"])
    print("By phenomenon:", summary["counts_by_phenomenon"])
    if summary["warnings"]:
        print("\nWarnings (%d):" % len(summary["warnings"]))
        for w in summary["warnings"]:
            print("  -", w)
    if summary["errors"]:
        print("\nErrors (%d):" % len(summary["errors"]))
        for e in summary["errors"]:
            print("  -", e)
    else:
        print("\nNo errors.")
    print("\nValid:", "yes" if summary["valid"] else "no")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--input-dir",
        default="inputs/json_final",
        help="Benchmark root containing manifest.json and run_* folders",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors",
    )
    p.add_argument(
        "--json-output",
        default=None,
        metavar="PATH",
        help="Write validation_summary.json to this path",
    )
    args = p.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_absolute():
        input_dir = (_ROOT / input_dir).resolve()

    summary = validate_test_set(input_dir, strict=args.strict)
    _print_report(summary)

    if args.json_output:
        out_path = Path(args.json_output)
        if not out_path.is_absolute():
            out_path = _ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Wrote:", out_path)

    return 0 if summary["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
