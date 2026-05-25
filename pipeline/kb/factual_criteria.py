"""
Pragmatic factual-criteria mode: externally checkable legal/factual conditions as case inputs.

Similar in spirit to structure-driven domain filling (e.g. VERUS-LM): criteria that the case
may state explicitly are not forced through helper/derived rule graphs during evaluation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pipeline.kb.composite_predicate_heuristics import (
    looks_directly_observable_factual,
    looks_legal_conclusion_computed,
    looks_threshold_counting_composite,
)
from pipeline.kb.legal_effect import (
    predicate_looks_like_classification_output,
    predicate_represents_legal_effect_output,
)

_BLOCKED_OUTPUT_CATEGORIES = frozenset(
    {
        "legal_effect",
        "consequence",
        "applicability",
        "classification",
        "sanction",
        "punishment",
        "entitlement",
        "permission",
        "prohibition",
    }
)

_FACTUAL_CRITERIA_SIGNAL_RE = re.compile(
    r"(?i)(?:"
    r"\bcriteri(?:on|a)\b|"
    r"\bconditions?\b|"
    r"meets?_.*conditions?|"
    r"satisfies?_.*conditions?|"
    r"fulfilled?_.*conditions?|"
    r"possess(?:es|ed)?_valid_|"
    r"has_valid_(?:passport|travel_document|document)|"
    r"valid_(?:passport|travel_document|document)|"
    r"travel_document|"
    r"failed_to_|"
    r"stated_|"
    r"declared_|"
    r"concealed_|"
    r"used_false_|"
    r"departure_within_|"
    r"failed_to_comply|"
    r"unwillingness_to_comply|"
    r"complied_with|"
    r"did_not_comply"
    r")"
)

# Numeric threshold/counting helpers — use case_given bridge, not pragmatic observable allowlist.
_THRESHOLD_COUNTING_ONLY_RE = re.compile(
    r"(?i)(?:"
    r"^exceeds?_|"
    r"_exceeds?_|"
    r"more_than_(?:one|two|three).*(?:criter|threshold)|"
    r"at_least_(?:two|three|four).*(?:criter|threshold)|"
    r"two_consecutive|"
    r"consecutive_years|"
    r"no_more_than_.*criter|"
    r"pairwise_exceeded|"
    r"threshold_exceeded"
    r")"
)


def pragmatic_factual_criteria_mode_enabled() -> bool:
    from pipeline.config import config_section

    return bool(config_section("evaluation").get("pragmatic_factual_criteria_mode"))


def _sig_dict(sig: dict[str, Any] | Any) -> dict[str, Any]:
    if isinstance(sig, dict):
        return sig
    if hasattr(sig, "__dataclass_fields__"):
        return {
            "name": getattr(sig, "name", ""),
            "description": getattr(sig, "description", ""),
            "kind": getattr(sig, "kind", ""),
            "legal_output": getattr(sig, "legal_output", None),
            "output_category": getattr(sig, "output_category", ""),
            "directly_observable": getattr(sig, "directly_observable", False),
            "case_input": getattr(sig, "case_input", False),
            "factual_criteria_input": getattr(sig, "factual_criteria_input", False),
        }
    return {}


def is_threshold_counting_helper_only(name: str, description: str = "") -> bool:
    """True when predicate should stay on case_given threshold path, not pragmatic allowlist."""
    blob = (name or "") + " " + (description or "")
    if _THRESHOLD_COUNTING_ONLY_RE.search(name or ""):
        return True
    if looks_threshold_counting_composite(name, description) and not _FACTUAL_CRITERIA_SIGNAL_RE.search(
        blob
    ):
        return True
    return False


def is_factual_criteria_input_candidate(
    sig: dict[str, Any] | Any,
    *,
    query_predicate: str | None = None,
    kb_schema: dict | None = None,
) -> bool:
    """
    True when a predicate may be treated as an externally checkable factual criterion (not a
    legal conclusion and not a pure threshold-counting helper).
    """
    s = _sig_dict(sig)
    name = str(s.get("name") or "").strip()
    if not name:
        return False

    if query_predicate and name == str(query_predicate).strip():
        return False

    if s.get("legal_output") is True:
        return False

    cat = str(s.get("output_category") or "").strip().lower()
    if cat in _BLOCKED_OUTPUT_CATEGORIES:
        return False

    lo = s.get("legal_output") if isinstance(s.get("legal_output"), bool) else None
    kind = str(s.get("kind") or "").strip().lower()
    desc = str(s.get("description") or "")

    if predicate_represents_legal_effect_output(
        name,
        description=desc,
        kind=kind,
        legal_output=lo,
        output_category=cat,
    ):
        return False

    if looks_legal_conclusion_computed(name, desc):
        return False

    if is_threshold_counting_helper_only(name, desc):
        return False

    if looks_directly_observable_factual(name, desc):
        return True

    if predicate_looks_like_classification_output(
        name,
        description=desc,
        kind=kind,
        legal_output=lo,
        output_category=cat,
    ):
        return False

    if _FACTUAL_CRITERIA_SIGNAL_RE.search(name) or _FACTUAL_CRITERIA_SIGNAL_RE.search(desc):
        return True

    if re.search(r"(?i)meets?_.*conditions?", name):
        return True

    return False


def symbol_marked_factual_criteria_input(sig: dict[str, Any] | Any) -> bool:
    s = _sig_dict(sig)
    if s.get("factual_criteria_input") is True:
        return True
    meta = s.get("metadata")
    return isinstance(meta, dict) and meta.get("factual_criteria_input") is True


def decl_exempt_from_computed_observable_checks(decl: Any) -> bool:
    """Skip computed_observable_unsafe / floating-helper errors in pragmatic mode."""
    if not pragmatic_factual_criteria_mode_enabled():
        return False
    if symbol_marked_factual_criteria_input(decl):
        return True
    return is_factual_criteria_input_candidate(decl)


def apply_pragmatic_factual_criteria_to_ir(
    ir: dict,
    *,
    query_predicate: str | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Reclassify factual-criteria predicates in-place before JSON IR validation.
    """
    diag = diagnostics if diagnostics is not None else new_factual_criteria_diagnostics()
    diag["mode_enabled"] = pragmatic_factual_criteria_mode_enabled()
    if not diag["mode_enabled"]:
        return diag

    reclassified: list[str] = []
    rejected_legal: list[str] = []
    for p in ir.get("predicates") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        name = str(p["name"])
        if predicate_represents_legal_effect_output(
            name,
            description=str(p.get("description") or ""),
            kind=str(p.get("kind") or ""),
            legal_output=p.get("legal_output") if isinstance(p.get("legal_output"), bool) else None,
            output_category=str(p.get("output_category") or ""),
        ):
            rejected_legal.append(name)
            continue
        if not is_factual_criteria_input_candidate(
            p, query_predicate=query_predicate, kb_schema=ir
        ):
            continue
        prev_kind = p.get("kind")
        p["kind"] = "observable"
        p["directly_observable"] = True
        p["case_input"] = True
        p["factual_criteria_input"] = True
        if prev_kind != "observable":
            reclassified.append(name)
    diag["predicates_reclassified_as_factual_criteria"] = sorted(set(reclassified))
    diag["rejected_legal_conclusion_candidates"] = sorted(set(rejected_legal))
    return diag


def case_text_supports_factual_criteria(
    case_text: str | None,
    pred: str,
    sig: dict[str, Any],
    *,
    evidence_text: str | None = None,
) -> tuple[bool, str]:
    """Evidence must be explicit substring of case text; no invented numerics."""
    from pipeline.kb.factual_case_input import _case_text_supports_predicate

    if not is_factual_criteria_input_candidate(sig):
        return False, ""
    return _case_text_supports_predicate(case_text, pred, sig, evidence_text=evidence_text)


def patch_predicate_entry_for_factual_criteria(pred: dict[str, Any]) -> bool:
    """Mark a symbol-table predicate dict as externally checkable case input."""
    if not isinstance(pred, dict) or not pred.get("name"):
        return False
    if not is_factual_criteria_input_candidate(pred):
        return False
    pred["kind"] = "observable"
    pred["directly_observable"] = True
    pred["case_input"] = True
    pred["factual_criteria_input"] = True
    return True


def try_apply_pragmatic_factual_criteria_symbol_fixup(
    symbol_table: dict[str, Any] | None,
    helper_name: str,
    *,
    scope_metadata: dict[str, Any] | None = None,
) -> bool:
    """
    When missing_helper_definition targets a factual criterion, reclassify the symbol
    without forcing a THEN-defining rule (pragmatic evaluation mode only).
    """
    if not pragmatic_factual_criteria_mode_enabled():
        return False
    if not symbol_table or not helper_name:
        return False
    patched = False
    for pred in symbol_table.get("predicates") or []:
        if not isinstance(pred, dict) or str(pred.get("name") or "") != helper_name:
            continue
        if patch_predicate_entry_for_factual_criteria(pred):
            patched = True
    if not patched:
        return False
    diag = (scope_metadata or {}).get("factual_criteria_diagnostics")
    if isinstance(diag, dict):
        treated = list(diag.get("missing_helpers_treated_as_case_input") or [])
        if helper_name not in treated:
            treated.append(helper_name)
        diag["missing_helpers_treated_as_case_input"] = treated
        reclassified = list(diag.get("predicates_reclassified_as_factual_criteria") or [])
        if helper_name not in reclassified:
            reclassified.append(helper_name)
        diag["predicates_reclassified_as_factual_criteria"] = sorted(set(reclassified))
    return True


def missing_helper_factual_criteria_repair_hint(helper_name: str) -> str:
    return (
        "Pragmatic factual-criteria mode: helper '%s' appears to be an externally checkable "
        "factual criterion. Mark it kind=observable with directly_observable=true, "
        "case_input=true, and factual_criteria_input=true rather than deriving it in THEN."
        % helper_name
    )


def new_factual_criteria_diagnostics() -> dict[str, Any]:
    return {
        "mode_enabled": pragmatic_factual_criteria_mode_enabled(),
        "predicates_reclassified_as_factual_criteria": [],
        "missing_helpers_treated_as_case_input": [],
        "case_asserted_factual_criteria": [],
        "rejected_legal_conclusion_candidates": [],
        "evidence_text_validation_results": [],
    }


def write_factual_criteria_mode_diagnostics(path: str | Path, payload: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def collect_case_asserted_factual_criteria(
    case: dict[str, Any] | None,
    kb_schema: dict | None,
    *,
    case_text: str | None = None,
    query_predicate: str | None = None,
) -> dict[str, Any]:
    """Summarize factual criteria asserted in case IR for diagnostics."""
    out: dict[str, Any] = {
        "asserted": [],
        "rejected": [],
    }
    if not isinstance(case, dict):
        return out

    import re

    atom_re = re.compile(r"^\s*(?:not|~|¬)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(")
    preds_by_name = {
        str(p.get("name")): p
        for p in (kb_schema or {}).get("predicates") or []
        if isinstance(p, dict) and p.get("name")
    }

    for ln in case.get("facts") or []:
        if not isinstance(ln, str):
            continue
        m = atom_re.match(ln.strip())
        if not m:
            continue
        pname = m.group(1)
        sig = preds_by_name.get(pname) or {"name": pname, "kind": "observable"}
        ok, snippet = case_text_supports_factual_criteria(
            case_text, pname, sig, evidence_text=None
        )
        entry = {"predicate": pname, "fact": ln.strip(), "supported": ok, "evidence_snippet": snippet}
        if symbol_marked_factual_criteria_input(sig) or is_factual_criteria_input_candidate(
            sig, query_predicate=query_predicate, kb_schema=kb_schema
        ):
            if ok or not pragmatic_factual_criteria_mode_enabled():
                out["asserted"].append(entry)
            else:
                out["rejected"].append({**entry, "reason": "unsupported_by_case_text"})
        elif pragmatic_factual_criteria_mode_enabled():
            out["rejected"].append({**entry, "reason": "not_factual_criteria_candidate"})
    return out
