"""Runtime KB augmentation: case_given_* input predicates with bridge rules."""

from __future__ import annotations

import re
from typing import Any

from pipeline.kb.factual_case_input import case_given_predicate_name

MAX_BRIDGE_ARITY = 8
_VAR_NAMES = ["c", "fy", "fy1", "fy2", "x", "y", "z", "w"]
_ATOM = re.compile(r"^\s*(?:not|~|¬)?\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")


class CaseGivenBridgeArityError(ValueError):
    """Raised when a bridge predicate arity exceeds supported limits."""

    def __init__(self, predicate: str, arity: int, *, max_arity: int = MAX_BRIDGE_ARITY) -> None:
        self.predicate = predicate
        self.arity = arity
        self.max_arity = max_arity
        super().__init__(
            f"case_given bridge for '{predicate}' has arity {arity}; "
            f"maximum supported arity is {max_arity}."
        )


def _bridge_var_names(arity: int) -> list[str]:
    if arity <= 0:
        raise CaseGivenBridgeArityError("<unknown>", arity)
    if arity > MAX_BRIDGE_ARITY:
        raise CaseGivenBridgeArityError("<unknown>", arity)
    if arity <= len(_VAR_NAMES):
        return _VAR_NAMES[:arity]
    return [f"v{i}" for i in range(arity)]


def _fo_domain_sig(arg_types: list[str]) -> str:
    if not arg_types:
        return "()"
    if len(arg_types) == 1:
        return str(arg_types[0])
    return " * ".join(str(t) for t in arg_types)


def _bridge_rule_line(input_name: str, target_name: str, arg_types: list[str]) -> str:
    if not arg_types:
        raise CaseGivenBridgeArityError(target_name or input_name, 0)
    if len(arg_types) > MAX_BRIDGE_ARITY:
        raise CaseGivenBridgeArityError(target_name or input_name, len(arg_types))
    var_names = _bridge_var_names(len(arg_types))
    quants = [f"{var_names[i]} in {arg_types[i]}" for i in range(len(arg_types))]
    vars_part = ", ".join(quants)
    args_call = ", ".join(var_names)
    return (
        f"  ! {vars_part}: "
        f"(({input_name}({args_call})) => ({target_name}({args_call})))."
    )


def _find_matching_brace(text: str, open_brace_index: int) -> int:
    depth = 0
    for i in range(open_brace_index, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def inject_case_given_bridges_into_fo(fo_text: str, bridges: list[dict[str, Any]]) -> str:
    """Append case_given predicates to vocabulary and bridge rules to theory."""
    if not bridges or not fo_text:
        return fo_text

    vocab_lines: list[str] = []
    theory_lines: list[str] = []
    for b in bridges:
        inp = str(b.get("input_predicate") or "").strip()
        tgt = str(b.get("target_predicate") or "").strip()
        args = list(b.get("args_types") or b.get("arg_types") or [])
        if not inp or not tgt:
            continue
        if re.search(rf"\b{re.escape(inp)}\s*:", fo_text):
            continue
        try:
            vocab_lines.append(f"  {inp}: {_fo_domain_sig(args)} -> Bool")
            line = _bridge_rule_line(inp, tgt, args)
        except CaseGivenBridgeArityError:
            raise
        if line and line.strip() not in fo_text:
            theory_lines.append(line)

    if not vocab_lines and not theory_lines:
        return fo_text

    out = fo_text
    if vocab_lines and "vocabulary V {" in out:
        theory_idx = out.find("theory T:V {")
        vocab_region_end = theory_idx if theory_idx > 0 else len(out)
        vocab_region = out[:vocab_region_end]
        close = vocab_region.rfind("}")
        if close > 0:
            insertion = "\n" + "\n".join(vocab_lines) + "\n"
            out = vocab_region[:close] + insertion + vocab_region[close:] + out[vocab_region_end:]

    if "theory T:V {" in out and theory_lines:
        theory_start = out.find("theory T:V {")
        if theory_start >= 0:
            open_idx = out.find("{", theory_start)
            close_idx = _find_matching_brace(out, open_idx)
            if open_idx >= 0 and close_idx > open_idx:
                out = (
                    out[:close_idx]
                    + "\n"
                    + "\n".join(theory_lines)
                    + "\n"
                    + out[close_idx:]
                )
    return out


def extend_kb_schema_with_case_given(
    kb_schema: dict[str, Any],
    case_given_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a copy of kb_schema with case_given input predicates registered."""
    schema = dict(kb_schema) if isinstance(kb_schema, dict) else {}
    preds = list(schema.get("predicates") or [])
    existing = {str(p.get("name")) for p in preds if isinstance(p, dict) and p.get("name")}

    for entry in case_given_inputs or []:
        inp = str(entry.get("input_predicate") or "").strip()
        tgt = str(entry.get("target_predicate") or "").strip()
        if not inp or inp in existing:
            continue
        sig = entry.get("target_signature") or {}
        args = list(sig.get("args") or entry.get("args_types") or [])
        preds.append(
            {
                "name": inp,
                "kind": "input",
                "args": args,
                "returns": "Bool",
                "description": (
                    "Case-given factual input for "
                    + tgt
                    + " (externally asserted from case text, not a legal conclusion)."
                ),
                "case_input": True,
                "directly_observable": True,
            }
        )
        existing.add(inp)

    schema["predicates"] = preds
    schema["case_given_bridge_rules"] = [
        {
            "input_predicate": e.get("input_predicate"),
            "target_predicate": e.get("target_predicate"),
            "args_types": list(
                (e.get("target_signature") or {}).get("args")
                or e.get("args_types")
                or []
            ),
        }
        for e in (case_given_inputs or [])
        if e.get("input_predicate") and e.get("target_predicate")
    ]
    return schema


def build_case_given_inputs_from_assertions(
    assertions: list[dict[str, Any]],
    kb_schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize metadata records for bridge injection."""
    out: list[dict[str, Any]] = []
    for a in assertions or []:
        if not isinstance(a, dict):
            continue
        tgt = str(a.get("target_predicate") or a.get("symbol") or "").strip()
        inp = str(a.get("input_predicate") or case_given_predicate_name(tgt)).strip()
        sig = None
        for p in (kb_schema or {}).get("predicates") or []:
            if isinstance(p, dict) and p.get("name") == tgt:
                sig = p
                break
        out.append(
            {
                "target_predicate": tgt,
                "input_predicate": inp,
                "args": list(a.get("args") or []),
                "args_types": list((sig or {}).get("args") or []),
                "target_signature": sig or {"args": a.get("args") or []},
                "evidence_text": a.get("evidence_text") or "",
                "source": a.get("source") or "case_given",
                "assertion_kind": a.get("assertion_kind") or "factual_threshold_satisfaction",
            }
        )
    return out


def augment_kb_for_case_given(
    base_kb_text: str,
    kb_schema: dict[str, Any],
    case: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Augment FO + kb_schema when case carries case_given_factual_inputs metadata."""
    inputs = case.get("case_given_factual_inputs") or []
    if not inputs:
        return base_kb_text, kb_schema
    bridges = build_case_given_inputs_from_assertions(inputs, kb_schema)
    fo = inject_case_given_bridges_into_fo(base_kb_text, bridges)
    schema = extend_kb_schema_with_case_given(kb_schema, bridges)
    return fo, schema


def structure_asserts_only_case_given(
    case_facts: list[str],
    bridges: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """
    Return (ok, violations) ensuring structure facts assert case_given_P only, never bare P
    when a bridge maps case_given_P => P.
    """
    targets = {str(b.get("target_predicate") or "") for b in bridges or []}
    violations: list[str] = []
    for ln in case_facts or []:
        if not isinstance(ln, str):
            continue
        m = _ATOM.match(ln.strip())
        if not m:
            continue
        pred = m.group(1)
        if pred in targets:
            violations.append(ln.strip())
    return (len(violations) == 0, violations)
