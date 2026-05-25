"""Tests for scripts/validate_test_set.py."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "validate_test_set.py"


def _run_validator(tmp_path: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--input-dir", str(tmp_path), *extra_args],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )


def _minimal_fixture(tmp_path: Path) -> Path:
    (tmp_path / "README_TEST_SET.md").write_text("# test\n", encoding="utf-8")
    run_dir = tmp_path / "run_001"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "id": "run_001",
                "law": {"path": "example_laws/erfrecht.text"},
                "case": {"text": "Case."},
                "questions": [
                    {
                        "id": "q1",
                        "text": "Question?",
                        "expected": {
                            "mode": "boolean",
                            "value": True,
                            "reason": "Because the rule applies.",
                        },
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = {
        "version": 1,
        "runs": [
            {
                "id": "run_001",
                "path": "run_001/run.json",
                "law_domain": "inheritance",
                "evaluation_group": "core",
                "difficulty": "basic",
                "phenomena": ["legal_effect"],
            }
        ],
    }
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_valid_tiny_fixture_passes(tmp_path):
    _minimal_fixture(tmp_path)
    proc = _run_validator(tmp_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_missing_run_fails(tmp_path):
    import shutil

    _minimal_fixture(tmp_path)
    shutil.rmtree(tmp_path / "run_001")
    proc = _run_validator(tmp_path)
    assert proc.returncode != 0
    assert "missing" in (proc.stdout + proc.stderr).lower()


def test_missing_expected_reason_fails(tmp_path):
    root = _minimal_fixture(tmp_path)
    data = json.loads((root / "run_001" / "run.json").read_text(encoding="utf-8"))
    del data["questions"][0]["expected"]["reason"]
    (root / "run_001" / "run.json").write_text(json.dumps(data) + "\n", encoding="utf-8")
    proc = _run_validator(root)
    assert proc.returncode != 0
    assert "reason" in (proc.stdout + proc.stderr).lower()


def test_generated_artifact_fails(tmp_path):
    root = _minimal_fixture(tmp_path)
    (root / "run_001" / "score.json").write_text("{}", encoding="utf-8")
    proc = _run_validator(root)
    assert proc.returncode != 0
    assert "score.json" in proc.stdout + proc.stderr


def test_unknown_difficulty_fails(tmp_path):
    root = _minimal_fixture(tmp_path)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["runs"][0]["difficulty"] = "extreme"
    (root / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    proc = _run_validator(root)
    assert proc.returncode != 0
    assert "difficulty" in (proc.stdout + proc.stderr).lower()
