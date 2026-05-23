"""
Detect legal statuses/classifications modeled as narrow primitive types (status-as-type trap).

Law-agnostic: compares normalized type/predicate names and weak lexical cues only.
"""

from __future__ import annotations

import re
from typing import Any

# Weak lexical cues in type names/descriptions (not applied to broad domain types alone).
_STATUS_TYPE_LEXICON: tuple[str, ...] = (
    "status",
    "classification",
    "category",
    "eligible",
    "qualifies",
    "qualify",
    "applicant",
    "resident",
    "citizen",
    "national",
    "company type",
    "spouse",
    "heir",
    "beneficiary",
    "debtor",
    "creditor",
    "parent",
    "subsidiary",
    "undertaking",
    "legal person",
    "vulnerable",
    "minor",
    "adult",
    "holder",
    "owner",
    "member",
    "director",
    "manager",
    "representative",
    "statuut",
    "hoedanigheid",
    "categorie",
    "kwalificeert",
    "begunstigde",
    "schuldenaar",
    "schuldeiser",
    "echtgenoot",
    "erfgenaam",
    "minderjarige",
    "meerderjarige",
    "bestuurder",
    "vertegenwoordiger",
)

# Primitive domains that are usually genuine entity sorts, not legal-status types.
_BROAD_DOMAIN_TYPES: frozenset[str] = frozenset(
    {
        "company",
        "person",
        "legalentity",
        "legalperson",
        "entity",
        "organization",
        "organisation",
        "party",
        "actor",
        "agent",
        "naturalperson",
        "juridicalperson",
        "corporation",
        "firm",
        "enterprise",
    }
)

_RECORD_TYPE_MARKERS: tuple[str, ...] = (
    "record",
    "document",
    "file",
    "entry",
    "datum",
    "event",
    "transaction",
)


def _canon(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "", (name or "").lower())
    if s.startswith("is") and len(s) > 2:
        s = s[2:]
    elif s.startswith("has") and len(s) > 3:
        s = s[3:]
    return s


def _type_has_status_lexicon(type_name: str, description: str = "") -> bool:
    text = ((type_name or "") + " " + (description or "")).lower()
    canon_t = _canon(type_name)
    if canon_t in _BROAD_DOMAIN_TYPES:
        return False
    return any(tok in text for tok in _STATUS_TYPE_LEXICON)


def _is_record_like_type(type_name: str, description: str = "") -> bool:
    text = ((type_name or "") + " " + (description or "")).lower()
    return any(m in text for m in _RECORD_TYPE_MARKERS)


def names_semantically_identical(type_name: str, predicate_name: str) -> bool:
    """True when type and unary is_* predicate names denote the same status label."""
    ct = _canon(type_name)
    cp = _canon(predicate_name)
    if not ct or not cp:
        return False
    if ct == cp:
        return True
    if cp.startswith(ct) or ct.startswith(cp):
        return True
    # Allow minor suffix differences (e.g. eligibleapplicant vs eligibleapplicants).
    shorter, longer = (ct, cp) if len(ct) <= len(cp) else (cp, ct)
    if len(shorter) >= 6 and longer.startswith(shorter):
        return True
    return False


def _unary_classification_predicate_name(name: str) -> bool:
    n = (name or "").strip().lower()
    return n.startswith("is_") or n.startswith("is")


def _matching_status_argument_types(
    predicate_name: str,
    predicate_args: list[str],
    type_set: set[str],
) -> list[str]:
    return [
        at
        for at in predicate_args
        if at in type_set and names_semantically_identical(at, predicate_name)
    ]


def status_as_type_symbol_issue(
    type_name: str,
    *,
    predicate_name: str,
    predicate_args: list[str],
    predicate_kind: str,
    type_description: str = "",
    type_set: set[str] | None = None,
) -> str | None:
    """
    Return human-readable issue if this type/predicate pair is a status-as-type trap.

    None when the pair looks acceptable.
    """
    if type_name not in (predicate_args or []):
        return None
    if not _unary_classification_predicate_name(predicate_name):
        return None
    if not names_semantically_identical(type_name, predicate_name):
        return None
    if _is_record_like_type(type_name, type_description):
        return None

    canon_t = _canon(type_name)
    has_status_lex = _type_has_status_lexicon(type_name, type_description)
    pk = (predicate_kind or "").strip().lower()

    # Redundant is_company(Company) on a broad domain type — not a status-as-type trap.
    if canon_t in _BROAD_DOMAIN_TYPES and not has_status_lex:
        return None

    if pk not in ("derived", "helper", "conclusion") and not has_status_lex:
        return None

    if pk in ("derived", "helper", "conclusion"):
        return (
            "Predicate '%s' takes argument type '%s', which is semantically identical to the "
            "status it concludes. This prevents ordinary entities from being classified. Use a "
            "broader argument type (Person, LegalEntity, Entity, Organization, Company, etc.) "
            "inferred from the law—not a narrow type named after the status. Repair layer: symbols."
            % (predicate_name, type_name)
        )

    return (
        "Type '%s' with predicate '%s' over that same narrow type looks like a legal status or "
        "classification encoded as a primitive type. Use a broader base type for the entity and "
        "model the status as a derived predicate over that base type. Repair layer: symbols."
        % (type_name, predicate_name)
    )


def validate_status_as_type_symbols(
    types: list[str],
    predicates: list,
    *,
    type_descriptions: dict[str, str] | None = None,
) -> None:
    """Validate symbol table for status-as-type modeling. Raises JSONIRCompilationError."""
    from pipeline.kb.json_ir import JSONIRCompilationError, SCHEMA_DESIGN_TAG

    desc = type_descriptions or {}
    type_set = set(types)
    seen: set[tuple[str, str]] = set()
    for pred in predicates:
        matching = _matching_status_argument_types(pred.name, list(pred.args), type_set)
        for arg_t in matching:
            key = (arg_t, pred.name)
            if key in seen:
                continue
            seen.add(key)
            issue = status_as_type_symbol_issue(
                arg_t,
                predicate_name=pred.name,
                predicate_args=list(pred.args),
                predicate_kind=pred.kind,
                type_description=desc.get(arg_t, ""),
                type_set=type_set,
            )
            if issue:
                raise JSONIRCompilationError(SCHEMA_DESIGN_TAG + ": " + issue)


def validate_status_as_type_rules(
    rules: list,
    *,
    pred_kinds: dict[str, str],
) -> None:
    """Flag rules that conclude a status predicate over a variable quantified as the status type."""
    from pipeline.kb.json_ir import JSONIRCompilationError, RULE_DESIGN_TAG, _DERIVED_OUTPUT_KINDS

    for idx, raw_rule in enumerate(rules or []):
        if not isinstance(raw_rule, dict):
            continue
        quant_env = _rule_quant_env(raw_rule, idx)
        if not quant_env:
            continue
        _, then_side = _rule_expr_sides(raw_rule)
        for atom in _iter_pred_atoms_simple(then_side):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if pred_kinds.get(pn) not in _DERIVED_OUTPUT_KINDS:
                continue
            if not _unary_classification_predicate_name(pn):
                continue
            args = atom.get("args") or []
            if len(args) != 1:
                continue
            var = args[0]
            if not isinstance(var, str) or var not in quant_env:
                continue
            var_type = quant_env[var]
            if not names_semantically_identical(var_type, pn):
                continue
            if _canon(var_type) in _BROAD_DOMAIN_TYPES and not _type_has_status_lexicon(var_type):
                continue
            raise JSONIRCompilationError(
                RULE_DESIGN_TAG
                + ": rules[%d].then concludes derived predicate '%s(%s)' where variable '%s' is "
                "quantified as type '%s', which is semantically the same as the status being derived. "
                "Ordinary entities cannot be classified. Quantify a broader entity type and keep '%s' "
                "as a derived predicate over that type. Repair layer: symbols."
                % (idx, pn, var, var, var_type, pn)
            )


def validate_status_as_type_modeling(
    types: list[str],
    predicates: list,
    rules: list,
    *,
    pred_kinds: dict[str, str] | None = None,
    type_descriptions: dict[str, str] | None = None,
) -> None:
    """Run symbol-table and rule-level status-as-type checks."""
    validate_status_as_type_symbols(
        types, predicates, type_descriptions=type_descriptions
    )
    if pred_kinds:
        validate_status_as_type_rules(rules, pred_kinds=pred_kinds)


def _rule_quant_env(raw_rule: dict, idx: int) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in raw_rule.get("forall") or []:
        if isinstance(item, dict) and item.get("var") and item.get("type"):
            out[str(item["var"]).strip()] = str(item["type"]).strip()
    return out


def _rule_expr_sides(raw_rule: dict) -> tuple[Any, Any]:
    if_side = raw_rule.get("if", [])
    then_side = raw_rule.get("then", []) if "then" in raw_rule else raw_rule.get("formula")
    return if_side, then_side


def _iter_pred_atoms_simple(expr: Any):
    if isinstance(expr, list):
        for x in expr:
            yield from _iter_pred_atoms_simple(x)
        return
    if not isinstance(expr, dict):
        return
    if "pred" in expr or "symbol" in expr:
        yield expr
        return
    if "not" in expr:
        yield from _iter_pred_atoms_simple(expr.get("not"))
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            yield from _iter_pred_atoms_simple(x)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            yield from _iter_pred_atoms_simple(x)
        return
