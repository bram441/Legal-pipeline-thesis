"""Pure module imports must not require idp_engine at import time."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _import_in_subprocess(module: str) -> None:
    """Import in a clean process with idp_engine blocked."""
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, r"{_ROOT}")
import importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_module(self, fullname, path=None):
        if fullname == "idp_engine" or fullname.startswith("idp_engine."):
            return self
        return None
    def load_module(self, fullname):
        raise ImportError("blocked idp_engine")
sys.meta_path.insert(0, Block())
import {module}
print("ok")
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_schema_environment_import_without_idp_engine():
    _import_in_subprocess("pipeline.kb.schema_environment")


def test_case_fact_validation_import_without_idp_engine():
    _import_in_subprocess("pipeline.extraction.case_fact_validation")


def test_entity_type_mapping_import_without_idp_engine():
    _import_in_subprocess("pipeline.validation.entity_type_mapping")


def test_pipeline_package_does_not_eagerly_import_idp_engine():
    """import pipeline should not load idp_engine (lazy __getattr__)."""
    code = f"""
import sys
from pathlib import Path
sys.path.insert(0, r"{_ROOT}")
import importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_module(self, fullname, path=None):
        if fullname == "idp_engine" or fullname.startswith("idp_engine."):
            return self
        return None
    def load_module(self, fullname):
        raise ImportError("blocked idp_engine")
sys.meta_path.insert(0, Block())
import pipeline
assert "idp_engine" not in sys.modules
print("ok")
"""
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_idp_integration_skips_when_unavailable():
    pytest.importorskip("idp_engine")
    backend = importlib.import_module("idp_z3.idp_backend")
    assert hasattr(backend, "run_idp")
