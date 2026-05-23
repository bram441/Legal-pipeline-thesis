"""
Law-agnostic detection of legal-effect/timing language and legal-output predicates.

Used by KB schema validation (law_text_for_lints) and query-target selection.
"""

from __future__ import annotations

import re
from typing import Any

# Strong multi-word cues in scoped law text — classification-only provisions should not match.
_STRONG_LAW_EFFECT_PATTERNS: tuple[str, ...] = (
    r"\bconsequences?\s+(?:apply|must|shall|take|are)\b",
    r"\bconsequences?\s+apply\s+from\b",
    r"\blegal\s+effect\b",
    r"\btake(?:s)?\s+effect\b",
    r"\benter(?:s)?\s+into\s+force\b",
    r"\b(?:apply|applies|applied)\s+from\s+the\b",
    r"\bfrom\s+the\s+(?:following|next)\b",
    r"\b(?:starting|starts?)\s+from\b",
    r"\bceases?\s+to\s+apply\b",
    r"\bno\s+longer\s+applies?\b",
    r"\bmust\s+be\s+taken\s+into\s+account\b",
    r"\bshall\s+be\s+taken\s+into\s+account\b",
    r"\bdient\s+in\s+aanmerking\s+te\s+worden\s+genomen\b",
    r"\bmoet\s+in\s+aanmerking\s+worden\s+genomen\b",
    r"\btaken\s+into\s+account\s+immediately\b",
    r"\bimmediately\b.+\btaken\s+into\s+account\b",
    r"\bis\s+entitled\s+to\b",
    r"\bhas\s+the\s+right\s+to\b",
    r"\bobligation\s+applies\b",
    r"\bexception\s+applies\b",
    r"\bderogation\s+applies\b",
    r"\bprohibition\s+applies\b",
    r"\bpermission\s+exists\b",
    r"\bgevolgen?\s+(?:zijn\s+)?van\s+toepassing\b",
    r"\bgevolgen?\s+vanaf\b",
    r"\bgevolgen?\b.+\bvanaf\b",
    r"\bgevolgen?\s+.*\bin\s+werking\b",
    r"\bgaan\b.+\bgevolgen\b",
    r"\brechtsgevolg\b",
    r"\btreedt\s+in\s+werking\b",
    r"\bwordt\s+van\s+kracht\b",
    r"\bvan\s+toepassing\s+vanaf\b",
    r"\bvanaf\s+het\s+(?:volgende|daaropvolgende)\b",
    r"\bhoudt\s+op\s+van\s+toepassing\b",
    r"\bniet\s+langer\s+van\s+toepassing\b",
    r"\bheeft\s+recht\s+op\b",
    r"\bis\s+gerechtigd\b",
    r"\buitzondering\s+is\s+van\s+toepassing\b",
    r"\bafwijking\s+is\s+van\s+toepassing\b",
)

_STRONG_LAW_EFFECT_RE = re.compile(
    "|".join(f"(?:{p})" for p in _STRONG_LAW_EFFECT_PATTERNS),
    re.IGNORECASE | re.DOTALL,
)

_QUESTION_EFFECT_PATTERNS: tuple[str, ...] = (
    r"\bconsequences?\s+apply\b",
    r"\bconsequences?\s+according\b",
    r"\bapplies?\s+from\b",
    r"\bapply\s+from\b",
    r"\beffect\s+takes?\s+place\b",
    r"\bmust\s+be\s+taken\s+into\s+account\b",
    r"\btaken\s+into\s+account\b",
    r"\bright\s+arises\b",
    r"\bobligation\s+applies\b",
    r"\bvan\s+toepassing\s+vanaf\b",
    r"\bgevolgen\s+vanaf\b",
    r"\bgevolgen\b.+\bvanaf\b",
    r"\bgaan\b.+\bgevolgen\b",
    r"\bgevolgen\s+.*\bvan\s+toepassing\b",
    r"\bgevolgen\s+.*\bin\s+vanaf\b",
    r"\bmoet\s+in\s+aanmerking\s+worden\s+genomen\b",
    r"\bdient\s+in\s+aanmerking\s+worden\s+genomen\b",
)

_QUESTION_EFFECT_RE = re.compile(
    "|".join(f"(?:{p})" for p in _QUESTION_EFFECT_PATTERNS),
    re.IGNORECASE | re.DOTALL,
)

_LEGAL_EFFECT_OUTPUT_CATEGORIES: frozenset[str] = frozenset(
    {
        "legal_effect",
        "effect",
        "timing",
        "consequence",
        "applicability",
        "obligation",
        "right",
        "permission",
        "prohibition",
        "exception",
        "entitlement",
    }
)

_CLASSIFICATION_OUTPUT_CATEGORIES: frozenset[str] = frozenset(
    {"classification", "status", "definition", "category"}
)

_EFFECT_OUTPUT_TOKENS: tuple[str, ...] = (
    "consequence",
    "consequences",
    "effect",
    "applies",
    "apply",
    "applicable",
    "applicability",
    "timing",
    "period",
    "following",
    "commence",
    "cease",
    "entitled",
    "entitlement",
    "obligation",
    "right",
    "permission",
    "prohibited",
    "prohibition",
    "exception",
    "immediately",
    "account",
    "gevolgen",
    "toepassing",
    "werking",
    "vanaf",
    "aanmerking",
    "gerechtigd",
    "recht",
    "van kracht",
    "in werking",
)

_CLASSIFICATION_NAME_PREFIXES: tuple[str, ...] = ("is_", "has_")

_INTERMEDIATE_NAME_MARKERS: tuple[str, ...] = (
    "exceeds",
    "exceed",
    "threshold",
    "criterion",
    "criteria",
    "meets_",
    "satisfies",
    "qualifies_as",
    "amount_",
    "count_",
    "within_",
    "below_",
    "above_",
)

_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _blob(name: str, description: str = "") -> str:
    return ((name or "") + " " + (description or "")).strip().lower()


def _tokens(name: str, description: str = "") -> set[str]:
    parts = _TOKEN_SPLIT_RE.split(_blob(name, description))
    return {p for p in parts if len(p) >= 3}


def law_text_has_strong_legal_effect_language(law_text: str | None) -> bool:
    t = (law_text or "").strip()
    if not t:
        return False
    return bool(_STRONG_LAW_EFFECT_RE.search(t))


def question_has_legal_effect_language(question: str | None) -> bool:
    t = (question or "").strip()
    if not t:
        return False
    return bool(_QUESTION_EFFECT_RE.search(t))


def _has_effect_output_tokens(name: str, description: str = "") -> bool:
    blob = _blob(name, description)
    toks = _tokens(name, description)
    if any(tok in blob for tok in _EFFECT_OUTPUT_TOKENS):
        return True
    effect_toks = {
        "consequence",
        "consequences",
        "effect",
        "applies",
        "apply",
        "applicable",
        "timing",
        "following",
        "commence",
        "cease",
        "entitled",
        "entitlement",
        "obligation",
        "permission",
        "prohibition",
        "exception",
        "immediately",
        "gevolgen",
        "toepassing",
        "werking",
        "vanaf",
        "aanmerking",
        "gerechtigd",
        "recht",
    }
    return bool(toks & effect_toks)


def _has_intermediate_markers(name: str, description: str = "") -> bool:
    n = (name or "").lower()
    if any(m in n for m in _INTERMEDIATE_NAME_MARKERS):
        return True
    blob = _blob(name, description)
    return any(m.rstrip("_") in blob for m in _INTERMEDIATE_NAME_MARKERS)


def predicate_represents_legal_effect_output(
    name: str,
    *,
    description: str = "",
    kind: str = "",
    legal_output: bool | None = None,
    output_category: str = "",
) -> bool:
    """True when a derived predicate represents a legal effect/consequence/timing output."""
    if legal_output is True:
        return True
    if legal_output is False:
        return False
    cat = (output_category or "").strip().lower()
    if cat in _LEGAL_EFFECT_OUTPUT_CATEGORIES:
        return True
    if cat in _CLASSIFICATION_OUTPUT_CATEGORIES:
        return False
    k = (kind or "").strip().lower()
    if k not in {"derived", "conclusion"}:
        return False
    if not _has_effect_output_tokens(name, description):
        return False
    if predicate_looks_like_classification_output(
        name, description=description, kind=kind, output_category=cat
    ):
        return False
    return True


def predicate_looks_like_classification_output(
    name: str,
    *,
    description: str = "",
    kind: str = "",
    legal_output: bool | None = None,
    output_category: str = "",
) -> bool:
    if legal_output is True:
        return False
    if legal_output is False:
        return True
    cat = (output_category or "").strip().lower()
    if cat in _CLASSIFICATION_OUTPUT_CATEGORIES:
        return True
    if cat in _LEGAL_EFFECT_OUTPUT_CATEGORIES:
        return False
    n = (name or "").lower()
    if not n.startswith(_CLASSIFICATION_NAME_PREFIXES):
        return False
    if _has_effect_output_tokens(name, description) and not _has_intermediate_markers(name, description):
        # is_consequence_applies style names start with is_ but express effects.
        if any(
            t in _blob(name, description)
            for t in (
                "consequence",
                "consequences",
                "effect",
                "applies_from",
                "apply_from",
                "takes_effect",
                "entitled",
                "obligation",
                "permission",
                "prohibition",
                "gevolgen",
                "toepassing",
                "aanmerking",
            )
        ):
            return False
    return True


def predicate_looks_like_intermediate_output(
    name: str,
    *,
    description: str = "",
    kind: str = "",
) -> bool:
    k = (kind or "").strip().lower()
    if k == "helper":
        return True
    if k in {"derived", "conclusion"} and _has_intermediate_markers(name, description):
        if not predicate_represents_legal_effect_output(
            name, description=description, kind=kind
        ):
            return True
    return False


def schema_has_legal_effect_output_predicate(predicates: list) -> bool:
    for p in predicates:
        kind = getattr(p, "kind", None) or (p.get("kind") if isinstance(p, dict) else "")
        if str(kind).lower() not in {"derived", "conclusion"}:
            continue
        name = getattr(p, "name", None) or (p.get("name") if isinstance(p, dict) else "")
        desc = getattr(p, "description", None) or (
            p.get("description") if isinstance(p, dict) else ""
        )
        lo = getattr(p, "legal_output", None)
        if lo is None and isinstance(p, dict):
            lo = p.get("legal_output")
        cat = getattr(p, "output_category", None) or (
            p.get("output_category") if isinstance(p, dict) else ""
        )
        if predicate_represents_legal_effect_output(
            str(name),
            description=str(desc or ""),
            kind=str(kind),
            legal_output=lo if isinstance(lo, bool) else None,
            output_category=str(cat or ""),
        ):
            return True
    return False


def schema_only_classification_or_intermediate_derived(predicates: list) -> bool:
    derived = []
    for p in predicates:
        kind = str(
            getattr(p, "kind", None) or (p.get("kind") if isinstance(p, dict) else "")
        ).lower()
        if kind not in {"derived", "conclusion"}:
            continue
        derived.append(p)
    if not derived:
        return False
    for p in derived:
        name = str(getattr(p, "name", None) or (p.get("name") if isinstance(p, dict) else ""))
        desc = str(
            getattr(p, "description", None)
            or (p.get("description") if isinstance(p, dict) else "")
        )
        kind = str(
            getattr(p, "kind", None) or (p.get("kind") if isinstance(p, dict) else "")
        )
        lo = getattr(p, "legal_output", None)
        if lo is None and isinstance(p, dict):
            lo = p.get("legal_output")
        cat = str(
            getattr(p, "output_category", None)
            or (p.get("output_category") if isinstance(p, dict) else "")
        )
        if predicate_represents_legal_effect_output(
            name,
            description=desc,
            kind=kind,
            legal_output=lo if isinstance(lo, bool) else None,
            output_category=cat,
        ):
            return False
    return True


def should_require_legal_effect_output(
    law_text_for_lints: str | None,
    *,
    scope_metadata: dict | None = None,
) -> bool:
    """
    True when validators should require a legal-effect output predicate.
    Prefer scoped text without effect language; scope metadata is a secondary guard.
    """
    if scope_metadata is not None:
        q_asks = scope_metadata.get("question_asks_legal_effect")
        has_effect = scope_metadata.get("contains_effect_language")
        if q_asks is False and has_effect is False:
            return False
        if has_effect is True:
            return True
        if q_asks is True:
            return True
    return law_text_has_strong_legal_effect_language(law_text_for_lints)


def validate_legal_effect_output_presence(
    predicates: list,
    *,
    law_text_for_lints: str | None,
    scope_metadata: dict | None = None,
) -> None:
    """
    When scoped law text has strong legal-effect language, require a derived legal-output
    predicate (not only classifications/intermediate helpers).
    """
    if not should_require_legal_effect_output(
        law_text_for_lints, scope_metadata=scope_metadata
    ):
        return
    if schema_has_legal_effect_output_predicate(predicates):
        return
    if not schema_only_classification_or_intermediate_derived(predicates):
        return

    from pipeline.kb.json_ir import JSONIRCompilationError, SCHEMA_DESIGN_TAG

    snippet = (law_text_for_lints or "").strip()
    if len(snippet) > 120:
        snippet = snippet[:117] + "..."
    raise JSONIRCompilationError(
        SCHEMA_DESIGN_TAG
        + ": The scoped law text contains legal-effect or timing language"
        + (f' ("{snippet}")' if snippet else "")
        + ", but the JSON IR has no derived legal-output predicate representing that effect. "
        "Do not model the provision only as classification or threshold predicates. "
        "Add a derived predicate for the legal consequence, effect, applicability, timing, "
        "obligation, right, permission, prohibition, or exception, with rules defining it. "
        "Repair layer: symbols."
    )


def symbol_dict_for_query(sym: dict) -> dict:
    """Normalize symbol metadata for query validation."""
    return {
        "name": sym.get("name"),
        "description": sym.get("description") or "",
        "kind": sym.get("kind") or "",
        "legal_output": sym.get("legal_output"),
        "output_category": sym.get("output_category") or "",
    }
