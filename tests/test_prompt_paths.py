"""Prompt registry: canonical paths, aliases, no direct legacy file usage in code."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline.utils.prompt_loader import PROMPTS_DIR
from pipeline.utils.prompt_paths import PROMPT_ALIASES, REQUIRED_PROMPT_PATHS, resolve_prompt_path

_ROOT = Path(__file__).resolve().parents[1]


def test_required_prompt_paths_exist():
    missing = []
    for rel in REQUIRED_PROMPT_PATHS:
        path = PROMPTS_DIR / rel.replace("\\", "/")
        if not path.is_file():
            missing.append(rel)
    assert not missing, "Missing prompt files: " + ", ".join(missing)


def test_aliases_resolve_to_existing_canonical_files():
    for old, canonical in PROMPT_ALIASES.items():
        resolved = resolve_prompt_path(old)
        assert resolved == canonical
        path = PROMPTS_DIR / canonical
        assert path.is_file(), f"Alias {old} -> {canonical} missing at {path}"


def test_legacy_alias_source_files_are_not_duplicated_on_disk():
    """Old alias paths should not exist as separate files (loader uses canonical only)."""
    duplicates = []
    for old in PROMPT_ALIASES:
        legacy_path = PROMPTS_DIR / old.replace("\\", "/")
        if legacy_path.is_file():
            duplicates.append(str(legacy_path.relative_to(_ROOT)))
    assert not duplicates, "Remove duplicate legacy prompt files: " + ", ".join(duplicates)


def test_python_code_does_not_load_legacy_alias_paths_directly():
    """Call sites should use canonical paths or constants from prompt_paths."""
    alias_keys = set(PROMPT_ALIASES.keys())
    offenders = []
    pattern = re.compile(r'load_prompt\(\s*["\']([^"\']+)["\']')
    pattern2 = re.compile(r'render_prompt\(\s*["\']([^"\']+)["\']')
    for py in _ROOT.rglob("*.py"):
        if "tests" in py.parts or ".venv" in py.parts:
            continue
        if py.name in {"prompt_paths.py", "prompt_loader.py"}:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for m in pattern.finditer(text):
            if m.group(1) in alias_keys:
                offenders.append(f"{py.relative_to(_ROOT)}: load_prompt({m.group(1)!r})")
        for m in pattern2.finditer(text):
            if m.group(1) in alias_keys:
                offenders.append(f"{py.relative_to(_ROOT)}: render_prompt({m.group(1)!r})")
    assert not offenders, "Use canonical prompt paths:\n" + "\n".join(offenders)
