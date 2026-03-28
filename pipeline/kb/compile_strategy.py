"""
KB compilation strategy: combines PIPELINE_USE_LE and PIPELINE_KB_TWO_PHASE.

Strategies:
  direct_single     — law → single-shot FO
  direct_two_phase  — law → vocab → theory
  le_single         — law → LE → single-shot FO
  le_two_phase      — law → LE → vocab → theory
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

# strategy_name -> (use_le, two_phase)
STRATEGIES: dict[str, tuple[bool, bool]] = {
    "direct_single": (False, False),
    "direct_two_phase": (False, True),
    "le_single": (True, False),
    "le_two_phase": (True, True),
}

STRATEGY_CHOICES = tuple(STRATEGIES.keys())


def strategy_to_flags(name: str) -> tuple[bool, bool]:
    if name not in STRATEGIES:
        raise ValueError(
            "Unknown kb_compile_strategy: "
            + repr(name)
            + ". Expected one of: "
            + ", ".join(STRATEGY_CHOICES)
        )
    return STRATEGIES[name]


def flags_to_strategy(use_le: bool, two_phase: bool) -> str:
    for label, (ul, tp) in STRATEGIES.items():
        if ul == use_le and tp == two_phase:
            return label
    return "custom"


def flags_from_process_env() -> tuple[bool, bool]:
    """Current effective flags from environment (same rules as use_le_enabled / two_phase_enabled)."""
    le = (os.getenv("PIPELINE_USE_LE") or "").strip().lower() in ("1", "true", "yes", "on")
    tp = (os.getenv("PIPELINE_KB_TWO_PHASE") or "").strip().lower() in ("1", "true", "yes", "on")
    return le, tp


def resolve_strategy_label(
    cli_strategy: str | None,
    run_json: dict[str, Any] | None,
) -> str | None:
    """
    Resolution order: CLI > run.json kb_compile_strategy > None (keep process env).

    Returns canonical strategy name or None.
    """
    if cli_strategy:
        strategy_to_flags(cli_strategy)  # validate
        return cli_strategy
    if run_json:
        s = run_json.get("kb_compile_strategy")
        if isinstance(s, str) and s.strip():
            strategy_to_flags(s.strip())
            return s.strip()
    return None


def kb_run_context(cli_strategy: str | None, run_json: dict[str, Any] | None, mode: str):
    """
    Build a context manager for KB env overrides and the resolved strategy label.

    Priority: CLI ``cli_strategy`` > ``run_json["kb_compile_strategy"]`` > process env.

    Returns:
      (context_manager, resolved_label) where ``resolved_label`` is always a canonical name.
    """
    from contextlib import nullcontext

    resolved = resolve_strategy_label(cli_strategy, run_json if mode == "json" else None)
    if resolved is not None:
        use_le, two_phase = strategy_to_flags(resolved)
        return kb_compile_env_overrides(use_le, two_phase), resolved
    use_le, two_phase = flags_from_process_env()
    return nullcontext(), flags_to_strategy(use_le, two_phase)


@contextmanager
def kb_compile_env_overrides(use_le: bool, two_phase: bool):
    """Temporarily set PIPELINE_USE_LE and PIPELINE_KB_TWO_PHASE; restore after."""
    keys = ("PIPELINE_USE_LE", "PIPELINE_KB_TWO_PHASE")
    saved = {k: os.environ.get(k) for k in keys}
    try:
        os.environ["PIPELINE_USE_LE"] = "1" if use_le else "0"
        os.environ["PIPELINE_KB_TWO_PHASE"] = "1" if two_phase else "0"
        yield
    finally:
        for k in keys:
            v = saved[k]
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
