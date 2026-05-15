#!/usr/bin/env python3
"""Rerun evaluation cells where matrix.json has ok=false (same pipeline/kb flags as evaluation_cli)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--matrix", type=Path, required=True, help="Path to matrix.json")
    p.add_argument(
        "--skip",
        type=int,
        default=0,
        metavar="N",
        help="Skip the first N failed cells (resume a long batch).",
    )
    p.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Log file (default: <matrix_dir>/rerun_failures_console.log).",
    )
    args = p.parse_args()
    matrix_path = args.matrix.resolve()
    if not matrix_path.is_file():
        print("Not a file:", matrix_path, file=sys.stderr)
        return 1

    log_path = args.log
    if log_path is None:
        log_path = matrix_path.parent / "rerun_failures_console.log"
    log_path = log_path.resolve()

    m = json.loads(matrix_path.read_text(encoding="utf-8"))
    cli = m.get("evaluation_cli") or {}
    pb = cli.get("pipeline_backend") or "json_ir"
    kb = cli.get("kb_backend")
    runs_dir = Path(m["runs_dir"])
    if not runs_dir.is_absolute():
        runs_dir = (_ROOT / runs_dir).resolve()

    fails_all: list[tuple[str, str, Path]] = []
    for r, row in m["cells"].items():
        for s, c in row.items():
            if not c.get("ok"):
                fails_all.append((r, s, Path(c["path"])))

    total_failed = len(fails_all)
    if args.skip:
        if args.skip < 0 or args.skip > total_failed:
            print("--skip out of range", file=sys.stderr)
            return 1
        fails = fails_all[args.skip :]
        print("After --skip", args.skip, "remaining cells:", len(fails), flush=True)
    else:
        fails = fails_all

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_mode = "a" if args.skip else "w"
    with log_path.open(log_mode, encoding="utf-8") as logf:
        if args.skip:
            logf.write(f"\n\n--- resume skip={args.skip} (of {total_failed} failed in matrix) ---\n")
        else:
            logf.write(f"matrix={matrix_path}\n")
            logf.write(f"pipeline_backend={pb!r} kb_backend={kb!r}\n")
            logf.write(f"cells_failed_in_matrix={total_failed}\n\n")

    cmd_prefix = [
        sys.executable,
        "-u",
        str(_ROOT / "main.py"),
        "--mode",
        "json",
        "--pipeline-backend",
        pb,
    ]
    if kb is not None:
        cmd_prefix.extend(["--kb-backend", str(kb)])

    exit_any = 0
    summary: list[tuple[str, str, int, str]] = []
    for r, s, wdir in fails:
        wdir = wdir.resolve()
        banner = f"\n{'=' * 80}\nRERUN {r} + {s}\n  work_dir={wdir}\n{'=' * 80}\n"
        print(banner, flush=True)
        with log_path.open("a", encoding="utf-8") as logf:
            logf.write(banner)

        if not wdir.is_dir():
            msg = f"MISSING work dir: {wdir}\n"
            print(msg, file=sys.stderr, flush=True)
            with log_path.open("a", encoding="utf-8") as logf:
                logf.write(msg)
            exit_any = 1
            summary.append((r, s, 999, "missing_dir"))
            continue

        if not (wdir / "run.json").is_file():
            src = runs_dir / r
            if (src / "run.json").is_file():
                wdir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src / "run.json", wdir / "run.json")
            else:
                msg = f"No run.json in {wdir} or {src}\n"
                print(msg, file=sys.stderr, flush=True)
                with log_path.open("a", encoding="utf-8") as logf:
                    logf.write(msg)
                exit_any = 1
                summary.append((r, s, 998, "no_run_json"))
                continue

        cmd = cmd_prefix + ["--run", str(wdir), "--kb-strategy", s]
        with log_path.open("a", encoding="utf-8") as logf:
            logf.write("CMD: " + subprocess.list2cmdline(cmd) + "\n")
            p = subprocess.run(
                cmd,
                cwd=str(_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            logf.write(p.stdout or "")
            logf.write(f"\n--- exit {p.returncode} ---\n")
        out = p.stdout or ""
        try:
            print(out, end="", flush=True)
        except UnicodeEncodeError:
            enc = getattr(sys.stdout, "encoding", None) or "utf-8"
            print(out.encode(enc, errors="replace").decode(enc, errors="replace"), end="", flush=True)
        print(f"--- exit {p.returncode} ---", flush=True)
        if p.returncode != 0:
            exit_any = 1
        tail = (p.stdout or "").splitlines()[-8:]
        hint = " | ".join(t.strip() for t in tail if t.strip())[:200]
        summary.append((r, s, p.returncode, hint))

    print("\n" + "=" * 80 + "\nSUMMARY (run, strategy, exit, tail)\n" + "=" * 80, flush=True)
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write("\n" + "=" * 80 + "\nSUMMARY\n" + "=" * 80 + "\n")
        for r, s, code, hint in summary:
            line = f"{r}\t{s}\t{code}\t{hint}\n"
            print(line.rstrip(), flush=True)
            logf.write(line)
    print("\nDone. Full log:", log_path, flush=True)
    return exit_any


if __name__ == "__main__":
    raise SystemExit(main())
