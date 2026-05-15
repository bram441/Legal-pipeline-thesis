"""
Shared helpers for KB strategy evaluation (used by run_evaluation.py and compare_kb_strategies.py).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.kb.compile_strategy import STRATEGY_CHOICES  # noqa: E402


def copy_run_json(src_run_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_run_dir / "run.json", dest_dir / "run.json")


def run_main_json(
    run_dir: Path,
    strategy: str,
    no_translate: bool,
    kb_backend: str | None = None,
    pipeline_backend: str | None = None,
    *,
    belief_scoring: bool = False,
) -> int:
    """Invoke ``main.py --mode json``. Omit ``--kb-backend`` / ``--pipeline-backend`` when
    arguments are ``None`` so the subprocess follows ``.env`` defaults.
    """
    cmd = [
        sys.executable,
        str(_ROOT / "main.py"),
        "--mode",
        "json",
        "--run",
        str(run_dir),
        "--kb-strategy",
        strategy,
    ]
    if no_translate:
        cmd.append("--no-translate")
    if kb_backend is not None:
        cmd.extend(["--kb-backend", kb_backend])
    if pipeline_backend is not None:
        cmd.extend(["--pipeline-backend", pipeline_backend])
    env = os.environ.copy()
    if belief_scoring:
        env["SCORE_TREAT_OPEN_WITH_BELIEF"] = "1"
        env.setdefault("SCORE_BOOLEAN_BELIEF_THRESHOLD", "0.5")
    return subprocess.call(cmd, cwd=str(_ROOT), env=env)


def read_score(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def discover_json_runs(runs_dir: Path) -> list[Path]:
    """Subdirectories of runs_dir that contain run.json, sorted by name."""
    if not runs_dir.is_dir():
        return []
    out = []
    for p in sorted(runs_dir.iterdir()):
        if p.is_dir() and (p / "run.json").is_file():
            out.append(p.resolve())
    return out


def parse_runs_selection(runs_dir: Path, spec: str) -> list[Path]:
    """
    spec: 'all' or comma-separated folder names (e.g. run_001,run_003).
    Paths are resolved under runs_dir.
    """
    spec = (spec or "all").strip()
    if spec.lower() == "all":
        return discover_json_runs(runs_dir)
    names = [x.strip() for x in spec.split(",") if x.strip()]
    out = []
    for name in names:
        p = runs_dir / name
        if not (p / "run.json").is_file():
            raise FileNotFoundError("No run.json in " + str(p.resolve()))
        out.append(p.resolve())
    return out


def parse_strategies_selection(spec: str) -> list[str]:
    spec = (spec or "all").strip()
    if spec.lower() == "all":
        return list(STRATEGY_CHOICES)
    names = [x.strip() for x in spec.split(",") if x.strip()]
    for n in names:
        if n not in STRATEGY_CHOICES:
            raise ValueError(
                "Unknown strategy %r. Expected one of: %s" % (n, ", ".join(STRATEGY_CHOICES))
            )
    return names


def work_dir_name(
    run_folder: Path,
    strategy: str,
    *,
    pipeline_backend: str | None = None,
    kb_backend: str | None = None,
) -> str:
    """Filesystem-safe unique name, e.g. ``run_003__direct_single__json_ir``.

    Includes a backend suffix so two evaluation sweeps (legacy vs json_ir) do not
    overwrite the same work directory.
    """
    base = run_folder.name + "__" + strategy
    if pipeline_backend:
        return base + "__" + pipeline_backend.replace("/", "_")
    if kb_backend:
        return base + "__" + kb_backend.replace("/", "_")
    return base


def _gather_eval_diag_text(work_dir: Path) -> str:
    """Concatenate run trace and KB compile logs for heuristic failure classification."""
    parts: list[str] = []
    trace = work_dir / "run_trace.txt"
    if trace.is_file():
        try:
            parts.append(trace.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    try:
        for log in sorted(work_dir.rglob("kb_compile.log")):
            try:
                parts.append(log.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    except OSError:
        pass
    return "\n".join(parts)


def classify_failure(work_dir: Path, exit_code: int, *, ok: bool) -> str:
    """
    Coarse category for evaluation matrix cells (debugging poor benchmark runs).

    ok=True, exit_code=0: pipeline finished; use ``completed`` or ``completed_with_errors``
    if results.json shows per-question failures.

    ok=False or non-zero exit: infer from run_trace.txt / kb_compile.log when present.
    """
    work_dir = work_dir.resolve()

    if ok and exit_code == 0:
        results_path = work_dir / "results.json"
        if results_path.is_file():
            try:
                data = json.loads(results_path.read_text(encoding="utf-8"))
                for q in data.get("questions") or []:
                    pipe = (q or {}).get("pipeline") or {}
                    if pipe.get("error_stage") or pipe.get("error"):
                        return "completed_with_errors"
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        return "completed"

    blob_l = _gather_eval_diag_text(work_dir).lower()

    if exit_code != 0 and not blob_l.strip():
        return "process_error"

    if "translation failed" in blob_l:
        return "translation"
    if "case extraction failed" in blob_l:
        return "case_extraction"
    if "kb compilation failed after" in blob_l:
        return "kb_repair_exhausted"
    if "law compilation failed" in blob_l or "kb compilation failed (llm call)" in blob_l:
        return "law_compilation"
    if "kb lint:" in blob_l or "kb lint failed" in blob_l:
        return "kb_lint"
    if "idp failed to parse" in blob_l or "failed to parse compiled kb" in blob_l:
        return "kb_idp_parse"
    if "kbsemanticerror" in blob_l or "theory is unsatisfiable" in blob_l:
        return "kb_semantic"
    if "symbolic reasoning failed" in blob_l or "symbol not in vocabulary" in blob_l:
        return "reasoning_symbol_mismatch"
    if "validation failed (case/query)" in blob_l:
        return "case_query_validation"
    if "validation failed" in blob_l and "(error)" in blob_l:
        return "kb_compile_validation"
    if exit_code != 0:
        return "process_error"
    return "unknown"
