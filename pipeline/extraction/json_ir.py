"""Schema-aware normalization for case/query JSON IR.

The LLM should output structured extraction IR, while this module performs the
stable deterministic conversion to the older runtime shape:

case -> {"facts": [...], "entities": {...}}
query -> {"type": "predicate", "predicate": ..., "mode": ..., "args": [...]}

Major stability choices:
- supports predicate assertions and function/value assertions;
- never emits facts for undeclared symbols;
- validates predicate/function arity;
- resolves query args from case entities when safe;
- avoids placeholders like "?", "this_company", or type names in final args.
"""

from __future__ import annotations

import re
from typing import Any

from pipeline.extraction.query_role_resolve import apply_role_arg_consistency


class ExtractionIRValidationError(Exception):
    pass


# Do not list role-words like "deceased"/"spouse" here: they are valid constant names
# in legal cases (e.g. IsSurvivingLegalCohabitant(survivor, deceased)).
_PLACEHOLDERS = frozenset(
    {
        "",
        "?",
        "unknown",
        "none",
        "null",
        "this",
        "this_company",
        "the_company",
        "this_entity",
        "this_person",
        "this_year",
        "company",
        "person",
        "financialyear",
        "financial_year",
        "fy",
        "estate",
        "decision",
    }
)

SUPPORTED_QUERY_INTENTS: frozenset[str] = frozenset(
    {
        "satisfiable",
        "deduction",
        "deduction_set",
        "get_range",
        "explain",
        "propagation",
        "model_checking",
        "model_expansion",
        "relevance",
        "optimization",
    }
)
# Stable order for OpenAI json_schema enums and docs.
SUPPORTED_QUERY_INTENTS_SORTED: tuple[str, ...] = tuple(sorted(SUPPORTED_QUERY_INTENTS))
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")


def _norm_name(s: Any) -> str:
    return (str(s or "").strip().lower().replace("_", "").replace("-", ""))


def _symbol_tokens(name: Any) -> list[str]:
    s = str(name or "").strip()
    if not s:
        return []
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
    s = s.replace("_", " ").replace("-", " ")
    return [t.lower() for t in s.split() if t.strip()]


def _question_tokens(text: Any) -> set[str]:
    s = str(text or "").strip().lower()
    if not s:
        return set()
    s = re.sub(r"[^a-z0-9_ ]+", " ", s)
    toks = [t for t in s.split() if len(t) >= 3]
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "have", "has", "had",
        "does", "did", "what", "which", "when", "where", "why", "who", "according",
        "article", "under", "into", "onto", "about", "your", "their", "will", "shall",
        "can", "may", "must", "een", "het", "dat", "die", "wat", "welke", "volgens",
    }
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t for t in toks if t not in stop}


def _safe_entity(value: Any) -> str:
    s = str(value or "").strip().lower()
    s = re.sub(r"[^a-z0-9_]+", "_", s).strip("_")
    if not s:
        return ""
    if s[0].isdigit():
        s = "e_" + s
    return s


def _safe_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value or "").strip()
    if not s:
        return ""
    if _NUMBER_RE.match(s) or s.lower() in {"true", "false"}:
        return s.lower()
    return _safe_entity(s)


def _all_symbols(kb_schema: dict, *, bool_only: bool | None = None) -> list[dict]:
    syms = []
    for p in (kb_schema or {}).get("predicates", []) or []:
        if p.get("name"):
            syms.append({**p, "_category": "predicate"})
    for f in (kb_schema or {}).get("functions", []) or []:
        if f.get("name"):
            syms.append({**f, "_category": "function"})
    if bool_only is True:
        return [s for s in syms if str(s.get("returns") or "").lower() == "bool" or s.get("_category") == "predicate"]
    if bool_only is False:
        return [s for s in syms if not (str(s.get("returns") or "").lower() == "bool" or s.get("_category") == "predicate")]
    return syms


def _best_symbol_match(symbol_hint: Any, kb_schema: dict, *, user_question: Any = None, bool_only: bool | None = None, prefer_derived: bool = False) -> str | None:
    syms = _all_symbols(kb_schema, bool_only=bool_only)
    names = [s.get("name") for s in syms if s.get("name")]
    if not names:
        return None
    hint = str(symbol_hint or "").strip()
    if hint:
        for n in names:
            if n == hint or _norm_name(n) == _norm_name(hint):
                return n

    hint_toks = set(_symbol_tokens(hint))
    q_toks = _question_tokens(user_question)
    best = None
    best_score = -1.0
    for sym in syms:
        n = sym.get("name")
        nt = set(_symbol_tokens(n))
        if not nt:
            continue
        score = 0.0
        if hint_toks:
            inter = len(hint_toks & nt)
            score += (2.0 * inter) / float(max(1, len(hint_toks) + len(nt)))
        if q_toks:
            score += 0.7 * (len(q_toks & nt) / float(len(nt)))
        kind = str(sym.get("kind") or "").lower()
        if prefer_derived and kind in {"derived", "conclusion"}:
            score += 0.25
        if prefer_derived and kind in {"observable", "input"}:
            score -= 0.15
        if score > best_score:
            best_score = score
            best = n
    return best if best_score > 0 else None


def _symbol_sig(kb_schema: dict, name: str) -> dict | None:
    for s in _all_symbols(kb_schema):
        if s.get("name") == name:
            return s
    return None


def _symbol_kind(sig: dict | None) -> str:
    if not sig:
        return "unknown"
    return str(sig.get("kind") or "unknown").strip().lower()


def _merge_typed_entity(out_entities: dict, typ: str, value: str) -> None:
    if not typ or not value:
        return
    bucket = out_entities.setdefault(typ, [])
    if value not in bucket:
        bucket.append(value)
    out_entities[typ] = sorted(bucket)


def _validate_value_for_function_return(value: Any, returns: str) -> None:
    r = (returns or "").strip()
    if r == "Bool":
        if not isinstance(value, bool) and str(value).strip().lower() not in {"true", "false"}:
            raise ExtractionIRValidationError("Function value for Bool return must be boolean or true/false")
    elif r == "Int":
        if isinstance(value, bool):
            raise ExtractionIRValidationError("Function value for Int return must be an integer (not boolean)")
        if isinstance(value, int):
            return
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return
        raise ExtractionIRValidationError("Function value for Int return must be an integer")
    elif r in {"Real", "Float"}:
        if isinstance(value, bool):
            raise ExtractionIRValidationError("Function value for Real return must be numeric (not boolean)")
        if isinstance(value, (int, float)):
            return
        try:
            float(str(value).strip())
        except ValueError as e:
            raise ExtractionIRValidationError("Function value for Real return must be numeric") from e


def _entities_by_type(case: dict, typ: str) -> list[str]:
    ents = ((case or {}).get("entities") or {})
    vals = ents.get(typ) or ents.get(str(typ)) or []
    if not isinstance(vals, list):
        return []
    return [_safe_entity(v) for v in vals if _safe_entity(v)]


# Defaults when the case omits a sort the query still needs (see prompts/shared/json_ir_contract.txt).
_DEFAULT_ENTITY_BY_SCHEMA_TYPE = {
    "Estate": "estate_main",
    "Good": "goods_main",
    "Property": "property_main",
    "RealEstate": "residence_main",
    "HouseholdFurniture": "furniture_main",
    "FinancialYear": "fy_main",
}


def _typed_values_for_other_types(case: dict, skip_type: str) -> set[str]:
    out: set[str] = set()
    for t2, vs in ((case or {}).get("entities") or {}).items():
        if t2 == skip_type:
            continue
        if not isinstance(vs, list):
            continue
        for v in vs:
            s = _safe_entity(v)
            if s:
                out.add(s)
    return out


def _ensure_singleton_query_args(pred: str, args: list, case: dict, kb_schema: dict) -> None:
    """Fill placeholder or missing args using entities or law-agnostic defaults; mutates args and case.entities."""
    sig = _symbol_sig(kb_schema, pred)
    if not sig:
        return
    types = [str(t) for t in (sig.get("args") or [])]
    if not types:
        return
    while len(args) < len(types):
        args.append("")
    for i, typ in enumerate(types):
        raw = _safe_entity(args[i]) if i < len(args) else ""
        typ_l = _safe_entity(str(typ))
        is_ph = (
            (not raw)
            or raw in _PLACEHOLDERS
            or raw == typ_l
            or raw == str(typ).strip().lower()
        )
        if not is_ph:
            if raw in _typed_values_for_other_types(case, typ):
                d = _DEFAULT_ENTITY_BY_SCHEMA_TYPE.get(typ)
                if d:
                    args[i] = d
                    _merge_typed_entity(case.setdefault("entities", {}), typ, d)
            continue
        cand = _entities_by_type(case, typ)
        if len(cand) == 1:
            args[i] = cand[0]
            continue
        d = _DEFAULT_ENTITY_BY_SCHEMA_TYPE.get(typ)
        if d:
            args[i] = d
            _merge_typed_entity(case.setdefault("entities", {}), typ, d)


def _person_constants_from_case(case: dict) -> set[str]:
    """Person names from case.entities plus unary IsDeceased(x). facts (constants only)."""
    names = set(_entities_by_type(case, "Person"))
    for ln in (case or {}).get("facts") or []:
        m = re.match(r"^\s*IsDeceased\(([^)]+)\)\.\s*$", str(ln))
        if m:
            names.add(_safe_entity(m.group(1)))
    return {n for n in names if n}


def _deceased_persons_from_is_deceased_facts(case: dict) -> set[str]:
    out: set[str] = set()
    for ln in (case or {}).get("facts") or []:
        m = re.match(r"^\s*IsDeceased\(([^)]+)\)\.\s*$", str(ln))
        if m:
            out.add(_safe_entity(m.group(1)))
    return {d for d in out if d}


def _maybe_normalize_binary_person_person_survivor_deceased(
    query_obj: dict, case: dict, kb_schema: dict
) -> None:
    """If KB asks (Person, Person) and facts give exactly one IsDeceased/ and one other person, use (survivor, deceased).

    Fills duplicate or half-empty args when the model binds the same Person twice for both roles
    (common when only one name appears under case.entities.Person).
    """
    if str(query_obj.get("type") or "").lower() != "predicate":
        return
    if str(query_obj.get("mode") or "").lower() != "boolean":
        return
    pred = str(query_obj.get("predicate") or "").strip()
    if not pred:
        return
    sig = _symbol_sig(kb_schema, pred)
    if not sig:
        return
    kinds = list(sig.get("args") or [])
    if len(kinds) != 2 or kinds[0] != "Person" or kinds[1] != "Person":
        return
    args = list(query_obj.get("args") or [])
    if len(args) < 2:
        return
    dead = _deceased_persons_from_is_deceased_facts(case)
    pool = _person_constants_from_case(case)
    if len(dead) != 1:
        return
    d = next(iter(dead))
    living = sorted(p for p in pool if p != d)
    if len(living) != 1:
        return
    s = living[0]
    a0 = _safe_entity(str(args[0])) if len(args) > 0 else ""
    a1 = _safe_entity(str(args[1])) if len(args) > 1 else ""

    def unf(x: str) -> bool:
        return (not x) or x in _PLACEHOLDERS or x == "person"

    if a0 == a1 and a0 in (s, d):
        query_obj["args"] = [s, d]
        return
    if unf(a0) and a1 == s:
        query_obj["args"] = [s, d]
        return
    if unf(a1) and a0 == s:
        query_obj["args"] = [s, d]
        return
    if unf(a0) and a1 == d:
        query_obj["args"] = [s, d]
        return
    if unf(a1) and a0 == d:
        query_obj["args"] = [s, d]
        return
    if not unf(a0) and not unf(a1) and {a0, a1} == {s, d} and (a0, a1) != (s, d):
        query_obj["args"] = [s, d]


def _entity_in_case(case: dict, value: str) -> bool:
    v = _safe_entity(value)
    for vals in ((case or {}).get("entities") or {}).values():
        if isinstance(vals, list) and v in {_safe_entity(x) for x in vals}:
            return True
    return False


def _normalize_args(raw_args: Any, arity: int) -> list[str] | None:
    if not isinstance(raw_args, list):
        return None
    args = [_safe_entity(x) for x in raw_args]
    args = [x for x in args if x and x not in _PLACEHOLDERS]
    if len(args) != arity:
        return None
    return args


def _render_pred_fact(pred: str, args: list[str], negated: bool = False) -> str:
    atom = pred + "(" + ",".join(args) + ")."
    return "not " + atom if negated else atom


def _render_func_fact(fun: str, args: list[str], value: Any) -> str:
    rhs = _safe_value(value)
    if not rhs:
        raise ExtractionIRValidationError("Function assertion has empty value for " + fun)
    return fun + "(" + ",".join(args) + ") = " + rhs + "."


def normalize_case_ir(case_ir: dict, kb_schema: dict) -> dict:
    if not isinstance(case_ir, dict):
        raise ExtractionIRValidationError("case IR must be an object")
    out = {"facts": [], "entities": {}}

    ents = case_ir.get("entities") or {}
    if isinstance(ents, dict):
        valid_types = {str(t) for t in (kb_schema or {}).get("types", [])}
        for t, vals in ents.items():
            t_name = str(t).strip()
            if valid_types and t_name not in valid_types:
                # Do not invent domains that are not in the KB vocabulary.
                continue
            if isinstance(vals, list):
                cleaned = sorted({v for v in (_safe_entity(x) for x in vals) if v})
                if cleaned:
                    out["entities"][t_name] = cleaned

    facts_seen: set[str] = set()

    # Predicate facts.
    assertions = case_ir.get("assertions") or []
    if not isinstance(assertions, list):
        raise ExtractionIRValidationError("case_ir.assertions must be a list")
    for i, a in enumerate(assertions):
        if not isinstance(a, dict):
            raise ExtractionIRValidationError(f"case_ir.assertions[{i}] must be an object")
        sym = str(a.get("symbol") or a.get("predicate") or "").strip()
        pred = _best_symbol_match(sym, kb_schema, bool_only=True)
        if not pred:
            raise ExtractionIRValidationError(f"Could not resolve predicate assertion symbol: {sym}")
        sig = _symbol_sig(kb_schema, pred)
        k = _symbol_kind(sig)
        if k == "helper":
            raise ExtractionIRValidationError(
                "Case extraction cannot assert helper predicate " + pred + ". Use observable facts only."
            )
        if k == "derived":
            raise ExtractionIRValidationError(
                "Case extraction must not assert derived predicate "
                + pred
                + " as a fact; assert observable inputs and let the KB derive conclusions."
            )
        arity = len(sig.get("args") or []) if sig else 0
        args = _normalize_args(a.get("args") or [], arity)
        if args is None:
            raise ExtractionIRValidationError(f"Predicate assertion {pred} expects {arity} args, got {a.get('args')}")
        for typ, arg in zip(sig.get("args") or [], args):
            _merge_typed_entity(out["entities"], str(typ), arg)
        fact = _render_pred_fact(pred, args, bool(a.get("negated", False)))
        if fact not in facts_seen:
            out["facts"].append(fact)
            facts_seen.add(fact)

    # Numeric/custom function facts. Accept either `value_assertions` or `assignments`.
    value_assertions = case_ir.get("value_assertions")
    if value_assertions is None:
        value_assertions = case_ir.get("assignments") or []
    if not isinstance(value_assertions, list):
        raise ExtractionIRValidationError("case_ir.value_assertions must be a list")
    for i, a in enumerate(value_assertions):
        if not isinstance(a, dict):
            raise ExtractionIRValidationError(f"case_ir.value_assertions[{i}] must be an object")
        sym = str(a.get("symbol") or a.get("function") or "").strip()
        fun = _best_symbol_match(sym, kb_schema, bool_only=False)
        if not fun:
            raise ExtractionIRValidationError(f"Could not resolve function assertion symbol: {sym}")
        sig = _symbol_sig(kb_schema, fun)
        fk = _symbol_kind(sig)
        if fk == "helper":
            raise ExtractionIRValidationError("Case extraction cannot assert helper function " + fun + ".")
        arity = len(sig.get("args") or []) if sig else 0
        args = _normalize_args(a.get("args") or [], arity)
        if args is None:
            raise ExtractionIRValidationError(f"Function assertion {fun} expects {arity} args, got {a.get('args')}")
        for typ, arg in zip(sig.get("args") or [], args):
            _merge_typed_entity(out["entities"], str(typ), arg)
        ret = (sig.get("returns") or "Int") if sig else "Int"
        _validate_value_for_function_return(a.get("value"), str(ret))
        fact = _render_func_fact(fun, args, a.get("value"))
        if fact not in facts_seen:
            out["facts"].append(fact)
            facts_seen.add(fact)

    for t_name, vals in list(out["entities"].items()):
        if isinstance(vals, list):
            out["entities"][t_name] = sorted(set(vals))

    return out


def _fill_query_args_from_entities(pred: str, args: list[str], case: dict, kb_schema: dict) -> list[str]:
    sig = _symbol_sig(kb_schema, pred)
    if not sig:
        return args
    expected_types = list(sig.get("args") or [])
    out: list[str] = []
    for i, typ in enumerate(expected_types):
        raw = _safe_entity(args[i]) if i < len(args) else ""
        typ_l = _safe_entity(str(typ))
        is_ph = (
            (not raw)
            or raw in _PLACEHOLDERS
            or raw == typ_l
            or raw == str(typ).strip().lower()
        )
        if raw and not is_ph:
            out.append(raw)
            continue
        candidates = _entities_by_type(case, typ)
        if len(candidates) == 1:
            out.append(candidates[0])
        else:
            # Keep unresolved; final validation will produce actionable feedback.
            out.append(raw)
    return out


def _validate_query_args(pred: str, args: list[str], case: dict, kb_schema: dict) -> None:
    sig = _symbol_sig(kb_schema, pred)
    if not sig:
        raise ExtractionIRValidationError("Could not find predicate signature for query: " + pred)
    expected_types = list(sig.get("args") or [])
    if len(args) != len(expected_types):
        raise ExtractionIRValidationError(f"Query predicate {pred} expects {len(expected_types)} args, got {len(args)}: {args}")
    for arg, typ in zip(args, expected_types):
        if not arg or arg in _PLACEHOLDERS or arg == _safe_entity(typ):
            raise ExtractionIRValidationError(f"Query arg for type {typ} is unresolved placeholder: {arg}")
        # Be strict only when the case explicitly provides entities of this type.
        typed_ents = _entities_by_type(case, typ)
        allowed: set[str] = set(typed_ents)
        if str(typ) == "Person":
            allowed |= _person_constants_from_case(case)
        if allowed and arg not in allowed:
            raise ExtractionIRValidationError(
                f"Query arg '{arg}' is not a {typ} entity in the case. Candidates: {sorted(allowed)}"
            )


def normalize_query_ir(query_ir: dict, case: dict, kb_schema: dict, user_question: str) -> dict:
    if not isinstance(query_ir, dict):
        raise ExtractionIRValidationError("query IR must be an object")
    kind = str(query_ir.get("kind") or "predicate").strip().lower()
    explain = bool(query_ir.get("explain", False))
    if kind == "intent":
        intent_name = str(query_ir.get("intent") or "").strip().lower()
        if not intent_name:
            raise ExtractionIRValidationError("intent query requires a non-empty intent field")
        if intent_name not in SUPPORTED_QUERY_INTENTS:
            raise ExtractionIRValidationError(
                "Unsupported query intent '"
                + intent_name
                + "'. Supported: "
                + ", ".join(SUPPORTED_QUERY_INTENTS_SORTED)
            )
        return {
            "type": "intent",
            "intent": intent_name,
            "symbol": str(query_ir.get("symbol_hint") or "").strip(),
            "entity": _safe_entity(query_ir.get("entity_hint") or ""),
            "explain": explain,
        }

    pred_hint = str(query_ir.get("predicate_hint") or query_ir.get("predicate") or "").strip()
    pred = _best_symbol_match(pred_hint, kb_schema, user_question=user_question, bool_only=True, prefer_derived=True)
    if not pred:
        raise ExtractionIRValidationError("Could not resolve query predicate from IR")
    pk = _symbol_kind(_symbol_sig(kb_schema, pred))
    if pk == "helper":
        raise ExtractionIRValidationError(
            "Do not query helper predicate " + pred + "; choose a derived legal conclusion observable from the case."
        )
    mode = str(query_ir.get("mode") or "boolean").strip().lower()
    if mode not in ("boolean", "set"):
        mode = "boolean"

    raw_args = [_safe_entity(x) for x in (query_ir.get("args") or []) if _safe_entity(x)]
    args = _fill_query_args_from_entities(pred, raw_args, case, kb_schema)

    query_obj = {"type": "predicate", "predicate": pred, "mode": mode, "args": args, "explain": explain}

    # Existing project-specific role alignment still helps for spouse/deceased phrasing.
    apply_role_arg_consistency(user_question, query_obj, case, kb_schema=kb_schema)

    _maybe_normalize_binary_person_person_survivor_deceased(query_obj, case, kb_schema)

    ql = (user_question or "").lower()
    if (
        query_obj.get("mode") == "boolean"
        and isinstance(query_obj.get("args"), list)
        and query_obj["args"]
        and ("surviving spouse" in ql or ("langstlevende" in ql and "echtgenoot" in ql))
    ):
        deceased = _deceased_persons_from_is_deceased_facts(case)
        pool = _person_constants_from_case(case)
        alive_list = [p for p in pool if p not in deceased]
        cur0 = _safe_entity(query_obj["args"][0])
        if cur0 in deceased and len(alive_list) == 1:
            query_obj["args"][0] = alive_list[0]
        elif (not cur0 or cur0 in _PLACEHOLDERS or cur0 == "person") and len(alive_list) == 1:
            query_obj["args"][0] = alive_list[0]

    _ensure_singleton_query_args(pred, query_obj["args"], case, kb_schema)

    if mode == "boolean":
        _validate_query_args(pred, query_obj["args"], case, kb_schema)
    elif mode == "set":
        # Set queries should not carry concrete args in current symbolic router.
        query_obj["args"] = []

    return query_obj
