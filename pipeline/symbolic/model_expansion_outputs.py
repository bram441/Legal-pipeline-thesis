"""Extract possible legal outputs from model_expansion results."""

from __future__ import annotations

from typing import Any


def extract_possible_outputs(
    models: list[dict],
    *,
    focus_symbols: list[str] | None = None,
    legal_output_symbols: list[str] | None = None,
) -> list[dict[str, Any]]:
    focus = {str(s) for s in (focus_symbols or []) if s}
    legal = {str(s) for s in (legal_output_symbols or []) if s}
    allow = focus or legal
    seen: set[tuple[str, tuple[str, ...], int]] = set()
    outputs: list[dict[str, Any]] = []

    for idx, model in enumerate(models or []):
        if not isinstance(model, dict):
            continue
        for atom in model.get("true_atoms") or []:
            if not isinstance(atom, dict):
                continue
            pred = str(atom.get("predicate") or "").strip()
            if not pred:
                continue
            if allow and pred not in allow:
                continue
            args = tuple(str(a) for a in (atom.get("args") or []))
            key = (pred, args, idx + 1)
            if key in seen:
                continue
            seen.add(key)
            outputs.append(
                {
                    "symbol": pred,
                    "args": list(args),
                    "source_model": idx + 1,
                    "kind": "predicate",
                }
            )
        for fn in model.get("function_values") or []:
            if not isinstance(fn, dict):
                continue
            name = str(fn.get("function") or "").strip()
            if not name:
                continue
            if allow and name not in allow:
                continue
            args = tuple(str(a) for a in (fn.get("args") or []))
            key = (name, args, idx + 1)
            if key in seen:
                continue
            seen.add(key)
            outputs.append(
                {
                    "symbol": name,
                    "args": list(args),
                    "value": fn.get("value"),
                    "source_model": idx + 1,
                    "kind": "function",
                }
            )
    return outputs
