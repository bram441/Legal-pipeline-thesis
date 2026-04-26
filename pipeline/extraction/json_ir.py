import re

from pipeline.extraction.query_role_resolve import apply_role_arg_consistency


class ExtractionIRValidationError(Exception):
    pass


def _norm_name(s):
    return (s or "").strip().lower().replace("_", "")


def _symbol_tokens(name):
    s = str(name or "").strip()
    if not s:
        return []
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    s = s.replace("_", " ").replace("-", " ")
    return [t.lower() for t in s.split() if t.strip()]


def _question_tokens(text):
    s = str(text or "").strip().lower()
    if not s:
        return set()
    s = re.sub(r"[^a-z0-9_ ]+", " ", s)
    toks = [t for t in s.split() if len(t) >= 3]
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "have", "has", "had",
        "does", "did", "what", "which", "when", "where", "why", "who", "according",
        "article", "under", "into", "onto", "about", "your", "their",
    }
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in toks if t not in stop}


def _best_predicate_match(pred_hint, kb_schema, user_question=None):
    preds = [p.get("name") for p in (kb_schema or {}).get("predicates", []) if p.get("name")]
    if not preds:
        return None
    if pred_hint:
        for n in preds:
            if n == pred_hint or _norm_name(n) == _norm_name(pred_hint):
                return n
    hint_toks = set(_symbol_tokens(pred_hint))
    q_toks = _question_tokens(user_question)
    best = None
    best_score = -1.0
    for n in preds:
        nt = set(_symbol_tokens(n))
        if not nt:
            continue
        s = 0.0
        if hint_toks:
            inter = len(hint_toks & nt)
            s += (2.0 * inter) / float(max(1, len(hint_toks) + len(nt)))
        if q_toks:
            s += 0.6 * (len(q_toks & nt) / float(len(nt)))
        if n.startswith("Is") and ("usufruct" in q_toks or "estate" in q_toks):
            s -= 0.2
        if s > best_score:
            best_score = s
            best = n
    return best


def _predicate_sig(kb_schema, pred_name):
    for p in (kb_schema or {}).get("predicates", []):
        if p.get("name") == pred_name:
            return p
    return None


def normalize_case_ir(case_ir, kb_schema):
    if not isinstance(case_ir, dict):
        raise ExtractionIRValidationError("case IR must be an object")
    out = {"facts": [], "entities": {}}
    ents = case_ir.get("entities") or {}
    if isinstance(ents, dict):
        for t, vals in ents.items():
            if isinstance(vals, list):
                out["entities"][str(t)] = [str(v).strip().lower() for v in vals if str(v).strip()]

    assertions = case_ir.get("assertions") or []
    if not isinstance(assertions, list):
        assertions = []
    for a in assertions:
        if not isinstance(a, dict):
            continue
        sym = str(a.get("symbol") or "").strip()
        pred = _best_predicate_match(sym, kb_schema)
        if not pred:
            continue
        sig = _predicate_sig(kb_schema, pred)
        if not sig:
            continue
        args = [str(x).strip().lower() for x in (a.get("args") or []) if str(x).strip()]
        arity = len(sig.get("args") or [])
        if len(args) != arity:
            continue
        neg = bool(a.get("negated", False))
        atom = pred + "(" + ",".join(args) + ")."
        if neg:
            atom = "not " + atom
        out["facts"].append(atom)
    return out


def normalize_query_ir(query_ir, case, kb_schema, user_question):
    if not isinstance(query_ir, dict):
        raise ExtractionIRValidationError("query IR must be an object")
    kind = str(query_ir.get("kind") or "predicate").strip().lower()
    explain = bool(query_ir.get("explain", False))
    if kind == "intent":
        return {
            "type": "intent",
            "intent": str(query_ir.get("intent") or "").strip().lower(),
            "symbol": str(query_ir.get("symbol_hint") or "").strip(),
            "entity": str(query_ir.get("entity_hint") or "").strip().lower(),
            "explain": explain,
        }

    pred_hint = str(query_ir.get("predicate_hint") or "").strip()
    pred = _best_predicate_match(pred_hint, kb_schema, user_question=user_question)
    if not pred:
        raise ExtractionIRValidationError("Could not resolve query predicate from IR")
    mode = str(query_ir.get("mode") or "boolean").strip().lower()
    if mode not in ("boolean", "set"):
        mode = "boolean"
    args = [str(x).strip().lower() for x in (query_ir.get("args") or []) if str(x).strip()]

    query_obj = {"type": "predicate", "predicate": pred, "mode": mode, "args": args, "explain": explain}
    # Deterministic role-based first-arg alignment.
    apply_role_arg_consistency(user_question, query_obj, case, kb_schema=kb_schema)
    # Fallback for common spouse-role questions when only deceased is explicitly grounded:
    # if arg0 is deceased and there is exactly one non-deceased person constant, use that.
    ql = (user_question or "").lower()
    if (
        query_obj.get("mode") == "boolean"
        and isinstance(query_obj.get("args"), list)
        and query_obj["args"]
        and ("surviving spouse" in ql or ("langstlevende" in ql and "echtgenoot" in ql))
    ):
        deceased = set()
        for ln in (case or {}).get("facts") or []:
            m = re.match(r"^\s*IsDeceased\(([^)]+)\)\.\s*$", str(ln))
            if m:
                deceased.add(m.group(1).strip().lower())
        cur0 = str(query_obj["args"][0]).strip().lower()
        if cur0 in deceased:
            persons = []
            for p in ((case or {}).get("entities") or {}).get("Person", []) or []:
                pp = str(p).strip().lower()
                if pp:
                    persons.append(pp)
            candidates = [p for p in persons if p not in deceased]
            if len(candidates) == 1:
                query_obj["args"][0] = candidates[0]
    return query_obj
