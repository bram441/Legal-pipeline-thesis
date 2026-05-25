"""Resolve case/query entity constants to KB environment types."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from pipeline.extraction.ir_utils import safe_entity as _safe_entity

_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_ATOM = re.compile(r"^\s*(?:not|~|¬)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_FUNC = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*=\s*.+\s*\.\s*$")


def _split_args(blob: str) -> list[str]:
    return [_safe_entity(x) for x in (blob or "").split(",") if _safe_entity(x)]


def _parse_fact_usages(facts: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ln in facts or []:
        if not isinstance(ln, str):
            continue
        s = ln.strip()
        mf = _FUNC.match(s)
        if mf:
            sym = mf.group(1)
            args = _split_args(mf.group(2))
            sig_key = "functions"
        else:
            m = _ATOM.match(s)
            if not m:
                continue
            sym = m.group(1)
            args = _split_args(m.group(2))
            sig_key = "predicates"
        env_sym = None
        for i, arg in enumerate(args):
            out.append(
                {
                    "entity": arg,
                    "symbol": sym,
                    "symbol_kind": sig_key,
                    "arg_index": i,
                    "source": "fact_argument",
                }
            )
    return out


def _declared_entity_types(case: dict[str, Any]) -> dict[str, str | None]:
    """entity_id -> declared type from case.entities keys (may be wrong type)."""
    declared: dict[str, str | None] = {}
    ents = (case or {}).get("entities") or {}
    if not isinstance(ents, dict):
        return declared
    for typ, vals in ents.items():
        if not isinstance(vals, list):
            continue
        for v in vals:
            eid = _safe_entity(v)
            if eid:
                declared[eid] = str(typ).strip() if typ else None
    return declared


def resolve_entity_type_mapping(
    case: dict[str, Any],
    query: dict[str, Any] | None,
    env: dict[str, Any],
) -> dict[str, Any]:
    """
    Build case_entity_type_mapping artifact.

    Infers types from fact/query argument positions using environment signatures.
    """
    env_types = set((env.get("types") or {}).keys())
    preds = env.get("predicates") or {}
    funs = env.get("functions") or {}

    evidence_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    declared = _declared_entity_types(case)

    for usage in _parse_fact_usages((case or {}).get("facts") or []):
        sym = usage["symbol"]
        idx = usage["arg_index"]
        ent = usage["entity"]
        if usage["symbol_kind"] == "predicates":
            sig = preds.get(sym) or {}
        else:
            sig = funs.get(sym) or {}
        arg_types = list(sig.get("args") or [])
        if idx < len(arg_types):
            evidence_by_entity[ent].append(
                {
                    "source": "fact_argument",
                    "symbol": sym,
                    "arg_index": idx,
                    "expected_type": arg_types[idx],
                }
            )

    query_args_info: list[dict[str, Any]] = []
    if isinstance(query, dict) and str(query.get("type") or "") == "predicate":
        q_pred = str(query.get("predicate") or "").strip()
        q_args = [_safe_entity(x) for x in (query.get("args") or [])]
        sig = preds.get(q_pred) or {}
        arg_types = list(sig.get("args") or [])
        for i, ent in enumerate(q_args):
            if not ent:
                continue
            expected = arg_types[i] if i < len(arg_types) else None
            if expected:
                evidence_by_entity[ent].append(
                    {
                        "source": "query_argument",
                        "symbol": q_pred,
                        "arg_index": i,
                        "expected_type": expected,
                    }
                )
            query_args_info.append(
                {
                    "entity": ent,
                    "arg_index": i,
                    "expected_type": expected,
                    "predicate": q_pred,
                }
            )

    all_entities: set[str] = set(declared.keys()) | set(evidence_by_entity.keys())
    entities_out: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    unmapped: list[str] = []

    for ent in sorted(all_entities):
        ev = evidence_by_entity.get(ent) or []
        inferred_types = {e["expected_type"] for e in ev if e.get("expected_type")}
        declared_type = declared.get(ent)
        resolved = None
        source = None
        if len(inferred_types) == 1:
            inferred = next(iter(inferred_types))
            if declared_type and declared_type in env_types and declared_type != inferred:
                conflicts.append(
                    {
                        "entity": ent,
                        "inferred_types": [inferred],
                        "declared_type": declared_type,
                        "evidence": ev,
                    }
                )
                inferred = None
            resolved = inferred
            srcs = {e["source"] for e in ev}
            source = ("+".join(sorted(srcs)) if srcs else "inferred") if resolved else None
        elif len(inferred_types) > 1:
            conflicts.append(
                {
                    "entity": ent,
                    "inferred_types": sorted(inferred_types),
                    "evidence": ev,
                }
            )
        elif declared_type and declared_type in env_types:
            resolved = declared_type
            source = "declared"
        elif declared_type and declared_type not in env_types:
            unmapped.append(ent)
        else:
            unmapped.append(ent)

        entities_out[ent] = {
            "declared_type": declared_type,
            "resolved_type": resolved,
            "source": source,
            "evidence": ev,
        }

    return {
        "entities": entities_out,
        "unmapped_entities": sorted(set(unmapped) - {e for e in entities_out if entities_out[e].get("resolved_type")}),
        "conflicts": conflicts,
        "query_arguments_with_inferred_types": query_args_info,
    }


def apply_resolved_entities_to_case(case: dict[str, Any], mapping: dict[str, Any]) -> dict[str, str]:
    """Rewrite case.entities from resolved types. Returns type->entities map for FO seeding."""
    typed: dict[str, list[str]] = defaultdict(list)
    for ent, info in (mapping.get("entities") or {}).items():
        rt = info.get("resolved_type")
        if rt and ent:
            typed[str(rt)].append(str(ent))
    case["entities"] = {k: sorted(set(v)) for k, v in typed.items() if v}
    return {k: list(v) for k, v in typed.items()}
