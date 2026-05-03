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


class JSONIRCompilationError(Exception):
    pass


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


def _law_sort_assignable(expected: str, got: str) -> bool:
    if expected == got:
        return True
    if expected == "Asset" and got in _ASSET_LIKE_SORTS:
        return True
    return False
_ALLOWED_COMPARE_OPS = {"=", "~=", "<", "=<", "<=", ">", ">=", "=>"}
_ALLOWED_KINDS = {"observable", "derived", "helper", "conclusion", "input", "unknown"}


@dataclass(frozen=True)
class SymbolDecl:
    name: str
    args: list[str]
    returns: str
    kind: str = "unknown"
    description: str = ""


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
    raise JSONIRCompilationError("Invalid JSON IR output: " + str(last_err)) from last_err


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
    return coerced


def _validate_type_name(type_name: Any) -> str:
    return _require_ident(type_name, "Type")


def _normalize_kind(value: Any) -> str:
    k = str(value or "unknown").strip().lower()
    return k if k in _ALLOWED_KINDS else "unknown"


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
    return SymbolDecl(
        name=name,
        args=parsed_args,
        returns=returns,
        kind=_normalize_kind(raw.get("kind")),
        description=str(raw.get("description") or "").strip(),
    )


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
            return "Bool" if s.lower() in {"true", "false"} else "Int"
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
                raise JSONIRCompilationError(
                    f"rules[{idx}].{ctx}: argument {j} to predicate '{pred}' expects type {exp}, got {got}."
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
            numeric = {"Int", "Real"}
            if not (lt in numeric and rt in numeric):
                raise JSONIRCompilationError(
                    f"rules[{idx}].{ctx}.compare: left type {lt} must match right type {rt} for comparison."
                )
        return "Bool"
    keys = sorted(raw.keys()) if isinstance(raw, dict) else []
    raise JSONIRCompilationError(
        f"rules[{idx}].{ctx}: unsupported expression object (keys {keys}). "
        "Allowed: atom {{\"pred\"/\"symbol\", \"args\", \"negated\"?}}, "
        "\"and\"/\"or\" lists, \"not\", or \"compare\" / {{left,op,right}}."
    )


def _typecheck_object_rule_before_render(raw_rule: dict, idx: int, symbol_sigs: dict[str, tuple[tuple[str, ...], str]]) -> None:
    q_raw = raw_rule.get("forall", [])
    if not isinstance(q_raw, list):
        return
    quants = [_normalize_quant_entry(q, idx) for q in q_raw]
    if not quants:
        return
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


def _render_rule_object(raw_rule: dict, idx: int, symbol_sigs: dict[str, tuple[tuple[str, ...], str]]) -> str:
    if not isinstance(raw_rule, dict):
        raise JSONIRCompilationError(f"rules[{idx}] must be a string or object.")
    q_raw = raw_rule.get("forall", [])
    if not isinstance(q_raw, list):
        raise JSONIRCompilationError(f"rules[{idx}].forall must be a list.")
    quants = [_normalize_quant_entry(q, idx) for q in q_raw]
    _typecheck_object_rule_before_render(raw_rule, idx, symbol_sigs)

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

    rules: list[str] = []
    declared_type_names = set(types)
    for i, r in enumerate(rules_raw):
        if isinstance(r, str):
            if not r.strip():
                raise JSONIRCompilationError(f"rules[{i}] must be a non-empty string.")
            rr = _normalize_rule_text(r)
            _validate_string_rule_no_unbound_constants(rr, declared_type_names)
        else:
            rr = _normalize_rule_text(_render_rule_object(r, i, seen_names))
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


def kb_schema_dict_from_normalized(norm: dict) -> dict:
    """Schema for extraction/validation: preserves predicate/function metadata from JSON_IR."""
    return {
        "types": list(norm["types"]),
        "predicates": [dict(p) for p in norm["predicates"]],
        "functions": [dict(f) for f in norm["functions"]],
    }


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


def render_json_ir_to_fo_and_schema(ir: dict) -> tuple[str, dict]:
    norm = normalize_json_ir(ir)
    return _fo_text_from_normalized(norm), kb_schema_dict_from_normalized(norm)


def render_json_ir_to_fo(ir: dict) -> str:
    return render_json_ir_to_fo_and_schema(ir)[0]
