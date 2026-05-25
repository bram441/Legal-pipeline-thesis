"""JSON IR support for deterministic FO(.) rendering.

This version intentionally makes the JSON_IR backend stricter than the legacy
LLM-to-FO path. The goal is not to silently repair bad legal models, but to
fail early with useful feedback so the retry loop can produce a better IR.

Supported rule object format, besides legacy string rules:

{
  "forall": [{"var": "c", "type": "Company"}],
  "if": [ {"pred": "IsCompany", "args": ["c"]} ],
  "then": [ {"pred": "SmallCompany", "args": ["c"]} ],
  "operator": "implies"   // or "iff"
}

Atoms/expressions accepted inside `if` and `then`:
- {"pred": "P", "args": ["x"], "negated": false}
- {"not": <expr>}
- {"and": [<expr>, ...]}
- {"or": [<expr>, ...]}
- {"compare": {"left": <term>, "op": "<=", "right": <term>}}
- {"left": <term>, "op": "<=", "right": <term>}  // shorthand

Terms:
- variables/constants as strings, e.g. "x", "fy1"
- numbers / booleans
- {"func": "EmployeeCount", "args": ["c", "fy"]}

Important stability choices:
- undeclared symbols are errors by default;
- object rules do not pad/truncate/swap arguments;
- predicates must return Bool;
- functions should return a non-Bool scalar/custom type;
- metadata like `kind` is preserved in normalized IR for downstream use.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from difflib import get_close_matches
from typing import Any

from pipeline.kb.composite_predicate_heuristics import (
    looks_computed_composite,
    symbol_background_or_case_input,
    symbol_directly_observable,
)
from pipeline.kb.json_ir_repair import RULE_DESIGN_TAG, SCHEMA_DESIGN_TAG


class JSONIRCompilationError(Exception):
    pass


_INPUT_BRIDGE_KINDS = frozenset({"observable", "input", "helper", "unknown"})
_DERIVED_OUTPUT_KINDS = frozenset({"derived", "conclusion"})
_RE_RULE_IDX = re.compile(r"rules\[(\d+)\]")


_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_SCALAR_TYPES = {"Bool", "Int", "Real"}
# Domain sorts the LLM may introduce as refinements of "Asset" in inheritance KBs; FO/IDP still accept as first-order terms.
_ASSET_LIKE_SORTS = frozenset(
    {
        "HouseholdFurniture",
        "FamilyHome",
        "RealEstate",
        "ResidentialProperty",
        "MovableProperty",
        "ImmovableProperty",
        "PersonalProperty",
        "EstateProperty",
    }
)
# Inheritance KBs often refine "Good" with household/real-estate sorts; treat as compatible.
_GOOD_LIKE_SORTS = frozenset(
    {
        "Good",
        "HouseholdFurniture",
        "FamilyHome",
        "MovableProperty",
        "PersonalProperty",
        "EstateProperty",
    }
)
_ESTATE_LIKE_SORTS = frozenset({"Estate", "EstateProperty", "RealEstate", "ResidentialProperty"})

def _law_sort_assignable(expected: str, got: str) -> bool:
    if expected == got:
        return True
    from pipeline.semantic.legal_question import domain_heuristics_enabled

    if not domain_heuristics_enabled():
        return False
    if expected == "Asset" and got in _ASSET_LIKE_SORTS:
        return True
    if expected in _GOOD_LIKE_SORTS and got in _GOOD_LIKE_SORTS:
        return True
    if expected in _ESTATE_LIKE_SORTS and got in _ESTATE_LIKE_SORTS:
        return True
    return False


_ALLOWED_COMPARE_OPS = {"=", "~=", "<", "=<", "<=", ">", ">=", "=>"}
_ALLOWED_KINDS = {"observable", "derived", "helper", "conclusion", "input", "unknown"}


@dataclass(frozen=True)
class PredAtomUsage:
    """Predicate atom occurrence in a rule with negation and placement."""

    name: str
    negated: bool
    rule_index: int
    side: str  # "if" | "then"


@dataclass(frozen=True)
class SymbolDecl:
    name: str
    args: list[str]
    returns: str
    kind: str = "unknown"
    description: str = ""
    directly_observable: bool = False
    background: bool = False
    case_input: bool = False
    reflexive_allowed: bool = False
    non_reflexive: bool = False
    legal_output: bool | None = None
    output_category: str = ""
    factual_criteria_input: bool = False


@dataclass(frozen=True)
class RuleCall:
    name: str
    arity: int


def _strip_code_fences(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    return s


def _balanced_json_candidates(text: str) -> list[str]:
    s = text or ""
    out: list[str] = []
    n = len(s)
    i = 0
    while i < n:
        if s[i] != "{":
            i += 1
            continue
        start = i
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < n:
            ch = s[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(s[start : j + 1])
                        break
            j += 1
        i = start + 1
    return out


def parse_json_ir(raw_text: str) -> dict:
    s = _strip_code_fences(raw_text)
    candidates: list[str] = []
    start = s.find("{")
    end = s.rfind("}")
    if start >= 0 and end > start:
        candidates.append(s[start : end + 1])
    candidates.extend(_balanced_json_candidates(s))
    if not candidates:
        candidates = [s]

    seen = set()
    parse_attempts: list[str] = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        parse_attempts.append(c)
        parse_attempts.append(re.sub(r",(\s*[}\]])", r"\1", c))

    last_err: Exception | None = None
    for candidate in parse_attempts:
        try:
            obj = json.loads(candidate)
            if not isinstance(obj, dict):
                raise JSONIRCompilationError("JSON IR root must be an object.")
            return obj
        except json.JSONDecodeError as e:
            last_err = e
    if last_err is not None:
        raise JSONIRCompilationError("Invalid JSON IR output: " + str(last_err)) from last_err
    raise JSONIRCompilationError("Invalid JSON IR output: no parseable JSON object found")


def _coerce_identifier(value: str) -> str:
    if _IDENT_RE.match(value):
        return value
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_")
    if not cleaned:
        return value
    parts = [p for p in cleaned.split("_") if p]
    if not parts:
        return value
    coerced = parts[0][:1].upper() + parts[0][1:]
    for p in parts[1:]:
        coerced += p[:1].upper() + p[1:]
    if coerced and coerced[0].isdigit():
        coerced = "T" + coerced
    return coerced


def _require_ident(value: Any, ctx: str) -> str:
    if value is None:
        raise JSONIRCompilationError(ctx + " must be a valid identifier.")
    if not isinstance(value, str):
        value = str(value)
    coerced = _coerce_identifier(value.strip())
    if not _IDENT_RE.match(coerced):
        raise JSONIRCompilationError(ctx + " must be a valid identifier.")
    if coerced.startswith("_") and not coerced.startswith("__"):
        raise JSONIRCompilationError(
            ctx + f": placeholder identifier '{coerced}' is not allowed; "
            "use variables declared in the rule's forall."
        )
    return coerced


def _reject_malformed_expr_shape(raw: dict, idx: int, ctx: str) -> None:
    """Reject common LLM shapes that mix function terms with comparison operators."""
    keys = set(raw.keys())
    if "pred" in keys or "symbol" in keys or "and" in keys or "or" in keys or "not" in keys:
        return
    if "compare" in keys:
        return
    if "func" in keys or "function" in keys:
        if "op" in keys or "right" in keys or "left" in keys:
            raise JSONIRCompilationError(
                f"rules[{idx}].{ctx}: invalid expression — wrap comparisons as "
                '{"left": {"func": "F", "args": ["x"]}, "op": "=<", "right": 10} '
                'or {"compare": {"left": ..., "op": "=<", "right": ...}}; '
                "do not put func and op/right at the same object level."
            )


def _validate_type_name(type_name: Any) -> str:
    return _require_ident(type_name, "Type")


def _normalize_kind(value: Any) -> str:
    k = str(value or "").strip().lower()
    if k == "input":
        return "observable"
    if k == "conclusion":
        return "derived"
    if k in {"observable", "derived", "helper"}:
        return k
    return "helper"


def _validate_symbol_decl(raw: Any, ctx: str, *, default_returns: str) -> SymbolDecl:
    if isinstance(raw, str):
        return SymbolDecl(name=_require_ident(raw, ctx + ".name"), args=[], returns=default_returns)
    if not isinstance(raw, dict):
        raise JSONIRCompilationError(ctx + " must be an object or identifier string.")
    name = _require_ident(raw.get("name"), ctx + ".name")
    args = raw.get("args", [])
    returns_raw = raw.get("returns", default_returns)
    returns = _require_ident(returns_raw, ctx + ".returns")
    if not isinstance(args, list):
        raise JSONIRCompilationError(ctx + ".args must be a list.")
    parsed_args = [_require_ident(arg_t, f"{ctx}.args[{i}]") for i, arg_t in enumerate(args)]
    raw_dict = raw if isinstance(raw, dict) else {}
    lo_raw = raw_dict.get("legal_output")
    legal_output: bool | None = None
    if lo_raw is not None:
        legal_output = bool(lo_raw)
    output_category = str(raw_dict.get("output_category") or "").strip().lower()
    meta = raw_dict.get("metadata") if isinstance(raw_dict.get("metadata"), dict) else {}
    reflexive_allowed = bool(
        raw_dict.get("reflexive") is True
        or raw_dict.get("reflexive_allowed") is True
        or meta.get("reflexive") is True
        or meta.get("reflexive_allowed") is True
    )
    non_reflexive = bool(
        raw_dict.get("non_reflexive") is True
        or meta.get("non_reflexive") is True
    )
    factual_criteria_input = bool(
        raw_dict.get("factual_criteria_input") is True
        or (isinstance(meta, dict) and meta.get("factual_criteria_input") is True)
    )
    return SymbolDecl(
        name=name,
        args=parsed_args,
        returns=returns,
        kind=_normalize_kind(raw.get("kind")),
        description=str(raw.get("description") or "").strip(),
        directly_observable=symbol_directly_observable(raw_dict) or factual_criteria_input,
        background=symbol_background_or_case_input(raw_dict),
        case_input=bool(raw_dict.get("case_input") is True) or factual_criteria_input,
        reflexive_allowed=reflexive_allowed,
        non_reflexive=non_reflexive,
        legal_output=legal_output,
        output_category=output_category,
        factual_criteria_input=factual_criteria_input,
    )


def _symbol_kind_map(predicates: list[SymbolDecl], functions: list[SymbolDecl]) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in predicates:
        out[p.name] = p.kind
    for f in functions:
        out[f.name] = f.kind
    return out


def validate_json_ir_symbols(
    ir: dict,
    *,
    law_text_for_lints: str | None = None,
    scope_metadata: dict | None = None,
    question_text: str | None = None,
    following_missing_temporal_support_repair: bool = False,
) -> tuple[list[SymbolDecl], list[SymbolDecl], list[str]]:
    """Validate symbol-table design (no rules). Returns (predicates, functions, types)."""
    types_raw = ir.get("types")
    predicates_raw = ir.get("predicates", [])
    functions_raw = ir.get("functions", [])
    if not isinstance(types_raw, list):
        raise JSONIRCompilationError("types must be a list.")
    if not isinstance(predicates_raw, list):
        raise JSONIRCompilationError("predicates must be a list.")
    if not isinstance(functions_raw, list):
        raise JSONIRCompilationError("functions must be a list.")

    types: list[str] = []
    for t in types_raw:
        if isinstance(t, dict):
            t = t.get("name")
        types.append(_validate_type_name(t))
    if not types:
        raise JSONIRCompilationError("types cannot be empty.")
    if len(set(types)) != len(types):
        raise JSONIRCompilationError("Duplicate type declarations in JSON IR.")

    predicates = [
        _validate_symbol_decl(p, f"predicates[{i}]", default_returns="Bool")
        for i, p in enumerate(predicates_raw)
    ]
    functions = [
        _validate_symbol_decl(f, f"functions[{i}]", default_returns="Int")
        for i, f in enumerate(functions_raw)
    ]

    type_set = set(types) | _SCALAR_TYPES
    has_derived = False
    has_observable = False
    for decl in predicates + functions:
        if decl.kind in _DERIVED_OUTPUT_KINDS:
            has_derived = True
        if decl.kind in {"observable", "input"}:
            has_observable = True
        if decl.returns not in type_set:
            raise JSONIRCompilationError("Unknown return type in declaration: " + decl.name)
        for at in decl.args:
            if at not in type_set:
                raise JSONIRCompilationError("Unknown argument type in declaration: " + decl.name)

    for decl in predicates:
        if decl.returns != "Bool":
            raise JSONIRCompilationError("Predicate must return Bool: " + decl.name)

    if not has_derived:
        raise JSONIRCompilationError(
            SCHEMA_DESIGN_TAG
            + ": Symbol table contains no derived legal outputs. A reusable legal KB must expose "
            "at least one derived predicate/function representing legal classifications, consequences, "
            "rights, obligations, permissions, prohibitions, exceptions, sanctions, validity results, "
            "entitlements, or exclusions."
        )
    if not has_observable:
        raise JSONIRCompilationError(
            SCHEMA_DESIGN_TAG
            + ": Symbol table contains no observable case-input symbols. A reusable legal KB must "
            "include observable predicates/functions that can be populated from case descriptions."
        )

    seen_names: dict[str, tuple[tuple[str, ...], str]] = {}
    for decl in predicates + functions:
        sig = (tuple(decl.args), decl.returns)
        prev = seen_names.get(decl.name)
        if prev and prev != sig:
            raise JSONIRCompilationError(
                SCHEMA_DESIGN_TAG + ": Conflicting signatures for symbol: " + decl.name
            )
        seen_names[decl.name] = sig

    type_descriptions: dict[str, str] = {}
    for t in types_raw:
        if isinstance(t, dict) and t.get("name"):
            type_descriptions[str(t["name"])] = str(t.get("description") or "").strip()

    from pipeline.kb.status_as_type import validate_status_as_type_symbols

    validate_status_as_type_symbols(
        types, predicates, type_descriptions=type_descriptions
    )

    if scope_metadata is not None or (law_text_for_lints or "").strip():
        from pipeline.kb.legal_effect import validate_legal_effect_symbols_stage

        validate_legal_effect_symbols_stage(
            predicates,
            law_text_for_lints=law_text_for_lints,
            scope_metadata=scope_metadata,
        )
        from pipeline.kb.temporal_support import validate_temporal_support_symbols_stage

        validate_temporal_support_symbols_stage(
            predicates,
            functions,
            types,
            law_text_for_lints=law_text_for_lints,
            scope_metadata=scope_metadata,
            question_text=question_text,
            following_missing_temporal_support_repair=following_missing_temporal_support_repair,
        )

    return predicates, functions, types


def _collect_pred_atom_names(expr: Any, sink: set[str]) -> None:
    if isinstance(expr, list):
        for x in expr:
            _collect_pred_atom_names(x, sink)
        return
    if not isinstance(expr, dict):
        return
    if "pred" in expr or "symbol" in expr:
        n = str(expr.get("pred") or expr.get("symbol") or "").strip()
        if n:
            sink.add(n)
        return
    if "not" in expr:
        _collect_pred_atom_names(expr.get("not"), sink)
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            _collect_pred_atom_names(x, sink)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            _collect_pred_atom_names(x, sink)
        return


def _collect_func_term_names(expr: Any, sink: set[str]) -> None:
    if isinstance(expr, list):
        for x in expr:
            _collect_func_term_names(x, sink)
        return
    if not isinstance(expr, dict):
        return
    if "func" in expr or "function" in expr:
        n = str(expr.get("func") or expr.get("function") or "").strip()
        if n:
            sink.add(n)
        for a in expr.get("args") or []:
            _collect_func_term_names(a, sink)
        return
    if "pred" in expr or "symbol" in expr:
        for a in expr.get("args") or []:
            _collect_func_term_names(a, sink)
        return
    if "not" in expr:
        _collect_func_term_names(expr.get("not"), sink)
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            _collect_func_term_names(x, sink)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            _collect_func_term_names(x, sink)
        return
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        _collect_func_term_names(comp.get("left"), sink)
        _collect_func_term_names(comp.get("right"), sink)


def _validate_object_rule_schema_design(
    raw_rule: dict,
    idx: int,
    pred_kinds: dict[str, str],
    pred_names: set[str],
    fun_names: set[str],
) -> None:
    """Schema-level checks before argument type inference."""
    if not isinstance(raw_rule, dict):
        return

    then_atoms: set[str] = set()
    if_atoms: set[str] = set()
    if "formula" in raw_rule:
        _collect_pred_atom_names(raw_rule.get("formula"), then_atoms)
        if_atoms = set(then_atoms)
    else:
        _collect_pred_atom_names(raw_rule.get("if", []), if_atoms)
        _collect_pred_atom_names(raw_rule.get("then", []), then_atoms)

    for name in sorted(then_atoms):
        kind = pred_kinds.get(name, "unknown")
        if kind == "observable":
            raise JSONIRCompilationError(
                SCHEMA_DESIGN_TAG
                + f": rules[{idx}].then: observable predicate '{name}' is used as a rule consequent. "
                "Observable predicates are case-input facts and should normally not be derived by legal rules. "
                "Use a derived predicate for the legal consequence, or repair the symbol table if no derived "
                "predicate exists."
            )

    pred_atoms_in_rule: set[str] = set()
    for key in ("if", "then", "formula"):
        if key in raw_rule:
            _collect_pred_atom_names(raw_rule.get(key), pred_atoms_in_rule)
    for name in sorted(pred_atoms_in_rule):
        if name in fun_names and name not in pred_names:
            raise JSONIRCompilationError(
                SCHEMA_DESIGN_TAG
                + f": rules[{idx}] uses function '{name}' as a Boolean predicate atom. "
                "If this concept is yes/no, declare it as a predicate with returns Bool. "
                "If it returns a value, use it only as a function term inside a comparison."
            )

    func_term_names: set[str] = set()

    def _collect_func_heads(expr: Any) -> None:
        if isinstance(expr, list):
            for x in expr:
                _collect_func_heads(x)
            return
        if not isinstance(expr, dict):
            return
        if "func" in expr or "function" in expr:
            n = str(expr.get("func") or expr.get("function") or "").strip()
            if n:
                func_term_names.add(n)
            for a in expr.get("args") or []:
                _collect_func_heads(a)
            return
        if "pred" in expr or "symbol" in expr:
            for a in expr.get("args") or []:
                _collect_func_heads(a)
            return
        if "not" in expr:
            _collect_func_heads(expr.get("not"))
            return
        if "and" in expr:
            for x in expr.get("and") or []:
                _collect_func_heads(x)
            return
        if "or" in expr:
            for x in expr.get("or") or []:
                _collect_func_heads(x)
            return
        comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
        if isinstance(comp, dict):
            _collect_func_heads(comp.get("left"))
            _collect_func_heads(comp.get("right"))

    for key in ("if", "then", "formula"):
        if key in raw_rule:
            _collect_func_heads(raw_rule.get(key))
    for name in sorted(func_term_names):
        if name in pred_names and name not in fun_names:
            raise JSONIRCompilationError(
                SCHEMA_DESIGN_TAG
                + f": rules[{idx}] uses predicate '{name}' as a function term. "
                "Predicates are Boolean atoms used as P(args) or negated P(args) in IF/THEN. "
                "Functions are value terms inside compare left/right only. "
                "Do not write C(args) = false. Repair layer: rules."
            )

    shared_derived = {
        p
        for p in if_atoms & then_atoms
        if pred_kinds.get(p) in _DERIVED_OUTPUT_KINDS
    }
    if shared_derived:
        has_bridge = any(pred_kinds.get(p) in _INPUT_BRIDGE_KINDS for p in if_atoms)
        if not has_bridge:
            raise JSONIRCompilationError(
                RULE_DESIGN_TAG
                + f": rules[{idx}] appears circular; derived predicate(s) "
                + ", ".join(sorted(shared_derived))
                + " depend only on themselves or other derived predicates without observable/helper conditions."
            )


def _rule_quant_env(raw_rule: dict, idx: int) -> dict[str, str]:
    env: dict[str, str] = {}
    q_raw = raw_rule.get("forall", [])
    if isinstance(q_raw, list):
        for q in q_raw:
            try:
                v, t = _normalize_quant_entry(q, idx)
                env[v] = t
            except JSONIRCompilationError:
                continue
    return env


def _vars_in_term(raw: Any, quant_env: dict[str, str]) -> set[str]:
    if isinstance(raw, str):
        s = raw.strip()
        if s in quant_env:
            return {s}
        return set()
    if isinstance(raw, dict) and ("func" in raw or "function" in raw):
        out: set[str] = set()
        for a in raw.get("args") or []:
            out |= _vars_in_term(a, quant_env)
        return out
    return set()


def _collect_vars_in_rule_expr(expr: Any, quant_env: dict[str, str]) -> set[str]:
    """Quantified variables referenced anywhere in a rule expression (predicates, compares, functions)."""
    if isinstance(expr, list):
        out: set[str] = set()
        for x in expr:
            out |= _collect_vars_in_rule_expr(x, quant_env)
        return out
    if not isinstance(expr, dict):
        return set()
    out: set[str] = set()
    if "pred" in expr or "symbol" in expr:
        for a in expr.get("args") or []:
            out |= _vars_in_term(a, quant_env)
    if "not" in expr:
        out |= _collect_vars_in_rule_expr(expr.get("not"), quant_env)
    if "and" in expr:
        for x in expr.get("and") or []:
            out |= _collect_vars_in_rule_expr(x, quant_env)
    if "or" in expr:
        for x in expr.get("or") or []:
            out |= _collect_vars_in_rule_expr(x, quant_env)
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        for side in (comp.get("left"), comp.get("right")):
            out |= _vars_in_term(side, quant_env)
    return out


def _iter_pred_atom_usages_in_expr(
    expr: Any,
    *,
    rule_index: int,
    side: str,
    negated: bool = False,
) -> Any:
    """Yield PredAtomUsage for predicate atoms under optional classical negation."""
    if isinstance(expr, list):
        for x in expr:
            yield from _iter_pred_atom_usages_in_expr(
                x, rule_index=rule_index, side=side, negated=negated
            )
        return
    if not isinstance(expr, dict):
        return
    if "pred" in expr or "symbol" in expr:
        pn = str(expr.get("pred") or expr.get("symbol") or "").strip()
        if pn:
            atom_neg = bool(expr.get("neg") or expr.get("negated", False))
            yield PredAtomUsage(
                name=pn,
                negated=negated or atom_neg,
                rule_index=rule_index,
                side=side,
            )
        return
    if "not" in expr:
        inner = expr.get("not")
        yield from _iter_pred_atom_usages_in_expr(
            inner, rule_index=rule_index, side=side, negated=True
        )
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            yield from _iter_pred_atom_usages_in_expr(
                x, rule_index=rule_index, side=side, negated=negated
            )
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            yield from _iter_pred_atom_usages_in_expr(
                x, rule_index=rule_index, side=side, negated=negated
            )
        return
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        for part in (comp.get("left"), comp.get("right")):
            yield from _iter_pred_atom_usages_in_expr(
                part, rule_index=rule_index, side=side, negated=negated
            )


def _collect_pred_atom_usages(rules: list) -> list[PredAtomUsage]:
    out: list[PredAtomUsage] = []
    for idx, raw_rule in enumerate(rules or []):
        if not isinstance(raw_rule, dict):
            continue
        if_side, then_side = _rule_expr_sides(raw_rule)
        for u in _iter_pred_atom_usages_in_expr(if_side, rule_index=idx, side="if"):
            out.append(u)
        for u in _iter_pred_atom_usages_in_expr(then_side, rule_index=idx, side="then"):
            out.append(u)
    return out


def _predicates_defined_in_then(rules: list) -> set[str]:
    defined: set[str] = set()
    for u in _collect_pred_atom_usages(rules):
        if u.side == "then":
            defined.add(u.name)
    return defined


def _iter_pred_atoms_with_args(expr: Any):
    if isinstance(expr, list):
        for x in expr:
            yield from _iter_pred_atoms_with_args(x)
        return
    if not isinstance(expr, dict):
        return
    if "pred" in expr or "symbol" in expr:
        yield expr
        return
    if "not" in expr:
        yield from _iter_pred_atoms_with_args(expr.get("not"))
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            yield from _iter_pred_atoms_with_args(x)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            yield from _iter_pred_atoms_with_args(x)
        return
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        for side in (comp.get("left"), comp.get("right")):
            yield from _iter_pred_atoms_with_args(side)


def _iter_function_refs(expr: Any):
    """Yield (function_name, side_dict) for func atoms inside comparisons and nested logic."""
    if isinstance(expr, list):
        for x in expr:
            yield from _iter_function_refs(x)
        return
    if not isinstance(expr, dict):
        return
    if "func" in expr or "function" in expr:
        fn = str(expr.get("func") or expr.get("function") or "").strip()
        if fn:
            yield fn
        return
    if "not" in expr:
        yield from _iter_function_refs(expr.get("not"))
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            yield from _iter_function_refs(x)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            yield from _iter_function_refs(x)
        return
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        for side in (comp.get("left"), comp.get("right")):
            yield from _iter_function_refs(side)


def _rule_expr_sides(raw_rule: dict) -> tuple[Any, Any]:
    if_side = raw_rule.get("if", [])
    then_side = raw_rule.get("then", []) if "then" in raw_rule else raw_rule.get("formula")
    return if_side, then_side


def _collect_helper_symbol_usage(
    rules: list,
    pred_kinds: dict[str, str],
    fun_kinds: dict[str, str],
) -> tuple[set[str], set[str], set[str], set[str]]:
    """Return (helpers_in_if_preds, helpers_in_if_funs, helpers_defined_then_preds, helpers_defined_then_funs)."""
    in_if_p: set[str] = set()
    in_if_f: set[str] = set()
    def_then_p: set[str] = set()
    def_then_f: set[str] = set()

    def _note_pred(name: str, *, in_if: bool, in_then: bool) -> None:
        if pred_kinds.get(name) != "helper":
            return
        if in_if:
            in_if_p.add(name)
        if in_then:
            def_then_p.add(name)

    def _note_fun(name: str, *, in_if: bool, in_then: bool) -> None:
        if fun_kinds.get(name) != "helper":
            return
        if in_if:
            in_if_f.add(name)
        if in_then:
            def_then_f.add(name)

    for raw_rule in rules or []:
        if not isinstance(raw_rule, dict):
            continue
        if_side, then_side = _rule_expr_sides(raw_rule)
        for atom in _iter_pred_atoms_with_args(if_side):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if pn:
                _note_pred(pn, in_if=True, in_then=False)
        for fn in _iter_function_refs(if_side):
            _note_fun(fn, in_if=True, in_then=False)
        for atom in _iter_pred_atoms_with_args(then_side):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if pn:
                _note_pred(pn, in_if=False, in_then=True)
    defined_f, _ = _helper_functions_defined_in_then(rules, fun_kinds)
    def_then_f.update(defined_f)

    return in_if_p, in_if_f, def_then_p, def_then_f


def _normalize_compare_op(op: Any) -> str:
    return str(op or "").strip().lower().replace("==", "=")


def _function_name_from_term(side: Any) -> str | None:
    if isinstance(side, dict) and ("func" in side or "function" in side):
        return str(side.get("func") or side.get("function") or "").strip() or None
    return None


def _is_numeric_literal_term(side: Any) -> bool:
    if isinstance(side, bool):
        return False
    if isinstance(side, (int, float)):
        return True
    if isinstance(side, str):
        from pipeline.kb.law_numeric_literals import parse_numeric_token

        return parse_numeric_token(side) is not None
    return False


def _iter_rule_compare_nodes(expr: Any):
    """Yield compare dict nodes under expr (shared shape with numeric_threshold_provenance)."""
    if isinstance(expr, list):
        for x in expr:
            yield from _iter_rule_compare_nodes(x)
        return
    if not isinstance(expr, dict):
        return
    if "pred" in expr or "symbol" in expr:
        return
    if "not" in expr:
        yield from _iter_rule_compare_nodes(expr.get("not"))
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            yield from _iter_rule_compare_nodes(x)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            yield from _iter_rule_compare_nodes(x)
        return
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        yield comp


def _helper_functions_defined_in_then(
    rules: list,
    fun_kinds: dict[str, str],
) -> tuple[set[str], dict[str, list[int]]]:
    """
    Helper function F is defined when THEN contains compare(F(...), =, literal) or compare(literal, =, F(...)).
    """
    defined: set[str] = set()
    by_rule: dict[str, list[int]] = {}
    for idx, raw_rule in enumerate(rules or []):
        if not isinstance(raw_rule, dict):
            continue
        _, then_side = _rule_expr_sides(raw_rule)
        for comp in _iter_rule_compare_nodes(then_side):
            if _normalize_compare_op(comp.get("op")) != "=":
                continue
            left, right = comp.get("left"), comp.get("right")
            for fn_side, lit_side in ((left, right), (right, left)):
                fn = _function_name_from_term(fn_side)
                if not fn or fun_kinds.get(fn) != "helper":
                    continue
                if not _is_numeric_literal_term(lit_side):
                    continue
                defined.add(fn)
                by_rule.setdefault(fn, []).append(idx)
    return defined, by_rule


def _decl_by_name(
    predicates: list[SymbolDecl],
    functions: list[SymbolDecl],
) -> dict[str, SymbolDecl]:
    out: dict[str, SymbolDecl] = {}
    for decl in predicates + functions:
        out[decl.name] = decl
    return out


def _validate_floating_helpers(
    ir: dict,
    pred_kinds: dict[str, str],
    fun_kinds: dict[str, str],
    *,
    predicates: list[SymbolDecl] | None = None,
    functions: list[SymbolDecl] | None = None,
) -> None:
    """Reject helpers used in IF that are never defined in any rule THEN."""
    from pipeline.kb.temporal_support import temporal_support_exempt_from_helper_definition

    rules = ir.get("rules") or []
    in_if_p, in_if_f, def_then_p, def_then_f = _collect_helper_symbol_usage(rules, pred_kinds, fun_kinds)
    by_name = _decl_by_name(predicates or [], functions or [])
    from pipeline.kb.factual_criteria import decl_exempt_from_computed_observable_checks

    floating_p = {
        n
        for n in (in_if_p - def_then_p)
        if not (by_name.get(n) and temporal_support_exempt_from_helper_definition(by_name[n]))
        and not (by_name.get(n) and decl_exempt_from_computed_observable_checks(by_name[n]))
    }
    floating_f = {
        n
        for n in (in_if_f - def_then_f)
        if not (by_name.get(n) and temporal_support_exempt_from_helper_definition(by_name[n]))
    }
    for name in sorted(floating_p):
        raise JSONIRCompilationError(
            RULE_DESIGN_TAG
            + f": Helper predicate '{name}' is used as a rule condition but has no defining rule "
            "(never appears in any rule THEN). Define it with rules from observable facts/functions "
            "(e.g. numeric comparisons), or reclassify as observable with directly_observable=true only "
            "if a case may state this composite fact verbatim. Do not delete the negated condition or "
            "rename the predicate without fixing the definition."
        )
    for name in sorted(floating_f):
        raise JSONIRCompilationError(
            RULE_DESIGN_TAG
            + f": Helper function '{name}' is used as a rule condition but has no defining rule. "
            "Define it in THEN with a numeric equality compare, e.g. "
            '{"compare": {"left": {"func": "%s", "args": ["c", "fy"]}, "op": "=", "right": LAW_LITERAL}} '
            "using a threshold literal from scoped law text. Do not use the function as a Bool predicate atom. "
            "Do not define case-value observables (e.g. annual_average_employees_fte) from law thresholds."
            % name
        )


def _validate_observable_composite_symbol_declarations(predicates: list[SymbolDecl]) -> None:
    """Reject computed-looking observables unless explicitly marked case-direct."""
    from pipeline.kb.factual_criteria import decl_exempt_from_computed_observable_checks

    for decl in predicates:
        if decl.kind != "observable":
            continue
        if decl.directly_observable:
            continue
        if decl.background or decl.case_input:
            continue
        if decl_exempt_from_computed_observable_checks(decl):
            continue
        if looks_computed_composite(decl.name, decl.description):
            raise JSONIRCompilationError(
                SCHEMA_DESIGN_TAG
                + f": Predicate '{decl.name}' (kind=observable) looks computed/composite "
                "(threshold, count, exceeds/meets/satisfies-style condition). "
                "Reclassify as kind=helper or derived and define it with rules from numeric functions "
                "or comparisons, or set directly_observable=true only when case texts may directly state "
                "this composite fact. Repair layer: symbols."
            )


def _validate_composite_predicate_rule_safety(
    ir: dict,
    predicates: list[SymbolDecl],
    pred_kinds: dict[str, str],
) -> None:
    """
    Block undefined computed/helper predicates—especially under negation—from proving legal conclusions.
    """
    rules = ir.get("rules") or []
    decl_by_name = {p.name: p for p in predicates}
    defined_then = _predicates_defined_in_then(rules)
    usages = _collect_pred_atom_usages(rules)
    from pipeline.kb.factual_criteria import decl_exempt_from_computed_observable_checks

    for u in usages:
        decl = decl_by_name.get(u.name)
        if not decl:
            continue
        kind = pred_kinds.get(u.name, decl.kind)
        computed = looks_computed_composite(decl.name, decl.description)
        defined = u.name in defined_then

        if decl_exempt_from_computed_observable_checks(decl):
            continue

        if kind == "observable" and computed and not decl.directly_observable:
            if u.side == "if" and not defined:
                neg_phrase = "negated " if u.negated else ""
                raise JSONIRCompilationError(
                    SCHEMA_DESIGN_TAG
                    + f": Computed-looking observable predicate '{u.name}' is used {neg_phrase}"
                    f"in rules[{u.rule_index}].if without any defining rule. "
                    "Under closed-world reasoning, an undefined atom is false, so negation can "
                    "spuriously entail legal conclusions. Repair: reclassify as helper/derived and add "
                    "defining rules from numeric functions/comparisons, or set directly_observable=true "
                    "only if cases may directly state this composite fact. Do not rename the predicate "
                    "or delete the negated condition. Repair layer: symbols."
                )

        if kind == "helper" and u.side == "if" and not defined:
            from pipeline.kb.temporal_support import temporal_support_exempt_from_helper_definition

            if temporal_support_exempt_from_helper_definition(decl):
                continue
            if decl_exempt_from_computed_observable_checks(decl):
                continue
            neg_phrase = "negated " if u.negated else ""
            raise JSONIRCompilationError(
                RULE_DESIGN_TAG
                + f": Helper predicate '{u.name}' is used {neg_phrase}in rules[{u.rule_index}].if "
                "but has no defining rule (never in any rule THEN). Add rules that define it from "
                "observable facts/functions, or use direct numeric comparisons in the legal rule. "
                "Do not rely on absence of an undefined helper to prove a negated condition. "
                "Repair layer: rules."
            )

        if kind in _DERIVED_OUTPUT_KINDS and u.side == "if" and u.negated and not defined:
            raise JSONIRCompilationError(
                RULE_DESIGN_TAG
                + f": Derived predicate '{u.name}' is negated in rules[{u.rule_index}].if without "
                "a defining rule. Derived symbols must be defined in rule THEN clauses, not assumed "
                "false when absent. Repair layer: rules."
            )


def _if_has_observable_bridge(expr: Any, pred_kinds: dict[str, str], fun_kinds: dict[str, str]) -> bool:
    if isinstance(expr, list):
        return any(_if_has_observable_bridge(x, pred_kinds, fun_kinds) for x in expr)
    if not isinstance(expr, dict):
        return False
    if "pred" in expr or "symbol" in expr:
        n = str(expr.get("pred") or expr.get("symbol") or "").strip()
        return pred_kinds.get(n) in _INPUT_BRIDGE_KINDS
    if "not" in expr:
        return _if_has_observable_bridge(expr.get("not"), pred_kinds, fun_kinds)
    if "and" in expr:
        return any(_if_has_observable_bridge(x, pred_kinds, fun_kinds) for x in (expr.get("and") or []))
    if "or" in expr:
        return any(_if_has_observable_bridge(x, pred_kinds, fun_kinds) for x in (expr.get("or") or []))
    comp = expr.get("compare") if "compare" in expr else expr if {"left", "op", "right"}.issubset(expr.keys()) else None
    if isinstance(comp, dict):
        for side in (comp.get("left"), comp.get("right")):
            if isinstance(side, dict) and ("func" in side or "function" in side):
                fn = str(side.get("func") or side.get("function") or "").strip()
                if fun_kinds.get(fn) in {"observable", "input", "helper", "unknown"}:
                    return True
    return False


def _validate_unary_role_conflation(
    raw_rule: dict,
    idx: int,
    pred_descriptions: dict[str, str],
) -> None:
    """Reject one rule variable carrying incompatible unary subject roles (e.g. deceased vs surviving)."""
    from pipeline.kb.role_hints import role_hints_conflict, unary_subject_role_hints
    from pipeline.semantic.legal_question import witness_modeling_hint

    if not isinstance(raw_rule, dict):
        return
    quant_env = _rule_quant_env(raw_rule, idx)
    if not quant_env:
        return

    var_hints: dict[str, set[str]] = {v: set() for v in quant_env}

    def _note_unary_calls(expr: Any) -> None:
        for atom in _iter_pred_atoms_with_args(expr):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if not pn:
                continue
            args = atom.get("args") or []
            if len(args) != 1:
                continue
            arg = args[0]
            if isinstance(arg, str) and arg in quant_env:
                for hint in unary_subject_role_hints(pn, pred_descriptions.get(pn, "")):
                    var_hints[arg].add(hint)

    for key in ("if", "then", "formula"):
        if key in raw_rule:
            _note_unary_calls(raw_rule.get(key))

    for var, hints in sorted(var_hints.items()):
        frozen = frozenset(hints)
        if role_hints_conflict(frozen):
            raise JSONIRCompilationError(
                RULE_DESIGN_TAG
                + f": rules[{idx}] variable '{var}' combines incompatible unary subject roles "
                f"({', '.join(sorted(hints))}). Observables about different lifecycle roles must use "
                "separate quantified variables linked by a binary relation (e.g. status_of(subject, other)), "
                "not a single shared variable."
                + witness_modeling_hint()
            )


def _validate_object_rule_role_binding(
    raw_rule: dict,
    idx: int,
    pred_kinds: dict[str, str],
    pred_descriptions: dict[str, str],
    fun_kinds: dict[str, str] | None = None,
    pred_meta: dict[str, SymbolDecl] | None = None,
) -> None:
    from pipeline.kb.self_relation_validation import (
        is_suspicious_self_relation,
        self_relation_error_message,
    )
    from pipeline.semantic.legal_question import witness_modeling_hint

    if not isinstance(raw_rule, dict):
        return
    _validate_unary_role_conflation(raw_rule, idx, pred_descriptions)
    quant_env = _rule_quant_env(raw_rule, idx)
    if_side = raw_rule.get("if", [])
    then_side = raw_rule.get("then", []) if "then" in raw_rule else raw_rule.get("formula")
    vars_if: set[str] = set()
    for key in ("if", "formula"):
        if key in raw_rule:
            vars_if |= _collect_vars_in_rule_expr(raw_rule.get(key), quant_env)
            if key == "formula":
                break

    then_derived_atoms: list[tuple[str, list]] = []
    for atom in _iter_pred_atoms_with_args(then_side):
        pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
        if pred_kinds.get(pn) in _DERIVED_OUTPUT_KINDS:
            then_derived_atoms.append((pn, list(atom.get("args") or [])))

    for pn, args in then_derived_atoms:
        for arg in args:
            if isinstance(arg, str) and arg in quant_env and arg not in vars_if:
                raise JSONIRCompilationError(
                    RULE_DESIGN_TAG
                    + f": rules[{idx}] has unconstrained consequent variable '{arg}' in derived predicate '{pn}'. "
                    "Variables in legal conclusions should be grounded by observable/helper conditions in the rule "
                    "antecedent. Add an if-condition linking '{arg}' to the legal subject, or remove '{arg}' from "
                    "the derived predicate signature if it is not legally relevant.".format(arg=arg, pn=pn)
                    + witness_modeling_hint()
                )

    fk = fun_kinds or {}
    then_has_derived = bool(then_derived_atoms)
    if then_has_derived and not _if_has_observable_bridge(if_side, pred_kinds, fk):
        if_atoms_only_derived = True
        for atom in _iter_pred_atoms_with_args(if_side):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if pred_kinds.get(pn) not in _DERIVED_OUTPUT_KINDS:
                if_atoms_only_derived = False
                break
        if if_atoms_only_derived:
            names = ", ".join(p for p, _ in then_derived_atoms)
            raise JSONIRCompilationError(
                RULE_DESIGN_TAG
                + f": rules[{idx}] derived legal conclusion(s) ({names}) are not grounded in observable or helper "
                "conditions. Legal conclusions should ultimately depend on case-input facts/values."
                + witness_modeling_hint()
            )

    for key in ("if", "then", "formula"):
        if key not in raw_rule:
            continue
        for atom in _iter_pred_atoms_with_args(raw_rule.get(key)):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            args = atom.get("args") or []
            if len(args) == 2 and isinstance(args[0], str) and isinstance(args[1], str):
                if args[0].strip() == args[1].strip() and args[0].strip() in quant_env:
                    desc = pred_descriptions.get(pn, "")
                    meta = (pred_meta or {}).get(pn)
                    if is_suspicious_self_relation(
                        pn,
                        args[0].strip(),
                        args[1].strip(),
                        description=desc,
                        reflexive_allowed=bool(meta.reflexive_allowed) if meta else False,
                        non_reflexive=bool(meta.non_reflexive) if meta else False,
                    ):
                        raise JSONIRCompilationError(
                            RULE_DESIGN_TAG
                            + ": "
                            + self_relation_error_message(
                                rule_index=idx,
                                pred_name=pn,
                                var_name=args[0].strip(),
                            )
                            + witness_modeling_hint()
                        )


def _derived_predicates_defined_in_rules(rules: list, pred_kinds: dict[str, str]) -> set[str]:
    defined: set[str] = set()
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        then_side = rule.get("then", []) if "then" in rule else rule.get("formula")
        for atom in _iter_pred_atoms_with_args(then_side):
            pn = str(atom.get("pred") or atom.get("symbol") or "").strip()
            if pred_kinds.get(pn) in _DERIVED_OUTPUT_KINDS:
                defined.add(pn)
    return defined


def _validate_derived_predicates_have_defining_rules(
    ir: dict,
    pred_kinds: dict[str, str],
) -> None:
    derived_names = {n for n, k in pred_kinds.items() if k in _DERIVED_OUTPUT_KINDS}
    if not derived_names:
        return
    defined = _derived_predicates_defined_in_rules(ir.get("rules") or [], pred_kinds)
    missing = sorted(derived_names - defined)
    if missing:
        raise JSONIRCompilationError(
            SCHEMA_DESIGN_TAG
            + ": derived predicate(s) "
            + ", ".join(missing)
            + " never appear in any rule THEN. Every derived legal-output symbol must be "
            "defined by at least one rule."
        )


def validate_combined_json_ir_schema(
    ir: dict,
    predicates: list[SymbolDecl],
    functions: list[SymbolDecl],
    *,
    law_text_for_lints: str | None = None,
    scope_metadata: dict | None = None,
) -> None:
    """Run symbol + rule schema checks before FO rendering."""
    pred_kinds = _symbol_kind_map(predicates, functions)
    pred_names = {p.name for p in predicates}
    fun_names = {f.name for f in functions}
    pred_descriptions = {p.name: p.description for p in predicates}
    pred_meta = {p.name: p for p in predicates}
    fun_kinds = {f.name: f.kind for f in functions}
    preflight_json_ir_rule_predicates(ir)
    _validate_observable_composite_symbol_declarations(predicates)
    _validate_floating_helpers(
        ir, pred_kinds, fun_kinds, predicates=predicates, functions=functions
    )
    _validate_composite_predicate_rule_safety(ir, predicates, pred_kinds)
    from pipeline.kb.threshold_cardinality import validate_threshold_cardinality_rules

    validate_threshold_cardinality_rules(ir, pred_kinds, law_text_for_lints)
    from pipeline.kb.threshold_classification_negative import (
        validate_threshold_classification_negative_support,
    )

    validate_threshold_classification_negative_support(
        ir, pred_kinds, law_text_for_lints=law_text_for_lints
    )
    from pipeline.kb.numeric_threshold_provenance import (
        validate_numeric_threshold_literals_in_rules,
    )

    validate_numeric_threshold_literals_in_rules(
        ir, law_text_for_lints=law_text_for_lints
    )
    from pipeline.kb.legal_effect import validate_legal_effect_output_presence

    validate_legal_effect_output_presence(
        predicates,
        law_text_for_lints=law_text_for_lints,
        scope_metadata=scope_metadata,
    )
    from pipeline.kb.status_as_type import validate_status_as_type_rules

    validate_status_as_type_rules(ir.get("rules") or [], pred_kinds=pred_kinds)
    _validate_derived_predicates_have_defining_rules(ir, pred_kinds)
    for i, rule in enumerate(ir.get("rules") or []):
        if isinstance(rule, dict):
            _validate_object_rule_schema_design(rule, i, pred_kinds, pred_names, fun_names)
            _validate_object_rule_role_binding(
                rule, i, pred_kinds, pred_descriptions, fun_kinds, pred_meta=pred_meta
            )


def compile_validate_json_ir(
    ir: dict,
    *,
    law_text_for_lints: str | None = None,
    scope_metadata: dict | None = None,
) -> dict:
    """Validate symbols + combined schema, then normalize to FO-ready IR."""
    predicates, functions, types = validate_json_ir_symbols(
        ir,
        law_text_for_lints=law_text_for_lints,
        scope_metadata=scope_metadata,
    )
    merged = {
        "types": types,
        "predicates": [_symbol_to_json(d) for d in predicates],
        "functions": [_symbol_to_json(d) for d in functions],
        "rules": ir.get("rules") or [],
    }
    from pipeline.kb.numeric_compare_normalize import normalize_json_ir_rule_compare_sorts

    normalize_json_ir_rule_compare_sorts(merged, predicates, functions)
    validate_combined_json_ir_schema(
        merged,
        predicates,
        functions,
        law_text_for_lints=law_text_for_lints,
        scope_metadata=scope_metadata,
    )
    return normalize_json_ir(merged)


def _normalize_with_quarantine(
    ir: dict,
    *,
    law_text_for_lints: str | None = None,
    scope_metadata: dict | None = None,
) -> tuple[dict, list[str]]:
    """Drop invalid object rules one-by-one when JSON_IR_ALLOW_PARTIAL_KB is enabled."""
    warnings: list[str] = []
    rules = list(ir.get("rules") or [])
    if not rules:
        return compile_validate_json_ir(
            ir, law_text_for_lints=law_text_for_lints, scope_metadata=scope_metadata
        ), warnings

    last_err: JSONIRCompilationError | None = None
    for drop_round in range(len(rules) + 1):
        try:
            return compile_validate_json_ir(
                ir, law_text_for_lints=law_text_for_lints, scope_metadata=scope_metadata
            ), warnings
        except JSONIRCompilationError as e:
            last_err = e
            m = _RE_RULE_IDX.search(str(e))
            drop_idx = int(m.group(1)) if m else None
            if drop_idx is None:
                drop_idx = next(
                    (i for i, r in enumerate(rules) if isinstance(r, dict)),
                    None,
                )
            if drop_idx is None or drop_idx >= len(rules):
                break
            dropped = rules.pop(drop_idx)
            ir = {**ir, "rules": list(rules)}
            warnings.append(
                "Dropped invalid rule %d after repeated validation failure: %s"
                % (drop_idx, str(e)[:500])
            )
            try:
                warnings.append("Dropped rule body: " + json.dumps(dropped, ensure_ascii=False)[:800])
            except (TypeError, ValueError):
                pass
    if last_err:
        raise last_err
    raise JSONIRCompilationError("JSON IR validation failed with partial KB enabled.")


def _count_args(arg_blob: str) -> int:
    s = (arg_blob or "").strip()
    if not s:
        return 0
    return len([a for a in s.split(",") if a.strip()])


def _rule_calls(rule: str) -> list[RuleCall]:
    out: list[RuleCall] = []
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)", rule):
        # Ignore quantifier-like/functionless builtins only if needed later.
        out.append(RuleCall(name=m.group(1), arity=_count_args(m.group(2))))
    return out


def _canon_symbol(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _build_rewrite_map(declared_names: set[str], calls: list[RuleCall]) -> dict[str, str]:
    out: dict[str, str] = {}
    canon_to_decl: dict[str, list[str]] = {}
    for dn in declared_names:
        canon_to_decl.setdefault(_canon_symbol(dn), []).append(dn)
    for c in calls:
        if c.name in declared_names or c.name in out:
            continue
        canon = _canon_symbol(c.name)
        direct = canon_to_decl.get(canon, [])
        if len(direct) == 1:
            out[c.name] = direct[0]
            continue
        close = get_close_matches(canon, list(canon_to_decl.keys()), n=1, cutoff=0.86)
        if close:
            candidates = canon_to_decl.get(close[0], [])
            if len(candidates) == 1:
                out[c.name] = candidates[0]
    return out


def _rewrite_rule_symbols(rule: str, rewrites: dict[str, str]) -> str:
    if not rewrites:
        return rule

    def repl(m: re.Match) -> str:
        name = m.group(1)
        args = m.group(2)
        return rewrites.get(name, name) + "(" + args + ")"

    return re.sub(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)", repl, rule)


def _normalize_rule_text(rule: str) -> str:
    s = (rule or "").strip()
    if not s:
        return s
    s = s.replace("&&", " & ")
    s = s.replace("||", " | ")
    s = s.replace("!=", " ~= ")
    s = s.replace("->>", " => ")
    s = s.replace("==>", " => ")
    s = re.sub(r"[-–—]\s*\*+\s*>", " => ", s)
    s = re.sub(r"(?<![<>=!])<=(?!>)", "=<", s)
    s = re.sub(r"!\s*([A-Za-z_]\w*\s*\()", r"~\1", s)
    s = re.sub(r"\bexists\s+([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*:", r"? \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r"\bforall\s+([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*:", r"! \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r"\bexists\s*\(\s*([A-Za-z_]\w*)\s*\*\s*in\s+([A-Za-z_]\w*)\s*:", r"? \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r"\bforall\s*\(\s*([A-Za-z_]\w*)\s*\*\s*in\s+([A-Za-z_]\w*)\s*:", r"! \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r",\s*\*\s*([!?])", r", \1", s)
    s = re.sub(r"\(\s*\*\s*([!?])", r"(\1", s)
    s = re.sub(r"\s\*\s*([!?])", r" \1", s)
    s = re.sub(r"([!?]\s*[A-Za-z_]\w*\s+in\s+[A-Za-z_]\w*)\s*\*", r"\1", s)
    s = re.sub(r"\*\s*([!?]\s*[A-Za-z_]\w*\s+in\s+[A-Za-z_]\w*)", r", \1", s)

    def _expand_grouped_quant(m: re.Match) -> str:
        q = m.group(1)
        vars_blob = m.group(2)
        typ = m.group(3)
        vars_ = [v.strip() for v in vars_blob.split(",") if v.strip()]
        if len(vars_) <= 1:
            return m.group(0)
        return q + " " + ", ".join(v + " in " + typ for v in vars_)

    s = re.sub(r"([!?])\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)+)\s+in\s+([A-Za-z_]\w*)", _expand_grouped_quant, s)
    s = re.sub(
        r"([!?]\s*[A-Za-z_]\w*\s+in\s+[A-Za-z_]\w*)\s+([!?]\s*[A-Za-z_]\w*\s+in\s+[A-Za-z_]\w*)",
        r"\1, \2",
        s,
    )
    s = re.sub(r",\s*,+", ", ", s)
    s = re.sub(r"\(\s*,\s*", "(", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_quant_entry(raw: Any, idx: int) -> tuple[str, str]:
    if isinstance(raw, dict):
        return _require_ident(raw.get("var"), f"rules[{idx}].forall.var"), _require_ident(raw.get("type"), f"rules[{idx}].forall.type")
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return _require_ident(raw[0], f"rules[{idx}].forall[0]"), _require_ident(raw[1], f"rules[{idx}].forall[1]")
    raise JSONIRCompilationError(f"rules[{idx}].forall entry must be {{var,type}} or [var,type].")


def _ensure_declared_symbol(name: str, arity: int, symbols: dict[str, tuple[tuple[str, ...], str]], ctx: str) -> tuple[tuple[str, ...], str]:
    sig = symbols.get(name)
    if not sig:
        raise JSONIRCompilationError(f"{ctx}: symbol '{name}' is not declared in predicates/functions.")
    expected_arity = len(sig[0])
    if expected_arity != arity:
        raise JSONIRCompilationError(f"{ctx}: symbol '{name}' expects {expected_arity} args, got {arity}.")
    return sig


def _split_fo_quantifier_head_and_body(rule: str) -> tuple[str | None, str]:
    """If rule starts with ! or ?, return (quantifier_head_without_body, body). Else (None, full)."""
    s = (rule or "").strip()
    if not s.startswith("!") and not s.startswith("?"):
        return None, s
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ":" and depth == 0:
            return s[:i].strip(), s[i + 1 :].strip()
    return None, s


def _vars_from_quantifier_head(head: str) -> set[str]:
    if not head:
        return set()
    h = head.lstrip("!?").strip()
    out: set[str] = set()
    for part in h.split(","):
        part = part.strip()
        m = re.match(r"^([A-Za-z_]\w*)\s+in\s+", part)
        if m:
            out.add(m.group(1))
    return out


def _top_level_colon_count(rule: str) -> int:
    depth = 0
    n = 0
    for ch in rule or "":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ":" and depth == 0:
            n += 1
    return n


def _has_colon_inside_parens(rule: str) -> bool:
    """True if ':' appears when parenthesis depth > 0 (nested quantifier / local scope in string rules)."""
    depth = 0
    for ch in rule or "":
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ":" and depth > 0:
            return True
    return False


def _sort_alias_key(name: str) -> str:
    """Case- and punctuation-insensitive key so `FinancialYear` matches `financial_year` in FO text."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _normalize_quantifier_sort(
    got: str, declared_types: set[str], scalars: set[str]
) -> str | None:
    """Map quantifier sort text to a declared JSON-IR / scalar sort name; None if unknown."""
    if got in declared_types or got in scalars:
        return got
    gk = _sort_alias_key(got)
    for d in declared_types:
        if _sort_alias_key(d) == gk:
            return d
    for s in scalars:
        if _sort_alias_key(s) == gk:
            return s
    return None


def _quantifier_var_types_from_head(head: str) -> dict[str, str]:
    """Parse `! v1 in T1, v2 in T2` / `? ...` head (without trailing colon) into var -> sort name."""
    h = (head or "").lstrip("!?").strip()
    out: dict[str, str] = {}
    for part in h.split(","):
        part = part.strip()
        m = re.match(r"^([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*$", part)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def _validate_string_rule_call_arg_sorts(
    rule: str,
    rule_idx: int,
    symbols: dict[str, tuple[tuple[str, ...], str]],
    declared_types: set[str],
) -> None:
    """Match quantified variables in string FO rules to symbol signatures (catches Date var used as Int, etc.)."""
    if _top_level_colon_count(rule) > 1 or _has_colon_inside_parens(rule):
        return
    head, body = _split_fo_quantifier_head_and_body(rule)
    if head is None:
        return
    env = _quantifier_var_types_from_head(head)
    if not env:
        return
    for call in _rule_calls(body):
        sig = symbols.get(call.name)
        if not sig:
            continue
        arg_types, _ret = sig
        m = re.search(r"\b" + re.escape(call.name) + r"\s*\(([^()]*)\)", body)
        if not m:
            continue
        raw_args = [a.strip() for a in m.group(1).split(",")]
        if len(raw_args) != len(arg_types):
            continue
        for j, (raw, exp) in enumerate(zip(raw_args, arg_types)):
            if not raw or _NUMBER_RE.match(raw) or raw.lower() in {"true", "false"}:
                continue
            if not _IDENT_RE.match(raw):
                continue
            if raw not in env:
                continue
            got_raw = env[raw]
            got = _normalize_quantifier_sort(got_raw, declared_types, _SCALAR_TYPES)
            if got is None:
                continue
            if not _law_sort_assignable(exp, got):
                raise JSONIRCompilationError(
                    f"rules[{rule_idx}]: argument {j} to '{call.name}' expects sort {exp}, "
                    f"but '{raw}' is quantified as {got_raw} (normalized: {got}). Fix the rule or the symbol table "
                    f"(IDP errors such as 'integer expected (date found: {raw})' come from this mismatch)."
                )


def _validate_string_rule_no_unbound_constants(rule: str, declared_types: set[str]) -> None:
    """Law rules must not use bare case-like constants; every call arg should be a quantified var or literal."""
    if _top_level_colon_count(rule) > 1 or _has_colon_inside_parens(rule):
        # Nested quantifiers (e.g. exists inside forall): skip this lightweight scan.
        return
    head, body = _split_fo_quantifier_head_and_body(rule)
    if head is None:
        return
    qvars = _vars_from_quantifier_head(head)
    if not qvars:
        return
    for call in _rule_calls(body):
        arg_blob = ""
        m = re.search(r"\b" + re.escape(call.name) + r"\s*\(([^()]*)\)", body)
        if m:
            arg_blob = m.group(1)
        for raw_arg in arg_blob.split(","):
            a = raw_arg.strip()
            if not a:
                continue
            if _NUMBER_RE.match(a) or a.lower() in {"true", "false"}:
                continue
            if not _IDENT_RE.match(a):
                continue
            if a in qvars:
                continue
            if a in declared_types:
                raise JSONIRCompilationError(
                    f"Law rule uses type name '{a}' as a value (did you mean a quantified variable?)."
                )
            raise JSONIRCompilationError(
                f"Unbound constant '{a}' in reusable law rule (not declared in quantifiers {sorted(qvars)}). "
                "Use only quantified variables, numeric literals, or true/false in rule heads."
            )


def _infer_term_type(
    raw: Any,
    idx: int,
    symbols: dict[str, tuple[tuple[str, ...], str]],
    env: dict[str, str],
    ctx: str,
) -> str:
    if isinstance(raw, bool):
        return "Bool"
    if isinstance(raw, int):
        return "Int"
    if isinstance(raw, float):
        return "Real"
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}: empty term.")
        if _NUMBER_RE.match(s) or s.lower() in {"true", "false"}:
            if s.lower() in {"true", "false"}:
                return "Bool"
            return "Real" if "." in s else "Int"
        if s not in env:
            raise JSONIRCompilationError(
                f"rules[{idx}].{ctx}: unbound identifier '{s}' in object rule (not in quantifiers {sorted(env)})."
            )
        return env[s]
    if isinstance(raw, dict):
        fn = raw.get("func") or raw.get("function")
        if not fn:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}: term object must contain 'func'.")
        name = _require_ident(fn, f"rules[{idx}].{ctx}.func")
        args = raw.get("args", [])
        if not isinstance(args, list):
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.args must be a list.")
        sig = _ensure_declared_symbol(name, len(args), symbols, f"rules[{idx}].{ctx}")
        for j, sub in enumerate(args):
            got = _infer_term_type(sub, idx, symbols, env, ctx + f".args[{j}]")
            exp = sig[0][j]
            if not _law_sort_assignable(exp, got):
                raise JSONIRCompilationError(
                    f"rules[{idx}].{ctx}: argument {j} to '{name}' expects type {exp}, got {got}."
                )
        return sig[1]
    raise JSONIRCompilationError(f"rules[{idx}].{ctx}: unsupported term {type(raw).__name__}.")


def _infer_expr_type(
    raw: Any,
    idx: int,
    symbols: dict[str, tuple[tuple[str, ...], str]],
    env: dict[str, str],
    ctx: str,
) -> str:
    if isinstance(raw, list):
        if not raw:
            return "Bool"
        for j, x in enumerate(raw):
            t = _infer_expr_type(x, idx, symbols, env, ctx + f"[{j}]")
            if t != "Bool":
                raise JSONIRCompilationError(f"rules[{idx}].{ctx}[{j}]: expected Bool, got {t}.")
        return "Bool"
    if isinstance(raw, str):
        raise JSONIRCompilationError(f"rules[{idx}].{ctx}: raw string expressions are not allowed inside object rules.")
    if not isinstance(raw, dict):
        raise JSONIRCompilationError(f"rules[{idx}].{ctx}: expression must be object or list.")
    _reject_malformed_expr_shape(raw, idx, ctx)
    if "pred" in raw or "symbol" in raw:
        pred = _require_ident(raw.get("pred") or raw.get("symbol"), f"rules[{idx}].{ctx}.pred")
        args = raw.get("args", [])
        if not isinstance(args, list):
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.args must be a list.")
        sig = _ensure_declared_symbol(pred, len(args), symbols, f"rules[{idx}].{ctx}")
        if sig[1] != "Bool":
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}: '{pred}' is a function, not a predicate.")
        for j, sub in enumerate(args):
            got = _infer_term_type(sub, idx, symbols, env, ctx + f".args[{j}]")
            exp = sig[0][j]
            if not _law_sort_assignable(exp, got):
                var_hint = ""
                if isinstance(sub, str) and sub.strip() in env:
                    var_hint = f" Variable '{sub.strip()}' is declared as '{got}'."
                raise JSONIRCompilationError(
                    f"rules[{idx}].{ctx}: argument {j} to predicate '{pred}' expects type {exp}, got {got}."
                    + var_hint
                    + " JSON_IR has no subtype system. If "
                    + got
                    + " is only a role/subset of "
                    + exp
                    + ", use "
                    + exp
                    + " as the variable type and represent the role with a predicate. "
                    "If the predicate signature is wrong, repair the symbol table."
                )
        return "Bool"
    if "not" in raw:
        t = _infer_expr_type(raw["not"], idx, symbols, env, ctx + ".not")
        if t != "Bool":
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.not: expected Bool, got {t}.")
        return "Bool"
    if "and" in raw:
        xs = raw.get("and")
        if not isinstance(xs, list) or not xs:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.and must be a non-empty list.")
        for j, x in enumerate(xs):
            t = _infer_expr_type(x, idx, symbols, env, ctx + f".and[{j}]")
            if t != "Bool":
                raise JSONIRCompilationError(f"rules[{idx}].{ctx}.and[{j}]: expected Bool, got {t}.")
        return "Bool"
    if "or" in raw:
        xs = raw.get("or")
        if not isinstance(xs, list) or not xs:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.or must be a non-empty list.")
        for j, x in enumerate(xs):
            t = _infer_expr_type(x, idx, symbols, env, ctx + f".or[{j}]")
            if t != "Bool":
                raise JSONIRCompilationError(f"rules[{idx}].{ctx}.or[{j}]: expected Bool, got {t}.")
        return "Bool"
    comp = raw.get("compare") if "compare" in raw else raw if {"left", "op", "right"}.issubset(raw.keys()) else None
    if comp is not None:
        if not isinstance(comp, dict):
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.compare must be an object.")
        op = str(comp.get("op") or "").strip()
        if op == "<=":
            op = "=<"
        if op not in _ALLOWED_COMPARE_OPS:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.compare has unsupported op: {op}")
        lt = _infer_term_type(comp.get("left"), idx, symbols, env, ctx + ".left")
        rt = _infer_term_type(comp.get("right"), idx, symbols, env, ctx + ".right")
        if lt == "Bool" or rt == "Bool":
            if op not in {"=", "~="}:
                raise JSONIRCompilationError(
                    f"rules[{idx}].{ctx}.compare: ordering comparisons require numeric terms, got {lt} vs {rt}."
                )
        elif lt != rt:
            raise JSONIRCompilationError(
                f"rules[{idx}].{ctx}.compare: left type {lt} must match right type {rt} for comparison "
                "(IDP rejects mixed sorts, including Int vs Real)."
            )
        return "Bool"
    keys = sorted(raw.keys()) if isinstance(raw, dict) else []
    raise JSONIRCompilationError(
        f"rules[{idx}].{ctx}: unsupported expression object (keys {keys}). "
        "Allowed: atom {{\"pred\"/\"symbol\", \"args\", \"negated\"?}}, "
        "\"and\"/\"or\" lists, \"not\", or \"compare\" / {{left,op,right}}."
    )


def _typecheck_object_rule_before_render(
    raw_rule: dict,
    idx: int,
    symbol_sigs: dict[str, tuple[tuple[str, ...], str]],
    *,
    pred_kinds: dict[str, str] | None = None,
    pred_names: set[str] | None = None,
    fun_names: set[str] | None = None,
) -> None:
    if pred_kinds is not None and pred_names is not None and fun_names is not None:
        _validate_object_rule_schema_design(raw_rule, idx, pred_kinds, pred_names, fun_names)
    q_raw = raw_rule.get("forall", [])
    if not isinstance(q_raw, list):
        return
    quants = [_normalize_quant_entry(q, idx) for q in q_raw]
    env = {v: t for v, t in quants}
    if "formula" in raw_rule:
        t = _infer_expr_type(raw_rule["formula"], idx, symbol_sigs, env, "formula")
        if t != "Bool":
            raise JSONIRCompilationError(f"rules[{idx}].formula must be Bool, got {t}")
        return
    if_raw = raw_rule.get("if", [])
    then_raw = raw_rule.get("then", [])
    _infer_expr_type(if_raw, idx, symbol_sigs, env, "if")
    _infer_expr_type(then_raw, idx, symbol_sigs, env, "then")


def _render_literal(value: Any, ctx: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if not isinstance(value, str):
        raise JSONIRCompilationError(ctx + " must be a string, number, boolean, or function term.")
    s = value.strip()
    if not s:
        raise JSONIRCompilationError(ctx + " cannot be empty.")
    if _NUMBER_RE.match(s) or s.lower() in {"true", "false"}:
        return s.lower()
    # In theory rules, bare identifiers are variables/constants from quantified domains.
    return _require_ident(s, ctx)


def _render_term(raw: Any, idx: int, symbols: dict[str, tuple[tuple[str, ...], str]], ctx: str) -> str:
    if isinstance(raw, dict):
        fn = raw.get("func") or raw.get("function")
        if not fn:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}: term object must contain 'func'.")
        name = _require_ident(fn, f"rules[{idx}].{ctx}.func")
        args = raw.get("args", [])
        if not isinstance(args, list):
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.args must be a list.")
        _ensure_declared_symbol(name, len(args), symbols, f"rules[{idx}].{ctx}")
        return name + "(" + ",".join(_render_term(a, idx, symbols, ctx + ".args") for a in args) + ")"
    return _render_literal(raw, f"rules[{idx}].{ctx}")


def _render_atom(raw: dict, idx: int, symbols: dict[str, tuple[tuple[str, ...], str]], ctx: str) -> str:
    pred = _require_ident(raw.get("pred") or raw.get("symbol"), f"rules[{idx}].{ctx}.pred")
    args = raw.get("args", [])
    if not isinstance(args, list):
        raise JSONIRCompilationError(f"rules[{idx}].{ctx}.args must be a list.")
    sig = _ensure_declared_symbol(pred, len(args), symbols, f"rules[{idx}].{ctx}")
    if sig[1] != "Bool":
        raise JSONIRCompilationError(f"rules[{idx}].{ctx}: '{pred}' is a function, not a predicate.")
    rendered_args = [_render_term(a, idx, symbols, ctx + ".args") for a in args]
    call = pred + "(" + ",".join(rendered_args) + ")"
    neg = bool(raw.get("neg") or raw.get("negated", False))
    return ("~" + call) if neg else call


def _render_expr(raw: Any, idx: int, symbols: dict[str, tuple[tuple[str, ...], str]], ctx: str) -> str:
    if isinstance(raw, list):
        if not raw:
            return "true"
        return " & ".join("(" + _render_expr(x, idx, symbols, ctx) + ")" for x in raw)
    if isinstance(raw, str):
        # Backward-compatible escape hatch. Still validated later for undeclared calls.
        return _normalize_rule_text(raw)
    if not isinstance(raw, dict):
        raise JSONIRCompilationError(f"rules[{idx}].{ctx} expression must be object/list/string.")

    if "pred" in raw or "symbol" in raw:
        return _render_atom(raw, idx, symbols, ctx)
    if "not" in raw:
        return "~(" + _render_expr(raw["not"], idx, symbols, ctx + ".not") + ")"
    if "and" in raw:
        xs = raw.get("and")
        if not isinstance(xs, list) or not xs:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.and must be a non-empty list.")
        return " & ".join("(" + _render_expr(x, idx, symbols, ctx + ".and") + ")" for x in xs)
    if "or" in raw:
        xs = raw.get("or")
        if not isinstance(xs, list) or not xs:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.or must be a non-empty list.")
        return " | ".join("(" + _render_expr(x, idx, symbols, ctx + ".or") + ")" for x in xs)

    comp = raw.get("compare") if "compare" in raw else raw if {"left", "op", "right"}.issubset(raw.keys()) else None
    if comp is not None:
        if not isinstance(comp, dict):
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.compare must be an object.")
        op = str(comp.get("op") or "").strip()
        if op == "<=":
            op = "=<"
        if op not in _ALLOWED_COMPARE_OPS:
            raise JSONIRCompilationError(f"rules[{idx}].{ctx}.compare has unsupported op: {op}")
        left = _render_term(comp.get("left"), idx, symbols, ctx + ".left")
        right = _render_term(comp.get("right"), idx, symbols, ctx + ".right")
        return left + " " + op + " " + right

    raise JSONIRCompilationError(f"rules[{idx}].{ctx}: unsupported expression object.")


def _render_rule_object(
    raw_rule: dict,
    idx: int,
    symbol_sigs: dict[str, tuple[tuple[str, ...], str]],
    *,
    pred_kinds: dict[str, str] | None = None,
    pred_names: set[str] | None = None,
    fun_names: set[str] | None = None,
) -> str:
    if not isinstance(raw_rule, dict):
        raise JSONIRCompilationError(f"rules[{idx}] must be a string or object.")
    q_raw = raw_rule.get("forall", [])
    if not isinstance(q_raw, list):
        raise JSONIRCompilationError(f"rules[{idx}].forall must be a list.")
    quants = [_normalize_quant_entry(q, idx) for q in q_raw]
    _typecheck_object_rule_before_render(
        raw_rule, idx, symbol_sigs, pred_kinds=pred_kinds, pred_names=pred_names, fun_names=fun_names
    )

    # Preferred explicit expression form.
    if "formula" in raw_rule:
        body = _render_expr(raw_rule["formula"], idx, symbol_sigs, "formula")
    else:
        if_raw = raw_rule.get("if", [])
        then_raw = raw_rule.get("then", [])
        operator = str(raw_rule.get("operator") or "implies").strip().lower()
        if operator not in {"implies", "iff"}:
            raise JSONIRCompilationError(f"rules[{idx}].operator must be 'implies' or 'iff'.")
        ant = _render_expr(if_raw, idx, symbol_sigs, "if")
        cons = _render_expr(then_raw, idx, symbol_sigs, "then")
        if not str(cons).strip() or str(cons).strip() == "true":
            raise JSONIRCompilationError(f"rules[{idx}] must contain a non-empty consequent in 'then'.")
        if operator == "iff":
            # Legal definitions are usually: conclusion iff conditions.
            body = "(" + cons + ") <=> (" + ant + ")"
        else:
            body = "(" + ant + ") => (" + cons + ")"

    if quants:
        qtxt = ", ".join(v + " in " + t for v, t in quants)
        return "! " + qtxt + ": " + body + "."
    return body + "."


def _symbol_to_json(d: SymbolDecl) -> dict[str, Any]:
    obj: dict[str, Any] = {"name": d.name, "args": d.args, "returns": d.returns}
    if d.kind != "unknown":
        obj["kind"] = d.kind
    if d.description:
        obj["description"] = d.description
    if d.directly_observable:
        obj["directly_observable"] = True
    if d.case_input:
        obj["case_input"] = True
    if d.factual_criteria_input:
        obj["factual_criteria_input"] = True
    if d.legal_output is not None:
        obj["legal_output"] = d.legal_output
    if d.output_category:
        obj["output_category"] = d.output_category
    return obj


def normalize_json_ir(ir: dict) -> dict:
    if "types" not in ir:
        raise JSONIRCompilationError("JSON IR missing required key: types")
    if "rules" not in ir:
        raise JSONIRCompilationError("JSON IR missing required key: rules")

    types_raw = ir.get("types")
    predicates_raw = ir.get("predicates", [])
    functions_raw = ir.get("functions", [])
    rules_raw = ir.get("rules")

    if not isinstance(types_raw, list):
        raise JSONIRCompilationError("types must be a list.")
    if not isinstance(predicates_raw, list):
        raise JSONIRCompilationError("predicates must be a list.")
    if not isinstance(functions_raw, list):
        raise JSONIRCompilationError("functions must be a list.")
    if not isinstance(rules_raw, list):
        raise JSONIRCompilationError("rules must be a list.")

    types: list[str] = []
    for t in types_raw:
        if isinstance(t, dict):
            t = t.get("name")
        types.append(_validate_type_name(t))
    if not types:
        raise JSONIRCompilationError("types cannot be empty.")
    if len(set(types)) != len(types):
        raise JSONIRCompilationError("Duplicate type declarations in JSON IR.")

    predicates = [_validate_symbol_decl(p, f"predicates[{i}]", default_returns="Bool") for i, p in enumerate(predicates_raw)]
    functions = [_validate_symbol_decl(f, f"functions[{i}]", default_returns="Int") for i, f in enumerate(functions_raw)]

    type_set = set(types) | _SCALAR_TYPES
    for decl in predicates:
        if decl.returns != "Bool":
            raise JSONIRCompilationError("Predicate must return Bool: " + decl.name)
    for decl in predicates + functions:
        if decl.returns not in type_set:
            raise JSONIRCompilationError("Unknown return type in declaration: " + decl.name)
        for at in decl.args:
            if at not in type_set:
                raise JSONIRCompilationError("Unknown argument type in declaration: " + decl.name)

    seen_names: dict[str, tuple[tuple[str, ...], str]] = {}
    for decl in predicates + functions:
        sig = (tuple(decl.args), decl.returns)
        prev = seen_names.get(decl.name)
        if prev and prev != sig:
            raise JSONIRCompilationError("Conflicting signatures for symbol: " + decl.name)
        seen_names[decl.name] = sig

    pred_kinds = _symbol_kind_map(predicates, functions)
    pred_names = {p.name for p in predicates}
    fun_names = {f.name for f in functions}

    from pipeline.kb.numeric_compare_normalize import normalize_json_ir_rule_compare_sorts

    normalize_json_ir_rule_compare_sorts(
        {
            "types": types,
            "predicates": [_symbol_to_json(d) for d in predicates],
            "functions": [_symbol_to_json(d) for d in functions],
            "rules": rules_raw,
        },
        predicates,
        functions,
    )

    rules: list[str] = []
    declared_type_names = set(types)
    for i, r in enumerate(rules_raw):
        if isinstance(r, str):
            if not r.strip():
                raise JSONIRCompilationError(f"rules[{i}] must be a non-empty string.")
            rr = _normalize_rule_text(r)
            _validate_string_rule_no_unbound_constants(rr, declared_type_names)
            _validate_string_rule_call_arg_sorts(rr, i, seen_names, declared_type_names)
        else:
            if isinstance(r, dict):
                _validate_object_rule_schema_design(r, i, pred_kinds, pred_names, fun_names)
            rr = _normalize_rule_text(
                _render_rule_object(
                    r, i, seen_names, pred_kinds=pred_kinds, pred_names=pred_names, fun_names=fun_names
                )
            )
        if not rr.endswith("."):
            rr += "."
        rules.append(rr)

    all_calls: list[RuleCall] = []
    for r in rules:
        all_calls.extend(_rule_calls(r))
    rewrites = _build_rewrite_map(set(seen_names.keys()), all_calls)
    rules = [_rewrite_rule_symbols(r, rewrites) for r in rules]

    declared = set(seen_names.keys())
    unresolved: dict[str, int] = {}
    arity_errors: list[str] = []
    for r in rules:
        for call in _rule_calls(r):
            if call.name not in declared:
                unresolved[call.name] = max(unresolved.get(call.name, 0), call.arity)
            else:
                expected = len(seen_names[call.name][0])
                if call.arity != expected:
                    arity_errors.append(f"{call.name} expects {expected}, got {call.arity}")

    synthesize = (os.getenv("JSON_IR_SYNTHESIZE_UNDECLARED", "") or "").strip().lower() in {"1", "true", "yes"}
    if unresolved and synthesize:
        if "Person" not in set(types):
            raise JSONIRCompilationError("Cannot synthesize undeclared symbols because type Person is not declared: " + ", ".join(sorted(unresolved)))
        for name, arity in sorted(unresolved.items()):
            d = SymbolDecl(name=name, args=["Person"] * arity, returns="Bool", kind="unknown")
            predicates.append(d)
            seen_names[d.name] = (tuple(d.args), d.returns)
    elif unresolved:
        raise JSONIRCompilationError("Rule uses undeclared symbol(s): " + ", ".join(f"{k}/{v}" for k, v in sorted(unresolved.items())))

    if arity_errors:
        raise JSONIRCompilationError("Rule symbol arity mismatch: " + "; ".join(sorted(set(arity_errors))))

    return {
        "types": types,
        "predicates": [_symbol_to_json(d) for d in predicates],
        "functions": [_symbol_to_json(d) for d in functions],
        "rules": rules,
    }


def _walk_exprs_for_predicate_atoms(expr: Any, sink: set[str]) -> None:
    """Collect predicate/symbol names used as Bool atoms in object-rule expressions."""
    if isinstance(expr, list):
        for x in expr:
            _walk_exprs_for_predicate_atoms(x, sink)
        return
    if not isinstance(expr, dict):
        return
    if "pred" in expr or "symbol" in expr:
        n = str(expr.get("pred") or expr.get("symbol") or "").strip()
        if n:
            sink.add(n)
        return
    if "not" in expr:
        _walk_exprs_for_predicate_atoms(expr.get("not"), sink)
        return
    if "and" in expr:
        for x in expr.get("and") or []:
            _walk_exprs_for_predicate_atoms(x, sink)
        return
    if "or" in expr:
        for x in expr.get("or") or []:
            _walk_exprs_for_predicate_atoms(x, sink)
        return
    # compare / func terms: no Bool predicate head here


def preflight_json_ir_rule_predicates(ir: dict) -> None:
    """Fail fast when rules use a symbol as a Bool atom but the symbol table declares it as a function or non-Bool."""
    preds_raw = ir.get("predicates") or []
    funs_raw = ir.get("functions") or []
    pred_returns: dict[str, str] = {}
    fun_names: set[str] = set()
    for p in preds_raw:
        if not isinstance(p, dict):
            continue
        nm = str(p.get("name") or "").strip()
        if not nm:
            continue
        pred_returns[nm] = str(p.get("returns") or "Bool").strip()
    for f in funs_raw:
        if isinstance(f, dict) and f.get("name"):
            fun_names.add(str(f["name"]).strip())

    used: set[str] = set()
    for rule in ir.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        for key in ("if", "then", "formula"):
            if key in rule:
                _walk_exprs_for_predicate_atoms(rule[key], used)

    for name in sorted(used):
        if name in fun_names and name not in pred_returns:
            raise JSONIRCompilationError(
                SCHEMA_DESIGN_TAG
                + ": Rules use '"
                + name
                + "' as a Bool predicate atom, but the symbol table lists it only under functions. "
                "If this concept is yes/no, declare it as a predicate with returns Bool. "
                "If it returns a value, use it only as a function term inside a comparison. "
                "Repair layer: rules."
            )
        if name in pred_returns and pred_returns[name].lower() != "bool":
            raise JSONIRCompilationError(
                SCHEMA_DESIGN_TAG
                + ": Rules use '"
                + name
                + "' as a Bool predicate, but the symbol table declares returns "
                + pred_returns[name]
                + ". Predicates used in rules must return Bool."
            )


def kb_schema_dict_from_normalized(norm: dict, *, rules_objects: list | None = None) -> dict:
    """Schema for extraction/validation: preserves predicate/function metadata from JSON_IR."""
    out: dict = {
        "types": list(norm["types"]),
        "predicates": [dict(p) for p in norm["predicates"]],
        "functions": [dict(f) for f in norm["functions"]],
    }
    if rules_objects:
        out["rules"] = [dict(r) for r in rules_objects if isinstance(r, dict)]
    return out


def _fo_text_from_normalized(norm: dict) -> str:
    lines: list[str] = ["vocabulary V {"]
    for t in norm["types"]:
        lines.append("  type " + t)

    for p in norm["predicates"]:
        domain = " * ".join(p["args"])
        if not domain:
            domain = "()"
        lines.append("  " + p["name"] + ": " + domain + " -> " + p["returns"])
    for f in norm["functions"]:
        domain = " * ".join(f["args"])
        if not domain:
            domain = "()"
        lines.append("  " + f["name"] + ": " + domain + " -> " + f["returns"])
    lines.append("}")
    lines.append("")
    lines.append("theory T:V {")
    for r in norm["rules"]:
        lines.append("  " + r)
    lines.append("}")
    return "\n".join(lines).strip() + "\n"


def render_json_ir_to_fo_and_schema(
    ir: dict,
    *,
    law_text_for_lints: str | None = None,
    scope_metadata: dict | None = None,
) -> tuple[str, dict]:
    from pipeline.kb.factual_criteria import apply_pragmatic_factual_criteria_to_ir

    query_pred = None
    if isinstance(scope_metadata, dict):
        query_pred = scope_metadata.get("query_predicate")
    apply_pragmatic_factual_criteria_to_ir(
        ir,
        query_predicate=query_pred,
        diagnostics=scope_metadata.get("factual_criteria_diagnostics") if isinstance(scope_metadata, dict) else None,
    )

    allow_partial = (os.getenv("JSON_IR_ALLOW_PARTIAL_KB") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }

    def _object_rules_from_source(source: dict) -> list:
        return [r for r in (source.get("rules") or []) if isinstance(r, dict)]

    try:
        predicates, functions, types = validate_json_ir_symbols(
            ir,
            law_text_for_lints=law_text_for_lints,
            scope_metadata=scope_metadata,
        )
        merged = {
            "types": types,
            "predicates": [_symbol_to_json(d) for d in predicates],
            "functions": [_symbol_to_json(d) for d in functions],
            "rules": ir.get("rules") or [],
        }
        validate_combined_json_ir_schema(
            merged,
            predicates,
            functions,
            law_text_for_lints=law_text_for_lints,
            scope_metadata=scope_metadata,
        )
        object_rules = _object_rules_from_source(merged)
        norm = normalize_json_ir(merged)
    except JSONIRCompilationError:
        if not allow_partial:
            raise
        norm, _warnings = _normalize_with_quarantine(
            ir, law_text_for_lints=law_text_for_lints, scope_metadata=scope_metadata
        )
        object_rules = _object_rules_from_source(ir)
    return _fo_text_from_normalized(norm), kb_schema_dict_from_normalized(norm, rules_objects=object_rules)


def render_json_ir_to_fo(ir: dict) -> str:
    return render_json_ir_to_fo_and_schema(ir)[0]
