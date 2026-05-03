"""Credence summaries for boolean symbolic results (possible / certain).

Classical FO gives three epistemic cells: entailed, contradicted, or open (possible
but not certain). For open cases we optionally apply a configurable *prior* toward
Yes (``PIPELINE_OPEN_WORLD_P_YES``) so evaluation and NL can report a credence, not
a spurious false.
"""

from __future__ import annotations

import os


def open_world_p_yes() -> float:
    """Prior / credence toward Yes when the theory leaves the atom open (default 0.5)."""
    raw = (os.getenv("PIPELINE_OPEN_WORLD_P_YES") or "0.5").strip()
    try:
        v = float(raw)
    except ValueError:
        v = 0.5
    return max(0.0, min(1.0, v))


def summarize_boolean_symbolic(symbolic_result: dict | None) -> dict:
    """
    Map ``{certain, possible}`` to labels and credence.

    Returns keys:
      - label: "entailed" | "contradicted" | "unknown"
      - p_yes: float in [0,1] — credence that the atom holds
      - p_no: float in [0,1]
      - verdict_strength_pct: int 0..100 — how decisive (100 = entailed/contradicted)
      - credence_yes_pct: int 0..100 — round(p_yes * 100), useful for display
    """
    pred = symbolic_result or {}
    certain = bool(pred.get("certain"))
    possible = bool(pred.get("possible"))

    if certain:
        return {
            "label": "entailed",
            "p_yes": 1.0,
            "p_no": 0.0,
            "verdict_strength_pct": 100,
            "credence_yes_pct": 100,
        }
    if not possible:
        return {
            "label": "contradicted",
            "p_yes": 0.0,
            "p_no": 1.0,
            "verdict_strength_pct": 100,
            "credence_yes_pct": 0,
        }
    p_yes = open_world_p_yes()
    strength = int(round(abs(p_yes - 0.5) * 2.0 * 100))
    return {
        "label": "unknown",
        "p_yes": p_yes,
        "p_no": 1.0 - p_yes,
        "verdict_strength_pct": strength,
        "credence_yes_pct": int(round(p_yes * 100)),
    }
