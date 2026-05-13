# idp_z3/predicate_solver.py

import re
from idp_z3.tasks import satisfiable_check_with_constraint
from idp_z3.case_structure import _to_idp_elem
from idp_z3.case_structure import extract_constants_from_facts

_sig_line = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+?)\s*->\s*Bool\s*$")
_QUERY_WILDCARDS = frozenset({"?", "_", "*", "any"})

def _unquote_idp_atom(x):
    s = str(x).strip()
    if s.startswith("'") and s.endswith("'") and len(s) >= 2:
        s = s[1:-1].replace("''", "'")
    return s

def evaluate_set(case, base_kb_text, predicate):
    facts = (case or {}).get("facts") or []
    candidates = extract_constants_from_facts(facts)

    certain = []
    possible = []

    for c in candidates:
        # c is already IDP element like 'alice'
        # but evaluate_atom expects args in “raw form”, so pass unquoted
        raw = _unquote_idp_atom(c)
        res = evaluate_atom(case, base_kb_text, predicate, [raw])

        if res.get("possible"):
            possible.append(raw)
        if res.get("certain"):
            certain.append(raw)

    return {
        "predicate": predicate,
        "mode": "set",
        "certain": certain,
        "possible": possible,
    }

def _parse_predicate_arg_types_from_kb(base_kb_text, predicate_name):
    """
    Very small FO(.) vocabulary parser:
      predicate: Party -> Bool
      predicate: Party * Damage -> Bool
      predicate: (Party * Damage) -> Bool

    Returns list[str] of argument types.
    """
    in_vocab = False
    for raw in base_kb_text.splitlines():
        line = raw.strip()

        if line.startswith("vocabulary V"):
            in_vocab = True
            continue
        if in_vocab and line.startswith("}"):
            in_vocab = False
            continue
        if not in_vocab:
            continue

        # LLM output sometimes glues the closing '}' of vocabulary V { ... } onto the
        # last declaration line, e.g. "Pred: Person * Estate -> Bool}". Strip for parsing.
        if line.endswith("Bool}") and "->" in line and not line.startswith("}"):
            line = line[:-1].rstrip()

        m = _sig_line.match(line)
        if not m:
            continue

        name = m.group(1)
        if name != predicate_name:
            continue

        left = m.group(2).strip()

        # Remove optional parentheses
        if left.startswith("(") and left.endswith(")"):
            left = left[1:-1].strip()

        # Split on '*' for n-ary
        parts = [p.strip() for p in left.split("*") if p.strip()]
        if not parts:
            raise ValueError("Could not parse predicate signature for: " + predicate_name)

        return parts

    raise ValueError("Predicate not found in KB vocabulary: " + predicate_name)


def _build_selection_constraint(predicate, arg_types, args):
    """
    Build:
      - extra vocab lines: __sel0: T0 -> Bool, ...
      - extra struct lines: __sel0 := {alice}. ...
      - constraint: ? x0 in T0, x1 in T1: __sel0(x0) & __sel1(x1) & pred(x0,x1).

    No constants appear in the theory.
    """
    if len(arg_types) != len(args):
        raise ValueError("Arity mismatch for predicate " + predicate)

    sel_names = []
    extra_vocab = []
    extra_struct = []

    var_names = []
    constrained_positions = []
    for i, t in enumerate(arg_types):
        sel = "__sel" + str(i)
        var = "x" + str(i)
        var_names.append(var)
        raw_arg = str(args[i]).strip().lower() if i < len(args) else ""
        if raw_arg in _QUERY_WILDCARDS:
            continue
        sel_names.append(sel)
        constrained_positions.append(i)
        extra_vocab.append(sel + ": " + t + " -> Bool")
        extra_struct.append(sel + " := {" + _to_idp_elem(args[i]) + "}.")

    # Quantifier prefix
    if len(var_names) == 1:
        q = "? " + var_names[0] + " in " + arg_types[0] + ": "
    else:
        parts = []
        for i in range(len(var_names)):
            parts.append(var_names[i] + " in " + arg_types[i])
        q = "? " + ", ".join(parts) + ": "

    # Body: __sel0(x0) & ... & pred(x0,...)
    sel_conds = []
    for sel_idx, arg_idx in enumerate(constrained_positions):
        sel_conds.append(sel_names[sel_idx] + "(" + var_names[arg_idx] + ")")

    atom = predicate + "(" + ",".join(var_names) + ")"
    body = " & ".join(sel_conds + [atom])

    constraint = q + body
    return extra_vocab, extra_struct, constraint, atom


def evaluate_atom(case, base_kb_text, predicate, args):
    arg_types = _parse_predicate_arg_types_from_kb(base_kb_text, predicate)

    extra_vocab, extra_struct, constraint_pos, atom_rendered = _build_selection_constraint(
        predicate=predicate,
        arg_types=arg_types,
        args=args
    )

    sat_atom = satisfiable_check_with_constraint(
        case=case,
        base_kb_text=base_kb_text,
        constraint_fo=constraint_pos,
        extra_vocab_lines=extra_vocab,
        extra_struct_lines=extra_struct
    )

    sat_not_atom = satisfiable_check_with_constraint(
        case=case,
        base_kb_text=base_kb_text,
        constraint_fo="~(" + constraint_pos + ")",
        extra_vocab_lines=extra_vocab,
        extra_struct_lines=extra_struct
    )

    possible = bool(sat_atom.get("sat"))
    not_atom_possible = bool(sat_not_atom.get("sat"))

    certain = False
    if possible and not not_atom_possible:
        certain = True

    return {
        "atom": atom_rendered,          # pretty: liable(x0) form
        "constraint": constraint_pos,   # debug: the real FO constraint used
        "possible": possible,
        "certain": certain,
    }
