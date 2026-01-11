# idp_z3/predicate_solver.py

import re
from idp_z3.tasks import satisfiable_check_with_constraint


_number = re.compile(r"^-?\d+(\.\d+)?$")


def _to_idp_term(x):
    """
    Convert a token to an IDP-safe term:
    - If already single-quoted 'alice', keep it.
    - If numeric, keep it.
    - Else, convert to a single-quoted domain element: 'alice'
      (escape internal single quotes by doubling: O'Brien -> 'o''brien')
    """
    s = str(x).strip()
    if not s:
        raise ValueError("Empty argument")

    if s.startswith("'") and s.endswith("'"):
        return s

    if _number.match(s):
        return s

    s = s.lower()
    s = s.replace("'", "''")
    return "'" + s + "'"


def _format_atom(predicate, args):
    rendered_args = []
    for a in args:
        rendered_args.append(_to_idp_term(a))
    return predicate + "(" + ",".join(rendered_args) + ")"


def evaluate_atom(case, base_kb_text, predicate, args):
    atom = _format_atom(predicate, args)

    sat_atom = satisfiable_check_with_constraint(
        case=case,
        base_kb_text=base_kb_text,
        constraint_fo=atom
    )

    sat_not_atom = satisfiable_check_with_constraint(
        case=case,
        base_kb_text=base_kb_text,
        constraint_fo="~(" + atom + ")"
    )

    possible = bool(sat_atom.get("sat"))
    not_atom_possible = bool(sat_not_atom.get("sat"))

    certain = False
    if possible and not not_atom_possible:
        certain = True

    return {
        "atom": atom,
        "possible": possible,
        "certain": certain,
    }
