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

from pipeline.kb.legal_effect import (
    predicate_looks_like_classification_output,
    predicate_represents_legal_effect_output,
    question_has_legal_effect_language,
    schema_has_legal_effect_output_predicate,
)
from pipeline.semantic.legal_question import (
    domain_heuristics_enabled,
    question_asks_legal_conclusion,
    question_asks_legal_definition,
)
from pipeline.extraction.case_fact_validation import (
    CaseFactAssertionRejected,
    build_case_predicate_rejection_message,
    case_fact_assertion_exempt,
    case_function_may_be_asserted,
    case_predicate_may_be_asserted,
    case_predicate_may_be_asserted_as_factual_input,
    case_text_has_numeric_values,
)
from pipeline.kb.factual_case_input import case_given_predicate_name, is_factual_case_input_candidate
from pipeline.extraction.ir_utils import (
    question_tokens as _question_tokens,
    safe_entity as _safe_entity,
    safe_value as _safe_value,
    symbol_tokens as _symbol_tokens,
)
from pipeline.extraction.query_role_resolve import apply_role_arg_consistency
from pipeline.symbolic.intent_registry import list_public_intents


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

# Public intents selectable in extraction (internal deduction/deduction_set use predicate mode).
SUPPORTED_QUERY_INTENTS: frozenset[str] = frozenset(list_public_intents())
SUPPORTED_QUERY_INTENTS_SORTED: tuple[str, ...] = tuple(sorted(SUPPORTED_QUERY_INTENTS))
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")


def _norm_name(s: Any) -> str:
    return (str(s or "").strip().lower().replace("_", "").replace("-", ""))


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
        if user_question and question_has_legal_effect_language(str(user_question)):
            from pipeline.extraction.query_target_selection import (
                is_legal_output_query_target,
                is_temporal_support_background_target,
            )

            if is_temporal_support_background_target(sym):
                score -= 2.0
            elif is_legal_output_query_target(sym):
                score += 0.35
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


def _derived_bool_predicates(kb_schema: dict) -> list[dict]:
    out: list[dict] = []
    for p in (kb_schema or {}).get("predicates") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        if str(p.get("returns") or "Bool").strip().lower() != "bool":
            continue
        if str(p.get("kind") or "").lower() in {"derived", "conclusion"}:
            out.append(p)
    return out


def _lexical_overlap_score(sym: dict, user_question: str) -> float:
    n = sym.get("name") or ""
    nt = set(_symbol_tokens(n))
    desc = set(_symbol_tokens(sym.get("description") or ""))
    q = _question_tokens(user_question)
    if not nt:
        return 0.0
    score = len(q & nt) / float(len(nt))
    if desc:
        score += 0.5 * (len(q & desc) / float(len(desc)))
    return score


def _looks_like_classification_predicate(sym: dict) -> bool:
    return predicate_looks_like_classification_output(
        str(sym.get("name") or ""),
        description=str(sym.get("description") or ""),
        kind=str(sym.get("kind") or ""),
        legal_output=sym.get("legal_output") if isinstance(sym.get("legal_output"), bool) else None,
        output_category=str(sym.get("output_category") or ""),
    )


def _looks_like_legal_effect_predicate(sym: dict) -> bool:
    return predicate_represents_legal_effect_output(
        str(sym.get("name") or ""),
        description=str(sym.get("description") or ""),
        kind=str(sym.get("kind") or ""),
        legal_output=sym.get("legal_output") if isinstance(sym.get("legal_output"), bool) else None,
        output_category=str(sym.get("output_category") or ""),
    )


def _derived_predicate_specificity_score(sym: dict, user_question: str) -> float:
    """Score derived predicates; higher means a more specific match to the question."""
    n = sym.get("name") or ""
    nt = set(_symbol_tokens(n))
    desc_toks = set(_symbol_tokens(sym.get("description") or ""))
    q = _question_tokens(user_question)
    overlap = _lexical_overlap_score(sym, user_question)
    if not nt:
        return overlap
    q_hit = len(q & nt)
    q_cov = q_hit / float(len(q)) if q else 0.0
    name_cov = q_hit / float(len(nt))
    token_bonus = min(len(nt), 14) * 0.035
    score = overlap + 0.35 * q_cov + 0.12 * name_cov + token_bonus
    effect_q = question_has_legal_effect_language(user_question)
    effect_pred = _looks_like_legal_effect_predicate(sym)
    if effect_q and effect_pred:
        score += 0.55
    if effect_q and _looks_like_classification_predicate(sym):
        score -= 0.65
    if question_asks_legal_definition(user_question) and _looks_like_classification_predicate(sym):
        score -= 0.25
    return score


def _is_more_specific_derived(sym_a: dict, sym_b: dict, user_question: str) -> bool:
    ta = set(_symbol_tokens(sym_a.get("name") or ""))
    tb = set(_symbol_tokens(sym_b.get("name") or ""))
    sa = _derived_predicate_specificity_score(sym_a, user_question)
    sb = _derived_predicate_specificity_score(sym_b, user_question)
    if ta and tb and tb < ta and sa >= sb - 0.05:
        return True
    return sa > sb + 0.08


def _pick_most_specific_derived_predicate(
    user_question: str,
    kb_schema: dict,
    current_pred: str | None,
) -> str | None:
    """Prefer the most specific derived predicate that matches the legal question."""
    derived = _derived_bool_predicates(kb_schema)
    if question_has_legal_effect_language(user_question):
        effect_derived = [d for d in derived if _looks_like_legal_effect_predicate(d)]
        if effect_derived:
            derived = effect_derived
    if not derived:
        return current_pred
    scored = [( _derived_predicate_specificity_score(s, user_question), s) for s in derived]
    scored = [(sc, s) for sc, s in scored if sc > 0]
    if not scored:
        return current_pred
    scored.sort(key=lambda x: -x[0])
    best_sc, best_sym = scored[0]
    if best_sc < 0.2:
        return current_pred
    if len(scored) > 1 and (best_sc - scored[1][0]) < 0.05:
        cur = _symbol_sig(kb_schema, current_pred) if current_pred else None
        if cur and str(cur.get("kind") or "").lower() in {"derived", "conclusion"}:
            return current_pred
        return str(best_sym["name"])
    if not current_pred:
        return str(best_sym["name"])
    cur = _symbol_sig(kb_schema, current_pred)
    if not cur or cur.get("kind") not in {"derived", "conclusion"}:
        return str(best_sym["name"])
    if _is_more_specific_derived(best_sym, cur, user_question):
        return str(best_sym["name"])
    return current_pred


def _try_auto_select_derived_predicate(
    user_question: str,
    case: dict,
    kb_schema: dict,
    raw_args: list[str],
) -> tuple[str, list[str]] | None:
    if not question_asks_legal_conclusion(user_question):
        return None
    pred = _pick_most_specific_derived_predicate(user_question, kb_schema, None)
    if not pred:
        return None
    args = _fill_query_args_from_entities(pred, list(raw_args), case, kb_schema)
    return pred, args


def _validate_query_target_for_legal_question(
    pred: str,
    user_question: str,
    kb_schema: dict,
) -> None:
    from pipeline.extraction.query_target_selection import (
        is_legal_output_query_target,
        is_temporal_support_background_target,
    )

    effect_question = question_has_legal_effect_language(user_question)
    if not question_asks_legal_conclusion(user_question) and not effect_question:
        return
    derived = _derived_bool_predicates(kb_schema)
    sig = _symbol_sig(kb_schema, pred) or {}
    if effect_question and is_temporal_support_background_target(sig):
        if schema_has_legal_effect_output_predicate(derived) or any(
            is_legal_output_query_target(p) for p in derived
        ):
            raise ExtractionIRValidationError(
                "Query target '"
                + pred
                + "' is a temporal support/background relation (previous/next/consecutive period), "
                "not the legal effect answer. Choose a derived predicate with legal_output=true or "
                "output_category legal_effect/consequence/applicability/timing."
            )
    pk = _symbol_kind(sig)
    if pk != "observable":
        sig = _symbol_sig(kb_schema, pred) or {}
        if effect_question and _looks_like_classification_predicate(sig):
            has_effect_derived = schema_has_legal_effect_output_predicate(derived)
            if has_effect_derived:
                raise ExtractionIRValidationError(
                    "Question asks about legal consequences or timing, but query target '"
                    + pred
                    + "' looks like a static classification predicate. Choose a derived predicate that "
                    "represents the legal effect, applicability, or temporal consequence."
                )
            raise ExtractionIRValidationError(
                "Question asks about legal consequences or timing, but the knowledge base only exposes "
                "classification-style derived predicates for '"
                + pred
                + "'. Add a derived legal-output predicate for the effect/timing rule in the KB."
            )
        return
    if derived:
        raise ExtractionIRValidationError(
            "Selected observable predicate '"
            + pred
            + "' for a legal-conclusion question. Observable predicates are case facts and should not be used "
            "as final answers to legal-effect questions. Choose a derived predicate that directly represents "
            "the requested legal status, right, obligation, permission, prohibition, validity result, entitlement, "
            "exclusion, classification, or legal consequence."
        )
    if question_asks_legal_definition(user_question):
        raise ExtractionIRValidationError(
            "Legal-definition or legal-effect question cannot be answered with observable predicate '"
            + pred
            + "'. The knowledge base has no suitable derived predicate; repair the symbol table and rules."
        )


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
    """Domain-specific heuristic (disabled unless LEGAL_PIPELINE_ENABLE_DOMAIN_HEURISTICS=1)."""
    if not domain_heuristics_enabled():
        return
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


def normalize_case_ir(
    case_ir: dict,
    kb_schema: dict,
    *,
    case_text: str | None = None,
    query_predicate: str | None = None,
) -> dict:
    if not isinstance(case_ir, dict):
        raise ExtractionIRValidationError("case IR must be an object")
    out: dict[str, Any] = {"facts": [], "entities": {}, "case_given_factual_inputs": []}

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
        evidence_text = str(a.get("evidence_text") or a.get("source_text") or "").strip() or None
        allowed, rejection_code = case_predicate_may_be_asserted(
            sig,
            case_text=case_text,
            evidence_text=evidence_text,
            query_predicate=query_predicate,
            kb_schema=kb_schema,
        )
        render_pred = pred
        case_given_meta: dict[str, Any] | None = None
        if allowed:
            factual_ok, _factual_code, snippet = case_predicate_may_be_asserted_as_factual_input(
                sig,
                case_text=case_text,
                evidence_text=evidence_text,
                query_predicate=query_predicate,
                kb_schema=kb_schema,
            )
            if (
                factual_ok
                and is_factual_case_input_candidate(sig, kb_schema)
                and not case_fact_assertion_exempt(sig)
            ):
                render_pred = case_given_predicate_name(pred)
                case_given_meta = {
                    "target_predicate": pred,
                    "input_predicate": render_pred,
                    "source": str(a.get("source") or "case_given"),
                    "evidence_text": snippet or evidence_text or "",
                    "assertion_kind": "factual_threshold_satisfaction",
                }
        if not allowed:
            raise CaseFactAssertionRejected(
                build_case_predicate_rejection_message(pred, rejection_code),
                pred=pred,
                rejection_code=rejection_code or "invalid_case_fact",
            )
        arity = len(sig.get("args") or []) if sig else 0
        args = _normalize_args(a.get("args") or [], arity)
        if args is None:
            raise ExtractionIRValidationError(f"Predicate assertion {pred} expects {arity} args, got {a.get('args')}")
        for typ, arg in zip(sig.get("args") or [], args):
            _merge_typed_entity(out["entities"], str(typ), arg)
        if case_given_meta is not None:
            case_given_meta["args"] = list(args)
            out["case_given_factual_inputs"].append(case_given_meta)
        fact = _render_pred_fact(render_pred, args, bool(a.get("negated", False)))
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
        allowed, rejection_code = case_function_may_be_asserted(sig)
        if not allowed:
            raise ExtractionIRValidationError(
                "Case extraction cannot assert helper/composite function "
                + fun
                + ". Use observable numeric inputs only."
            )
        arity = len(sig.get("args") or []) if sig else 0
        args = _normalize_args(a.get("args") or [], arity)
        if args is None:
            raise ExtractionIRValidationError(f"Function assertion {fun} expects {arity} args, got {a.get('args')}")
        for typ, arg in zip(sig.get("args") or [], args):
            _merge_typed_entity(out["entities"], str(typ), arg)
        ret = (sig.get("returns") or "Int") if sig else "Int"
        _validate_value_for_function_return(a.get("value"), str(ret))
        if not case_text_has_numeric_values(case_text):
            val_s = str(a.get("value") or "").strip()
            if val_s and case_text and val_s not in case_text.replace(",", "").replace(" ", ""):
                raise ExtractionIRValidationError(
                    "Case extraction cannot invent numeric value "
                    + val_s
                    + " for "
                    + fun
                    + " when the case text provides no explicit numbers."
                )
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
    query_target_selection_diag: dict = {}
    kind = str(query_ir.get("kind") or "predicate").strip().lower()
    explain = bool(query_ir.get("explain", False))
    if kind == "intent":
        intent_name = str(query_ir.get("intent") or "").strip().lower()
        if not intent_name:
            raise ExtractionIRValidationError("intent query requires a non-empty intent field")
        if intent_name in ("deduction", "deduction_set"):
            raise ExtractionIRValidationError(
                "Direct intent '" + intent_name + "' is internal. Use kind=predicate with mode=boolean or mode=set."
            )
        if intent_name not in SUPPORTED_QUERY_INTENTS:
            raise ExtractionIRValidationError(
                "Unsupported query intent '"
                + intent_name
                + "'. Supported public intents: "
                + ", ".join(SUPPORTED_QUERY_INTENTS_SORTED)
            )
        out: dict = {"type": "intent", "intent": intent_name, "explain": explain}
        if intent_name == "get_range":
            out["function"] = str(query_ir.get("function") or query_ir.get("symbol_hint") or "").strip()
            out["args"] = [_safe_entity(x) for x in (query_ir.get("args") or []) if _safe_entity(x)]
            out["entity"] = _safe_entity(query_ir.get("entity_hint") or "")
        elif intent_name == "satisfiable":
            pass
        elif intent_name in ("propagation", "relevance"):
            syms = query_ir.get("focus_symbols") or query_ir.get("symbol_hints") or []
            if isinstance(syms, str):
                syms = [syms]
            out["focus_symbols"] = [str(s).strip() for s in syms if str(s).strip()]
            ents = query_ir.get("focus_entities") or query_ir.get("entity_hints") or []
            if isinstance(ents, str):
                ents = [ents]
            out["focus_entities"] = [_safe_entity(x) for x in ents if _safe_entity(x)]
            if intent_name == "propagation":
                out["include_unknown"] = bool(query_ir.get("include_unknown", False))
        elif intent_name == "model_expansion":
            syms = query_ir.get("focus_symbols") or []
            if isinstance(syms, str):
                syms = [syms]
            out["focus_symbols"] = [str(s).strip() for s in syms if str(s).strip()]
            ents = query_ir.get("focus_entities") or []
            if isinstance(ents, str):
                ents = [ents]
            out["focus_entities"] = [_safe_entity(x) for x in ents if _safe_entity(x)]
            mm = query_ir.get("max_models")
            out["max_models"] = int(mm) if mm is not None else 1
        elif intent_name == "optimization":
            out["direction"] = str(query_ir.get("direction") or "min").strip().lower()
            obj_fn = str(query_ir.get("function") or query_ir.get("symbol_hint") or "").strip()
            out["objective"] = {
                "function": obj_fn,
                "args": [_safe_entity(x) for x in (query_ir.get("args") or []) if _safe_entity(x)],
            }
        elif intent_name == "explain":
            target = query_ir.get("target")
            if isinstance(target, dict):
                out["target"] = target
            elif str(query_ir.get("target_type") or "").lower() == "satisfiable":
                out["target"] = {"type": "satisfiable"}
            else:
                pred = str(query_ir.get("predicate_hint") or query_ir.get("predicate") or "").strip()
                args = [_safe_entity(x) for x in (query_ir.get("args") or []) if _safe_entity(x)]
                if pred:
                    out["target"] = {"type": "predicate", "predicate": pred, "args": args}
                else:
                    raise ExtractionIRValidationError("explain intent requires target or predicate_hint with args")
        return out

    pred_hint = str(query_ir.get("predicate_hint") or query_ir.get("predicate") or "").strip()
    mode = str(query_ir.get("mode") or "boolean").strip().lower()
    if mode not in ("boolean", "set"):
        mode = "boolean"

    raw_args = [_safe_entity(x) for x in (query_ir.get("args") or []) if _safe_entity(x)]

    pred = _best_symbol_match(pred_hint, kb_schema, user_question=user_question, bool_only=True, prefer_derived=True)
    if not pred:
        raise ExtractionIRValidationError("Could not resolve query predicate from IR")

    if question_asks_legal_conclusion(user_question):
        from pipeline.extraction.query_target_selection import apply_query_target_selection

        pred, query_target_selection_diag = apply_query_target_selection(
            pred_hint=pred_hint,
            user_question=user_question,
            kb_schema=kb_schema,
            current_pred=pred,
        )
        if not pred:
            raise ExtractionIRValidationError("Could not resolve query predicate from IR")

    if question_asks_legal_conclusion(user_question):
        refined = _pick_most_specific_derived_predicate(user_question, kb_schema, pred)
        if refined:
            pred = refined
        pk_tmp = _symbol_kind(_symbol_sig(kb_schema, pred))
        if pk_tmp == "observable":
            auto = _try_auto_select_derived_predicate(user_question, case, kb_schema, raw_args)
            if auto:
                pred, raw_args = auto

    pk = _symbol_kind(_symbol_sig(kb_schema, pred))
    if pk == "helper":
        raise ExtractionIRValidationError(
            "Do not query helper predicate " + pred + "; choose a derived legal conclusion."
        )

    if mode == "boolean" and pk == "observable" and question_asks_legal_conclusion(user_question):
        auto = _try_auto_select_derived_predicate(user_question, case, kb_schema, raw_args)
        if auto:
            pred, args = auto
            pk = _symbol_kind(_symbol_sig(kb_schema, pred))
        else:
            _validate_query_target_for_legal_question(pred, user_question, kb_schema)

    args = _fill_query_args_from_entities(pred, raw_args, case, kb_schema)

    query_obj = {
        "type": "predicate",
        "predicate": pred,
        "mode": mode,
        "args": args,
        "explain": explain,
        "predicate_kind": pk,
    }
    if query_target_selection_diag:
        query_obj["query_target_selection"] = query_target_selection_diag

    if domain_heuristics_enabled():
        apply_role_arg_consistency(user_question, query_obj, case, kb_schema=kb_schema)
        _maybe_normalize_binary_person_person_survivor_deceased(query_obj, case, kb_schema)
    else:
        from pipeline.extraction.query_role_generic import apply_generic_query_arg_fill

        apply_generic_query_arg_fill(user_question, query_obj, case, kb_schema)

    _ensure_singleton_query_args(pred, query_obj["args"], case, kb_schema)

    from pipeline.extraction.query_period_binding import apply_query_period_binding

    apply_query_period_binding(query_obj, case, kb_schema, user_question)

    if mode == "boolean":
        _validate_query_target_for_legal_question(pred, user_question, kb_schema)

    if mode == "boolean":
        _validate_query_args(pred, query_obj["args"], case, kb_schema)
    elif mode == "set":
        # Set queries should not carry concrete args in current symbolic router.
        query_obj["args"] = []

    return query_obj
