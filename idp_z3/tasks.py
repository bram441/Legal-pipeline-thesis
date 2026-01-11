# idp_z3/tasks.py

from .idp_backend import run_idp
from .case_structure import build_structure_block, build_structure_block_from_facts


def _compose_program(case, base_kb_text):
    if not base_kb_text:
        raise ValueError("base_kb_text is required")

    if isinstance(case, dict) and "facts" in case:
        structure = build_structure_block_from_facts(case["facts"])
    else:
        structure = build_structure_block(
            case["parties"],
            case["negligent"],
            case["caused_damage"],
        )

    # IMPORTANT: do not touch/normalize the KB text.
    return base_kb_text.strip() + "\n\n" + structure + "\n"


def satisfiable_check(case, base_kb_text):
    fo_code = _compose_program(case, base_kb_text)
    result = run_idp(fo_code, max_models=1)
    return {"sat": bool(result.get("sat"))}


def satisfiable_check_with_constraint(case, base_kb_text, constraint_fo):
    if not isinstance(constraint_fo, str) or not constraint_fo.strip():
        raise ValueError("constraint_fo must be a non-empty string")

    fo_code = _compose_program(case, base_kb_text)

    constraint = constraint_fo.strip()
    if not constraint.endswith("."):
        constraint = constraint + "."

    fo_code = fo_code + "\n" + (
        "theory Q:V {\n"
        "  " + constraint + "\n"
        "}\n"
    )

    result = run_idp(fo_code, max_models=1)
    return {"sat": bool(result.get("sat"))}
