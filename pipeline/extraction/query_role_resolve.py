"""
Deterministic query arg repair using case facts (not more LLM prompt text).

When the user question refers to a *role* (surviving spouse, deceased, …) without naming
a person, extraction can still bind the wrong Person constant. If the case facts already
ground roles (e.g. survivingSpouse(anna), deceased(bert)), we can fix unary boolean queries
before symbolic reasoning.
"""
import re
from typing import Dict, List, Optional, Set, Tuple

# Mirror extractor._QUESTION_STOPWORDS + patterns so explicit "Does Anna ..." still wins.
_Q_STOP = frozenset({
    "the", "what", "who", "which", "how", "why", "when", "where", "does", "did",
    "is", "are", "was", "were", "can", "could", "article", "art", "belgian",
    "law", "case", "facts", "sentence", "minimum", "maximum", "prison", "fine",
})


def _explicit_name_in_question(question: Optional[str]) -> Optional[str]:
    """If the question names a person (English or Dutch legal-question starters), return that name; else None."""
    if not question or not isinstance(question, str):
        return None
    q = question.strip()
    patterns = [
        r"\b(?:Is|Are|Does|Did|Was|Were)\s+([A-Z][a-zA-Z]+)\b",
        r"\b(?:for|about)\s+([A-Z][a-zA-Z]+)\b",
        r"\b([A-Z][a-zA-Z]+)\s+(?:liable|punishable|eligible|qualifies)\b",
        # Dutch: common matrix question openers before a proper name (inheritance / civil).
        r"^\s*(?:Heeft|Verkrijgt|Krijgt|Krijgen|Is|Zijn|Was|Ware|Kan|Kunnen|Moet|Moeten|Had|Hadden|Wordt|Worden|Valt|Vallen|Zal|Zullen)\s+([A-Z][a-zA-Z]+)\b",
    ]
    for pat in patterns:
        m = re.search(pat, q)
        if m:
            name = m.group(1).strip().lower()
            if name and name not in _Q_STOP and len(name) >= 2:
                return name
    return None

# Positive unary fact: Predicate(const).
_UNARY_POS = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*\.\s*$")
_NEG = re.compile(r"^\s*(?:not|~|¬)\s")


def _norm_pred(p: str) -> str:
    return (p or "").replace("_", "").lower()


def _iter_unary_positives(case) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    facts = (case or {}).get("facts") or []
    if not isinstance(facts, list):
        return out
    for ln in facts:
        if not isinstance(ln, str):
            continue
        s = ln.strip()
        if "=" in s or _NEG.search(s):
            continue
        m = _UNARY_POS.match(s)
        if m:
            out.append((m.group(1), m.group(2).strip().lower()))
    return out


def _survivor_constants(pairs: List[Tuple[str, str]]) -> Set[str]:
    out: Set[str] = set()
    for pred, arg in pairs:
        pn = _norm_pred(pred)
        if pn in ("survivingspouse", "survivinglegalcohabitant", "survivingcohabitingpartner"):
            out.add(arg)
        elif "survivingspouse" in pn or (pn.startswith("surviving") and "spouse" in pn):
            out.add(arg)
    return out


def _deceased_constants(pairs: List[Tuple[str, str]]) -> Set[str]:
    """People grounded as the deceased / estate subject in unary facts."""
    out: Set[str] = set()
    for pred, arg in pairs:
        pn = _norm_pred(pred)
        if pn == "deceased" or pn == "isdeceased":
            out.add(arg)
        elif pn.startswith("deceasedleaves"):
            out.add(arg)
        elif pn.startswith("survivedby"):
            out.add(arg)
    return out


def question_role_intent(question: Optional[str]) -> Optional[str]:
    """
    Rough intent when the question uses role wording instead of a proper name.
    Returns 'surviving_spouse' | 'deceased' | None.
    """
    if not question or not isinstance(question, str):
        return None
    t = question.lower()
    # Dutch
    if ("langstlevende" in t or "overlevende" in t) and ("echtgenoot" in t or "partner" in t):
        return "surviving_spouse"
    if "overledene" in t or "eerststervende" in t:
        return "deceased"
    # English
    if "surviving spouse" in t or "longest-living spouse" in t:
        return "surviving_spouse"
    if re.search(r"\bthe deceased\b", t):
        return "deceased"
    return None


def apply_role_arg_consistency(
    user_question: Optional[str],
    query_obj: Dict,
    case,
    kb_schema: Optional[Dict] = None,
) -> bool:
    """
    Domain-specific heuristic (succession/spouse/deceased role repair). Disabled by default.
    Set LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS=1 to enable for legacy experiments.

    Returns True if query_obj was modified.
    """
    from pipeline.semantic.legal_question import domain_heuristics_enabled

    if not domain_heuristics_enabled():
        return False

    if _explicit_name_in_question(user_question):
        return False

    intent = question_role_intent(user_question)
    if not intent:
        return False

    q_type = str(query_obj.get("type") or "").strip().lower()
    if q_type != "predicate":
        return False
    mode = str(query_obj.get("mode") or "set").strip().lower()
    if mode != "boolean":
        return False

    args = query_obj.get("args") or []
    if not isinstance(args, list) or len(args) < 1:
        return False
    cur = str(args[0]).strip().lower()
    if not cur:
        return False

    # For n-ary predicates, only rewrite first arg if schema says it is Person.
    if len(args) > 1 and kb_schema:
        pred = str(query_obj.get("predicate") or "").strip()
        if pred:
            sig = None
            for p in (kb_schema.get("predicates") or []):
                if p.get("name") == pred:
                    sig = p
                    break
            if sig:
                dom = list(sig.get("args") or [])
                if not dom or str(dom[0]) != "Person":
                    return False

    pairs = _iter_unary_positives(case)
    survivors = _survivor_constants(pairs)
    deceased = _deceased_constants(pairs)
    persons = set()
    ents = (case or {}).get("entities") or {}
    for key in ("Person", "person"):
        vals = ents.get(key)
        if isinstance(vals, list):
            for v in vals:
                if isinstance(v, str) and v.strip():
                    persons.add(v.strip().lower())

    # Fallback inference: if there is one deceased and exactly one other person,
    # treat that other person as the surviving spouse candidate.
    if intent == "surviving_spouse" and len(survivors) != 1 and len(deceased) == 1:
        d = next(iter(deceased))
        others = [p for p in persons if p != d]
        if len(others) == 1:
            survivors = {others[0]}

    if intent == "surviving_spouse":
        if len(survivors) != 1:
            return False
        sole = next(iter(survivors))
        if cur == sole:
            return False
        if cur in deceased and sole not in deceased:
            query_obj["args"][0] = sole
            return True
        if cur not in survivors and cur in deceased:
            query_obj["args"][0] = sole
            return True

    if intent == "deceased":
        if len(deceased) != 1:
            return False
        sole = next(iter(deceased))
        if cur == sole:
            return False
        if cur in survivors and sole not in survivors:
            query_obj["args"][0] = sole
            return True

    return False
