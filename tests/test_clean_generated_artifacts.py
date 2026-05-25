"""Clean generated artifacts from fixture run trees."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_clean_generated_artifacts_on_fixture_tree(tmp_path):
    run_dir = tmp_path / "run_fixture"
    run_dir.mkdir()
    (run_dir / "run.json").write_text("{}", encoding="utf-8")
    (run_dir / "results.json").write_text("{}", encoding="utf-8")
    (run_dir / "score.json").write_text("{}", encoding="utf-8")
    (run_dir / "translated").mkdir()
    (run_dir / "translated" / "kb.fo").write_text("vocabulary V {}", encoding="utf-8")
    (run_dir / "schema_environment.json").write_text("{}", encoding="utf-8")

    script = _ROOT / "scripts" / "clean_generated_artifacts.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--roots", str(tmp_path)],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    assert (run_dir / "run.json").is_file()
    assert not (run_dir / "results.json").exists()
    assert not (run_dir / "score.json").exists()
    assert not (run_dir / "translated").exists()
    assert not (run_dir / "schema_environment.json").exists()
