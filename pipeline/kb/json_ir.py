"""JSON IR support for deterministic FO(.) rendering."""

from __future__ import annotations

import json
import re
from difflib import get_close_matches
from dataclasses import dataclass


class JSONIRCompilationError(Exception):
    pass


_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
_SCALAR_TYPES = {"Bool", "Int", "Real"}


@dataclass(frozen=True)
class SymbolDecl:
    name: str
    args: list[str]
    returns: str


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
    """
    Extract balanced {...} object substrings from noisy model output.
    Keeps track of string literals so braces inside strings don't break scanning.
    """
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

    # Deduplicate while preserving order.
    seen = set()
    uniq_candidates = []
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        uniq_candidates.append(c)

    parse_attempts: list[str] = []
    for c in uniq_candidates:
        parse_attempts.append(c)
        # Common LLM artifact: trailing commas in arrays/objects.
        parse_attempts.append(re.sub(r",(\s*[}\]])", r"\1", c))

    # Common LLM artifact: trailing commas in arrays/objects.
    last_err: Exception | None = None
    obj = None
    for candidate in parse_attempts:
        try:
            obj = json.loads(candidate)
            break
        except json.JSONDecodeError as e:
            last_err = e
    if obj is None:
        raise JSONIRCompilationError("Invalid JSON IR output: " + str(last_err)) from last_err
    if not isinstance(obj, dict):
        raise JSONIRCompilationError("JSON IR root must be an object.")
    return obj


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


def _require_ident(value: str, ctx: str) -> str:
    if value is None:
        raise JSONIRCompilationError(ctx + " must be a valid identifier.")
    if not isinstance(value, str):
        value = str(value)
    coerced = _coerce_identifier(value.strip())
    if not _IDENT_RE.match(coerced):
        raise JSONIRCompilationError(ctx + " must be a valid identifier.")
    return coerced


def _validate_type_name(type_name: str) -> str:
    t = _require_ident(type_name, "Type")
    return t


def _validate_symbol_decl(raw: dict, ctx: str) -> SymbolDecl:
    if isinstance(raw, str):
        return SymbolDecl(name=_require_ident(raw, ctx + ".name"), args=[], returns="Bool")
    if not isinstance(raw, dict):
        raise JSONIRCompilationError(ctx + " must be an object or identifier string.")
    name = _require_ident(raw.get("name"), ctx + ".name")
    args = raw.get("args", [])
    returns_raw = raw.get("returns")
    if returns_raw is None:
        returns = "Bool"
    else:
        try:
            returns = _require_ident(returns_raw, ctx + ".returns")
        except JSONIRCompilationError:
            # Conservative fallback for noisy JSON IR: treat invalid/missing return type as Bool.
            returns = "Bool"
    if not isinstance(args, list):
        raise JSONIRCompilationError(ctx + ".args must be a list.")
    parsed_args: list[str] = []
    for i, arg_t in enumerate(args):
        parsed_args.append(_require_ident(arg_t, ctx + ".args[" + str(i) + "]"))
    return SymbolDecl(name=name, args=parsed_args, returns=returns)


def _count_args(arg_blob: str) -> int:
    s = (arg_blob or "").strip()
    if not s:
        return 0
    return len([a for a in s.split(",") if a.strip()])


def _rule_calls(rule: str) -> list[RuleCall]:
    out: list[RuleCall] = []
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)", rule):
        out.append(RuleCall(name=m.group(1), arity=_count_args(m.group(2))))
    return out


def _canon_symbol(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _build_rewrite_map(declared_names: set[str], calls: list[RuleCall]) -> dict[str, str]:
    """
    Deterministically map non-declared rule symbols to declared ones.
    Priority:
    1) exact match
    2) canonical exact match (case/underscore-insensitive)
    3) close match on canonical form (single high-confidence candidate)
    """
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
        # Fuzzy fallback when there is a strong single candidate.
        close = get_close_matches(canon, list(canon_to_decl.keys()), n=1, cutoff=0.82)
        if close:
            candidates = canon_to_decl.get(close[0], [])
            if len(candidates) == 1:
                out[c.name] = candidates[0]
    return out


def _rewrite_rule_symbols(rule: str, rewrites: dict[str, str]) -> str:
    if not rewrites:
        return rule

    def repl(m):
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
    # Canonicalize broad malformed implication operator variants.
    s = re.sub(r"[-–—]\s*\*+\s*>", " => ", s)
    s = re.sub(r"(?<![<>=!])<=", "=<", s)
    s = re.sub(r"!\s*([A-Za-z_]\w*\s*\()", r"~\1", s)

    # Quantifier keyword variants.
    s = re.sub(r"\bexists\s+([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*:", r"? \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r"\bforall\s+([A-Za-z_]\w*)\s+in\s+([A-Za-z_]\w*)\s*:", r"! \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r"\bexists\s*\(\s*([A-Za-z_]\w*)\s*\*\s*in\s+([A-Za-z_]\w*)\s*:", r"? \1 in \2:", s, flags=re.IGNORECASE)
    s = re.sub(r"\bforall\s*\(\s*([A-Za-z_]\w*)\s*\*\s*in\s+([A-Za-z_]\w*)\s*:", r"! \1 in \2:", s, flags=re.IGNORECASE)
    # Canonicalize stray separators before quantifier heads (common LLM corruption).
    s = re.sub(r",\s*\*\s*([!?])", r", \1", s)
    s = re.sub(r"\(\s*\*\s*([!?])", r"(\1", s)
    s = re.sub(r"\s\*\s*([!?])", r" \1", s)
    s = re.sub(r"([!?]\s*[A-Za-z_]\w*\s+in\s+[A-Za-z_]\w*)\s*\*", r"\1", s)
    # Ensure quantifier heads are separated by commas, not product tokens.
    s = re.sub(r"\*\s*([!?]\s*[A-Za-z_]\w*\s+in\s+[A-Za-z_]\w*)", r", \1", s)

    def _expand_grouped_quant(m):
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
    # Clean duplicate separators introduced by previous rewrites.
    s = re.sub(r",\s*,+", ", ", s)
    s = re.sub(r"\(\s*,\s*", "(", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_quant_entry(raw, idx: int) -> tuple[str, str]:
    if isinstance(raw, dict):
        var = _require_ident(raw.get("var"), f"rules[{idx}].forall.var")
        typ = _require_ident(raw.get("type"), f"rules[{idx}].forall.type")
        return var, typ
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        var = _require_ident(raw[0], f"rules[{idx}].forall[0]")
        typ = _require_ident(raw[1], f"rules[{idx}].forall[1]")
        return var, typ
    raise JSONIRCompilationError(f"rules[{idx}].forall entry must be {{var,type}} or [var,type].")


def _normalize_atom(raw, idx: int, side: str) -> dict:
    if not isinstance(raw, dict):
        raise JSONIRCompilationError(f"rules[{idx}].{side} atom must be an object.")
    pred = _require_ident(raw.get("pred"), f"rules[{idx}].{side}.pred")
    args = raw.get("args", [])
    if not isinstance(args, list):
        raise JSONIRCompilationError(f"rules[{idx}].{side}.args must be a list.")
    parsed_args = [_require_ident(a, f"rules[{idx}].{side}.args") for a in args]
    neg = bool(raw.get("neg", False))
    return {"pred": pred, "args": parsed_args, "neg": neg}


def _render_atom(atom: dict) -> str:
    call = atom["pred"] + "(" + ",".join(atom["args"]) + ")"
    return ("~" + call) if atom.get("neg") else call


def _render_rule_object(raw_rule: dict, idx: int, symbol_sigs: dict[str, tuple[tuple[str, ...], str]]) -> str:
    if not isinstance(raw_rule, dict):
        raise JSONIRCompilationError(f"rules[{idx}] must be a string or object.")
    q_raw = raw_rule.get("forall", [])
    if_raw = raw_rule.get("if", [])
    then_raw = raw_rule.get("then", [])
    if not isinstance(q_raw, list) or not isinstance(if_raw, list) or not isinstance(then_raw, list):
        raise JSONIRCompilationError(f"rules[{idx}] fields forall/if/then must be lists.")

    quants = [_normalize_quant_entry(q, idx) for q in q_raw]
    quant_type_map = {v: t for v, t in quants}

    def ensure_var_for_type(expected_type: str) -> str:
        for v, t in quants:
            if t == expected_type:
                return v
        base = expected_type[:1].lower() or "v"
        cand = base
        k = 2
        while cand in quant_type_map:
            cand = base + str(k)
            k += 1
        quants.append((cand, expected_type))
        quant_type_map[cand] = expected_type
        return cand

    def typed_atom(raw_atom, side: str) -> dict:
        atom = _normalize_atom(raw_atom, idx, side)
        sig = symbol_sigs.get(atom["pred"])
        if not sig:
            return atom
        exp_args = list(sig[0])
        args = list(atom["args"])
        if len(args) < len(exp_args):
            for t in exp_args[len(args):]:
                args.append(ensure_var_for_type(t))
        elif len(args) > len(exp_args):
            args = args[: len(exp_args)]
        typed_args = []
        for a, t in zip(args, exp_args):
            if quant_type_map.get(a) == t:
                typed_args.append(a)
            else:
                typed_args.append(ensure_var_for_type(t))
        atom["args"] = typed_args
        return atom

    if_atoms = [typed_atom(a, "if") for a in if_raw]
    then_atoms = [typed_atom(a, "then") for a in then_raw]
    if not then_atoms:
        raise JSONIRCompilationError(f"rules[{idx}] must contain at least one consequent atom in 'then'.")

    ant = "true" if not if_atoms else " & ".join(_render_atom(a) for a in if_atoms)
    cons = " & ".join(_render_atom(a) for a in then_atoms)
    if quants:
        qtxt = ", ".join(v + " in " + t for v, t in quants)
        return "! " + qtxt + ": (" + ant + ") => (" + cons + ")."
    return "(" + ant + ") => (" + cons + ")."


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
    for i, t in enumerate(types_raw):
        if isinstance(t, dict):
            t = t.get("name")
        types.append(_validate_type_name(t))
    if not types:
        raise JSONIRCompilationError("types cannot be empty.")
    if len(set(types)) != len(types):
        raise JSONIRCompilationError("Duplicate type declarations in JSON IR.")

    predicates = [_validate_symbol_decl(p, "predicates[" + str(i) + "]") for i, p in enumerate(predicates_raw)]
    functions = [_validate_symbol_decl(f, "functions[" + str(i) + "]") for i, f in enumerate(functions_raw)]

    type_set = set(types) | _SCALAR_TYPES
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
    for i, r in enumerate(rules_raw):
        if isinstance(r, str):
            if not r.strip():
                raise JSONIRCompilationError("rules[" + str(i) + "] must be a non-empty string.")
            rr = _normalize_rule_text(r)
        else:
            rr = _render_rule_object(r, i, seen_names)
            rr = _normalize_rule_text(rr)
        if not rr.endswith("."):
            rr += "."
        rules.append(rr)

    # Reconcile rule symbol calls to declared symbols before final validation.
    all_calls: list[RuleCall] = []
    for r in rules:
        all_calls.extend(_rule_calls(r))
    rewrites = _build_rewrite_map(set(seen_names.keys()), all_calls)
    rules = [_rewrite_rule_symbols(r, rewrites) for r in rules]

    # Ensure rules only use declared symbols; if unresolved, synthesize conservative Bool predicates
    # to keep the pipeline moving (repair loop can still improve semantics).
    declared = set(seen_names.keys())
    undeclared_with_arity: dict[str, int] = {}
    for r in rules:
        for call in _rule_calls(r):
            name = call.name
            if name not in declared:
                undeclared_with_arity[name] = max(undeclared_with_arity.get(name, 0), call.arity)
    if undeclared_with_arity:
        synthesized: list[dict] = []
        for name, arity in sorted(undeclared_with_arity.items()):
            args = ["Person"] * arity
            synthesized.append({"name": name, "args": args, "returns": "Bool"})
            predicates.append(SymbolDecl(name=name, args=args, returns="Bool"))
        for d in synthesized:
            seen_names[d["name"]] = (tuple(d["args"]), d["returns"])

    return {
        "types": types,
        "predicates": [{"name": d.name, "args": d.args, "returns": d.returns} for d in predicates],
        "functions": [{"name": d.name, "args": d.args, "returns": d.returns} for d in functions],
        "rules": rules,
    }


def render_json_ir_to_fo(ir: dict) -> str:
    norm = normalize_json_ir(ir)
    lines: list[str] = ["vocabulary V {"]
    for t in norm["types"]:
        lines.append("  type " + t)

    for p in norm["predicates"]:
        domain = " * ".join(p["args"]) if p["args"] else "()"
        lines.append("  " + p["name"] + ": " + domain + " -> " + p["returns"])
    for f in norm["functions"]:
        domain = " * ".join(f["args"]) if f["args"] else "()"
        lines.append("  " + f["name"] + ": " + domain + " -> " + f["returns"])
    lines.append("}")
    lines.append("")
    lines.append("theory T:V {")
    for r in norm["rules"]:
        lines.append("  " + r)
    lines.append("}")
    return "\n".join(lines).strip() + "\n"

