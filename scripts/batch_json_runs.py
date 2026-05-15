#!/usr/bin/env python3
"""Run ``main.py --mode json`` over a numeric range of run folders and print a short summary.

Examples (from repo root):

  # JSON-IR pipeline (default; explicit for reproducible thesis batches)
  python scripts/batch_json_runs.py --base inputs/json --from 101 --to 110

  # Legacy FO + legacy extraction
  python scripts/batch_json_runs.py --base inputs/json --from 1 --to 3 --pipeline-backend legacy

  # Optional: also pass --kb-backend (only when ``--pipeline-backend`` is omitted; see main.py)
  python scripts/batch_json_runs.py --base inputs/json --from 1 --to 1 --kb-backend json_ir

Forward *additional* flags to main.py after ``--`` (``--pipeline-backend`` / ``--kb-backend`` there are
removed if you set the same options via this script's flags; script flags win):

  python scripts/batch_json_runs.py --base inputs/json --from 1 --to 3 --pipeline-backend json_ir -- --no-translate
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from pipeline.kb.compile_backend import KB_BACKEND_CHOICES  # noqa: E402


def _split_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], argv[i + 1 :]
    return argv, []


def _strip_main_flag(extra: list[str], flag: str) -> list[str]:
    """Remove ``--flag``, ``--flag=value``, and ``--flag <value>`` tokens from forwarded argv."""
    out: list[str] = []
    i = 0
    n = len(extra)
    while i < n:
        tok = extra[i]
        if tok == flag:
            if i + 1 < n and not str(extra[i + 1]).startswith("-"):
                i += 2
            else:
                i += 1
            continue
        if tok.startswith(flag + "="):
            i += 1
            continue
        out.append(tok)
        i += 1
    return out


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

    p = argparse.ArgumentParser(
        description="Batch JSON runs via main.py --mode json. "
        "Sets --pipeline-backend explicitly by default (json_ir) so batches match run_evaluation "
        "and are not accidentally driven only by .env."
    )
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
    p.add_argument(
        "--pipeline-backend",
        default="json_ir",
        choices=["legacy", "json_ir"],
        help="Passed to every main.py invocation (default: json_ir). Same semantics as run_evaluation.py.",
    )
    p.add_argument(
        "--kb-backend",
        default=None,
        choices=list(KB_BACKEND_CHOICES),
        metavar="NAME",
        help="Optional: passed to main.py --kb-backend. When --pipeline-backend is set, main.py may ignore "
        "this flag; prefer --pipeline-backend alone unless you know you need both.",
    )
    args = p.parse_args(our_args)

    base = args.base
    if not base.is_absolute():
        base = (_PROJECT_ROOT / base).resolve()

    tail = _strip_main_flag(_strip_main_flag(list(main_extra), "--pipeline-backend"), "--kb-backend")

    if args.kb_backend and args.pipeline_backend:
        implied_kb = "json_ir" if args.pipeline_backend == "json_ir" else "legacy_fo"
        if args.kb_backend != implied_kb:
            print(
                "batch_json_runs: note: main.py ignores --kb-backend when --pipeline-backend is set "
                "(effective KB backend is "
                + implied_kb
                + ").",
                file=sys.stderr,
            )

    print(
        "batch_json_runs: pipeline_backend="
        + args.pipeline_backend
        + " kb_backend="
        + (args.kb_backend or "(omit)"),
        file=sys.stderr,
    )

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
            *tail,
            "--pipeline-backend",
            args.pipeline_backend,
        ]
        if args.kb_backend is not None:
            cmd.extend(["--kb-backend", args.kb_backend])
        if args.dry_run:
            print(" ".join(cmd))
            rows.append(
                {
                    "run": str(rd),
                    "name": rd.name,
                    "status": "dry_run",
                    "exit_code": 0,
                    "pipeline_backend": args.pipeline_backend,
                    "kb_backend": args.kb_backend or "",
                    "accuracy": "",
                    "inconclusive": "",
                    "failure_kind": "",
                }
            )
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

        line = (
            f"{rd.name}\t{status}\texit={proc.returncode}\tpipeline={args.pipeline_backend}"
            f"\taccuracy={accuracy}\tinconclusive={inconclusive}"
        )
        if failure_kind:
            line += f"\tkind={failure_kind}"
        print(line)
        if status == "failed" and (proc.stderr or "").strip():
            tail_err = (proc.stderr or "").strip().splitlines()[-3:]
            for ln in tail_err:
                print("  stderr:", ln[:240])
        rows.append(
            {
                "run": str(rd),
                "name": rd.name,
                "status": status,
                "exit_code": proc.returncode,
                "pipeline_backend": args.pipeline_backend,
                "kb_backend": args.kb_backend or "",
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
        fields = [
            "run",
            "name",
            "status",
            "exit_code",
            "pipeline_backend",
            "kb_backend",
            "accuracy",
            "inconclusive",
            "failure_kind",
        ]
        with outp.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)

    failed = sum(1 for r in rows if r.get("status") == "failed")
    bad = sum(1 for r in rows if r.get("status") not in ("ok", "dry_run"))
    if bad:
        return 1 if failed else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
