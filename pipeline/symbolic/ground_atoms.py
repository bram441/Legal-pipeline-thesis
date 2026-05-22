"""Generic grounded atom candidates from KB schema and case entities."""

from __future__ import annotations

import itertools
import re
from typing import Any

_PLACEHOLDERS = frozenset({"?", "_", "*", "any", ""})
_MAX_CANDIDATES = 200


def _safe_entity(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip().lower()
    return s if s and s not in _PLACEHOLDERS else ""


def entities_for_type(case: dict | None, typ: str) -> list[str]:
    ents = ((case or {}).get("entities") or {})
    vals = ents.get(typ) or ents.get(str(typ)) or []
    out: list[str] = []
    if isinstance(vals, list):
        for v in vals:
            s = _safe_entity(v)
            if s:
                out.append(s)
    if str(typ) == "Person":
        for ln in (case or {}).get("facts") or []:
            m = re.match(r"^\s*IsDeceased\(([^)]+)\)\.\s*$", str(ln))
            if m:
                s = _safe_entity(m.group(1))
                if s and s not in out:
                    out.append(s)
    return sorted(set(out))


def derived_symbols(kb_schema: dict | None, *, include_functions: bool = True) -> list[str]:
    if not kb_schema:
        return []
    out: list[str] = []
    for p in kb_schema.get("predicates") or []:
        if not isinstance(p, dict):
            continue
        kind = str(p.get("kind") or "").lower()
        if kind in {"derived", "conclusion"}:
            name = str(p.get("name") or "").strip()
            if name:
                out.append(name)
    if include_functions:
        for f in kb_schema.get("functions") or []:
            if not isinstance(f, dict):
                continue
            kind = str(f.get("kind") or "").lower()
            if kind in {"derived", "conclusion", "observable", "input", "helper"}:
                name = str(f.get("name") or "").strip()
                if name:
                    out.append(name)
    return sorted(set(out))


def predicate_sig(kb_schema: dict | None, name: str) -> dict | None:
    if not kb_schema or not name:
        return None
    target = name.strip().lower().replace("_", "")
    for p in kb_schema.get("predicates") or []:
        if not isinstance(p, dict):
            continue
        n = str(p.get("name") or "")
        if n == name or n.lower().replace("_", "") == target:
            return p
    return None


def function_sig(kb_schema: dict | None, name: str) -> dict | None:
    if not kb_schema or not name:
        return None
    target = name.strip().lower().replace("_", "")
    for f in kb_schema.get("functions") or []:
        if not isinstance(f, dict):
            continue
        n = str(f.get("name") or "")
        if n == name or n.lower().replace("_", "") == target:
            return f
    return None


def grounded_predicate_candidates(
    kb_schema: dict | None,
    case: dict | None,
    predicate: str,
    *,
    focus_entities: list[str] | None = None,
    max_candidates: int = _MAX_CANDIDATES,
) -> tuple[list[list[str]], str | None]:
    """Return list of arg-lists for grounding predicate, optional warning if truncated."""
    sig = predicate_sig(kb_schema, predicate)
    if not sig:
        return [], "Unknown predicate: " + predicate
    arg_types = [str(t) for t in (sig.get("args") or [])]
    pools: list[list[str]] = []
    for typ in arg_types:
        pool = entities_for_type(case, typ)
        if focus_entities and len(arg_types) == 1:
            pool = [e for e in pool if e in {_safe_entity(x) for x in focus_entities}] or pool
        if not pool:
            return [], f"No case entities for argument type {typ}"
        pools.append(pool)
    combos = list(itertools.product(*pools))
    warning = None
    if len(combos) > max_candidates:
        combos = combos[:max_candidates]
        warning = f"Candidate space truncated to {max_candidates} atoms for {predicate}"
    return [list(c) for c in combos], warning


def filter_symbols_by_question(symbols: list[str], kb_schema: dict | None, question: str) -> list[str]:
    if not question or not symbols:
        return symbols
    q = re.sub(r"[^a-z0-9]+", " ", (question or "").lower())
    q_tokens = {t for t in q.split() if len(t) > 2}
    if not q_tokens:
        return symbols
    scored: list[tuple[float, str]] = []
    for sym in symbols:
        sig = predicate_sig(kb_schema, sym) or function_sig(kb_schema, sym) or {}
        name_toks = set(re.sub(r"[^a-z0-9]+", " ", sym.lower()).split())
        desc_toks = set(re.sub(r"[^a-z0-9]+", " ", str(sig.get("description") or "").lower()).split())
        overlap = len(q_tokens & (name_toks | desc_toks))
        if overlap:
            scored.append((float(overlap), sym))
    if not scored:
        return symbols
    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored]
