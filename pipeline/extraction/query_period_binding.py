"""Generic temporal semantics for legal-output query period arguments."""

from __future__ import annotations

import re
from typing import Any

_FOLLOWING = re.compile(
    r"\b(?:following|after|subsequent\s+to|next)\b",
    re.IGNORECASE,
)
_YEAR_IN_TEXT = re.compile(r"\b((?:19|20)\d{2})\b")
_ENTITY_YEAR = re.compile(r"(?:19|20)\d{2}")
_ATOM = re.compile(r"^\s*(?:not|~|¬)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")

_EFFECT_YEAR_SIGNALS = (
    "apply from",
    "from financial year",
    "from the following",
    "from the next",
    "effect year",
    "consequences apply from",
    "starting from",
)
_SECOND_EXCEEDANCE_SIGNALS = (
    "second year",
    "second exceed",
    "second exceeding",
    "ending with",
    "end year",
    "during two consecutive",
    "two consecutive financial years",
    "consecutive years ending",
)
_ANCHOR_YEAR_SIGNALS = (
    "anchor year",
    "reference year",
    "during the financial year",
    "in the financial year",
)


def _norm(s: str) -> str:
    return str(s or "").strip().lower()


def _split_args(blob: str) -> list[str]:
    return [_norm(x.strip()) for x in (blob or "").split(",") if x.strip()]


def infer_query_period_role(sig: dict[str, Any] | None) -> str:
    """
    Classify what the FinancialYear argument of a legal-output predicate represents.

    Returns one of: effect_year | second_exceedance_year | anchor_year | unknown
    """
    if not isinstance(sig, dict):
        return "unknown"
    name = str(sig.get("name") or "").replace("_", " ")
    desc = str(sig.get("description") or "").replace("_", " ")
    text = (name + " " + desc).lower()

    if any(s in text for s in _SECOND_EXCEEDANCE_SIGNALS):
        return "second_exceedance_year"
    if any(s in text for s in _EFFECT_YEAR_SIGNALS):
        return "effect_year"
    if any(s in text for s in _ANCHOR_YEAR_SIGNALS):
        return "anchor_year"
    # Names like exceeds_*_in_year are anchor-like observation years
    if re.search(r"\b(?:during|in)\b.*\b(?:year|period|financial year)\b", text):
        return "anchor_year"
    if re.search(r"\b(?:from|apply)\b", text) and "financial year" in text:
        return "effect_year"
    return "unknown"


def _entity_year_hints(entities: dict[str, Any] | None) -> dict[str, str]:
    hints: dict[str, str] = {}
    if not isinstance(entities, dict):
        return hints
    for vals in entities.values():
        if not isinstance(vals, list):
            continue
        for ent in vals:
            if not isinstance(ent, str):
                continue
            m = _ENTITY_YEAR.search(ent)
            if m:
                hints[_norm(ent)] = m.group(0)
    return hints


def _next_financial_year_chains(case_facts: list[str]) -> list[tuple[str, str]]:
    chains: list[tuple[str, str]] = []
    for ln in case_facts or []:
        if not isinstance(ln, str):
            continue
        m = _ATOM.match(ln.strip())
        if not m or m.group(1) != "next_financial_year":
            continue
        args = _split_args(m.group(2))
        if len(args) == 2:
            chains.append((args[0], args[1]))
    return chains


def _period_arg_index(sig: dict[str, Any]) -> int | None:
    args = list(sig.get("args") or [])
    for i, typ in enumerate(args):
        if str(typ).strip().lower() in {"financialyear", "financial_year", "period", "year"}:
            return i
    if args:
        return len(args) - 1
    return None


def _following_anchor_year(user_question: str | None) -> str | None:
    if not user_question or not _FOLLOWING.search(user_question):
        return None
    years = _YEAR_IN_TEXT.findall(user_question)
    return years[-1] if years else None


def analyze_query_period_binding(
    *,
    query: dict[str, Any],
    case: dict[str, Any],
    kb_schema: dict[str, Any],
    user_question: str | None,
    predicate_sig: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyze whether query period args match question wording and predicate semantics."""
    sig = predicate_sig or {}
    pred = str(query.get("predicate") or sig.get("name") or "")
    args = [_norm(a) for a in (query.get("args") or [])]
    role = infer_query_period_role(sig)
    year_hints = _entity_year_hints((case or {}).get("entities"))
    chains = _next_financial_year_chains(list((case or {}).get("facts") or []))
    anchor_year = _following_anchor_year(user_question)

    period_idx = _period_arg_index(sig)
    selected_period = args[period_idx] if period_idx is not None and period_idx < len(args) else None
    selected_year = year_hints.get(selected_period or "", "") if selected_period else ""

    temporal_anchor_entity = None
    if anchor_year:
        for ent, yr in year_hints.items():
            if yr == anchor_year:
                temporal_anchor_entity = ent
                break

    successor_entities = {
        b for a, b in chains if temporal_anchor_entity and a == temporal_anchor_entity
    }
    predecessor_entities = {
        a for a, b in chains if temporal_anchor_entity and b == temporal_anchor_entity
    }

    warnings: list[str] = []
    matches_question = True

    if anchor_year and selected_period:
        if role == "effect_year":
            if selected_year == anchor_year:
                matches_question = False
                warnings.append(
                    "Question asks about the financial year following "
                    + anchor_year
                    + ", but the query period argument names the anchor year ("
                    + selected_period
                    + ")."
                )
            elif selected_period in predecessor_entities:
                matches_question = False
                warnings.append(
                    "Question asks about following "
                    + anchor_year
                    + ", but the query period is a predecessor financial year ("
                    + selected_period
                    + ")."
                )
            elif temporal_anchor_entity and successor_entities and selected_period not in successor_entities:
                if selected_period not in {temporal_anchor_entity}:
                    matches_question = False
                    warnings.append(
                        "Question asks about following "
                        + anchor_year
                        + ", but the query period is not the successor financial year in case facts."
                    )
        elif role == "second_exceedance_year":
            if selected_year and selected_year != anchor_year and _FOLLOWING.search(user_question or ""):
                warnings.append(
                    "Question mentions following "
                    + anchor_year
                    + "; predicate period role is second_exceedance_year/anchor — verify FY "
                    + str(selected_period)
                    + " is intended."
                )
        elif role == "unknown" and selected_year == anchor_year and _FOLLOWING.search(user_question or ""):
            warnings.append(
                "Ambiguous predicate period role with 'following "
                + anchor_year
                + "' wording; query uses anchor-year entity "
                + str(selected_period)
                + "."
            )
            matches_question = False

    return {
        "query_predicate": pred,
        "query_period_role": role,
        "temporal_anchor_entity": temporal_anchor_entity,
        "temporal_anchor_year": anchor_year,
        "selected_query_period": selected_period,
        "selected_query_period_year": selected_year or None,
        "successor_period_entities": sorted(successor_entities),
        "predecessor_period_entities": sorted(predecessor_entities),
        "matches_question_wording": matches_question,
        "query_argument_binding_warnings": warnings,
    }


def apply_query_period_binding(
    query_obj: dict[str, Any],
    case: dict[str, Any],
    kb_schema: dict[str, Any],
    user_question: str | None,
) -> dict[str, Any]:
    """
    Adjust query period args when effect_year + 'following Y' + unique successor entity exists.
    Returns diagnostics (also stored on query_obj as query_period_binding when non-empty).
    """
    pred = str(query_obj.get("predicate") or "")
    sig = None
    for p in (kb_schema or {}).get("predicates") or []:
        if isinstance(p, dict) and p.get("name") == pred:
            sig = p
            break
    diag = analyze_query_period_binding(
        query=query_obj,
        case=case,
        kb_schema=kb_schema,
        user_question=user_question,
        predicate_sig=sig,
    )

    role = diag.get("query_period_role")
    anchor_entity = diag.get("temporal_anchor_entity")
    successors = list(diag.get("successor_period_entities") or [])
    args = list(query_obj.get("args") or [])
    period_idx = _period_arg_index(sig or {}) if sig else None

    adjusted = False
    if (
        role == "effect_year"
        and anchor_entity
        and len(successors) == 1
        and period_idx is not None
        and period_idx < len(args)
        and _norm(args[period_idx]) != successors[0]
        and _following_anchor_year(user_question)
    ):
        args[period_idx] = successors[0]
        query_obj["args"] = args
        adjusted = True
        diag["selected_query_period"] = successors[0]
        diag["selected_query_period_year"] = _entity_year_hints(case.get("entities")).get(successors[0])
        diag["matches_question_wording"] = True
        diag["query_argument_binding_warnings"] = []
        diag["auto_adjusted_to_successor"] = True

    if adjusted:
        diag["query_argument_binding_warnings"] = []
    elif not diag.get("matches_question_wording") and diag.get("query_argument_binding_warnings"):
        diag["query_argument_binding_issue"] = True

    if diag.get("query_period_role") != "unknown" or diag.get("query_argument_binding_warnings"):
        query_obj["query_period_binding"] = diag
    return diag
