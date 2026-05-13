#!/usr/bin/env python3
"""Run `main.py --mode json` over a numeric range of run folders and print a short summary.

Example (from repo root):

  python scripts/batch_json_runs.py --base inputs/json --from 101 --to 110

Forward extra flags to main.py after ``--``::

  python scripts/batch_json_runs.py --base inputs/json --from 1 --to 3 -- --no-translate
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1 :]
    return argv, []


def _run_dir(base: Path, prefix: str, n: int, width: int) -> Path:
    return base / f"{prefix}{n:0{width}d}"


def _classify_failure(stderr: str, stdout: str) -> str:
    blob = (stderr + "\n" + stdout).lower()
    if "json ir validation failed" in blob or "lawcompilationerror" in blob:
        return "kb_compile"
    if "extractionerror" in blob or "llmextractionerror" in blob:
        return "extraction"
    if "translationfailed" in blob or "translation failed" in blob:
        return "translation"
    return "other"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    our_args, main_extra = _split_argv(argv)

    p = argparse.ArgumentParser(description="Batch JSON runs via main.py --mode json.")
    p.add_argument(
        "--base",
        type=Path,
        default=Path("inputs/json"),
        help="Directory containing run folders (default: inputs/json)",
    )
    p.add_argument("--from", dest="n_from", type=int, required=True, metavar="N")
    p.add_argument("--to", dest="n_to", type=int, required=True, metavar="N")
    p.add_argument("--prefix", default="run_", help="Folder name prefix (default: run_)")
    p.add_argument("--width", type=int, default=3, help="Zero-pad width for run number (default: 3)")
    p.add_argument("--python", default=sys.executable, help="Python executable to run main.py")
    p.add_argument("--dry-run", action="store_true", help="Print commands only")
    p.add_argument("--csv", type=Path, default=None, help="Write one row per run to this CSV path")
    args = p.parse_args(our_args)

    base = args.base
    if not base.is_absolute():
        base = (_PROJECT_ROOT / base).resolve()

    rows: list[dict[str, object]] = []
    for n in range(args.n_from, args.n_to + 1):
        rd = _run_dir(base, args.prefix, n, args.width)
        cmd = [
            str(args.python),
            str(_PROJECT_ROOT / "main.py"),
            "--mode",
            "json",
            "--run",
            str(rd),
            *main_extra,
        ]
        if args.dry_run:
            print(" ".join(cmd))
            rows.append({"run": str(rd), "status": "dry_run"})
            continue
        proc = subprocess.run(
            cmd,
            cwd=str(_PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        score_path = rd / "score.json"
        status = "ok"
        accuracy = ""
        inconclusive = ""
        failure_kind = ""
        if proc.returncode != 0:
            status = "failed"
            failure_kind = _classify_failure(proc.stderr or "", proc.stdout or "")
        elif not score_path.is_file():
            status = "incomplete"
            failure_kind = "no_score_json"
        else:
            try:
                sc = json.loads(score_path.read_text(encoding="utf-8"))
                acc = sc.get("accuracy")
                accuracy = "" if acc is None else f"{float(acc):.4f}"
                inconclusive = str(sc.get("inconclusive", ""))
            except (OSError, ValueError, TypeError):
                status = "incomplete"
                failure_kind = "bad_score_json"

        line = f"{rd.name}\t{status}\texit={proc.returncode}\taccuracy={accuracy}\tinconclusive={inconclusive}"
        if failure_kind:
            line += f"\tkind={failure_kind}"
        print(line)
        if status == "failed" and (proc.stderr or "").strip():
            tail = (proc.stderr or "").strip().splitlines()[-3:]
            for ln in tail:
                print("  stderr:", ln[:240])
        rows.append(
            {
                "run": str(rd),
                "name": rd.name,
                "status": status,
                "exit_code": proc.returncode,
                "accuracy": accuracy,
                "inconclusive": inconclusive,
                "failure_kind": failure_kind,
            }
        )

    if args.csv:
        outp = args.csv
        if not outp.is_absolute():
            outp = (_PROJECT_ROOT / outp).resolve()
        outp.parent.mkdir(parents=True, exist_ok=True)
        with outp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["run", "name", "status", "exit_code", "accuracy", "inconclusive", "failure_kind"])
            w.writeheader()
            w.writerows(rows)

    failed = sum(1 for r in rows if r.get("status") == "failed")
    bad = sum(1 for r in rows if r.get("status") not in ("ok", "dry_run"))
    if bad:
        return 1 if failed else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
