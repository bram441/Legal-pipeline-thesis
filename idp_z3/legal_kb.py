# idp_z3/legal_kb.py

from .idp_backend import run_idp
from .case_structure import build_structure_block


# Composes a complete FO(.) program by combining:
#   (1) the base KB (vocabulary + theory) and
#   (2) the case-specific structure (facts).
# This keeps the "law" reusable and isolates per-case data.
#
# Params:
#   parties (list[str]): Domain constants for Party.
#   negligent (list[str]): Parties marked negligent in this case.
#   caused_damage (list[str]): Parties marked as having caused damage in this case.
#
# Returns:
#   str: Full FO(.) program (base KB + structure) ready for IDP.from_str.

def build_fo_program(parties, negligent, caused_damage, base_kb_text):
    """
    Composes full FO(.) program = base KB (law) + case structure.
    base_kb_text must contain vocabulary+theory only.
    """
    if not base_kb_text:
        raise ValueError("base_kb_text is required (no hardcoded KB fallback).")

    struct_block = build_structure_block(parties, negligent, caused_damage)
    return base_kb_text.strip() + "\n\n" + struct_block


# Extracts the extension of the predicate `liable` from IDP's expanded model output.
# This is a lightweight text parser that searches for a line like:
#   liable := {alice, bob}.
# and returns the set of constants inside the braces.
#
# Params:
#   models (list[str]): Expanded model(s) as text returned by the IDP backend.
#
# Returns:
#   set[str]: Party identifiers that are liable in (typically) the first expanded model.
#            (This is "naive" and can be generalized later to multiple models/uncertainty.)

def parse_liable_from_models(models):
    liable_set = set()

    for line in "\n".join(models).splitlines():
        line = line.strip()
        if line.startswith("liable :="):
            _, right = line.split(":=", 1)
            right = right.strip()
            if right.endswith("."):
                right = right[:-1].strip()
            if right.startswith("{") and right.endswith("}"):
                inner = right[1:-1].strip()
                if inner:
                    parts = [p.strip() for p in inner.split(",")]
                    liable_set.update(parts)
            break

    return liable_set


# Runs the IDP pipeline for the current liability toy domain:
# builds FO(.) program, calls the IDP backend, and returns SAT + liable parties.
# This is the "symbolic solve" function for the current predicate of interest.
#
# Params:
#   parties (list[str]): Domain constants for Party.
#   negligent (list[str]): Parties negligent in the case.
#   caused_damage (list[str]): Parties that caused damage in the case.
#
# Returns:
#   tuple[bool, set[str]]:
#     - sat (bool): Whether the FO(.) theory is satisfiable given the case facts.
#     - liable_set (set[str]): Parties inferred to be liable (empty if UNSAT or none inferred).

def decide_liability(parties, negligent, caused_damage, base_kb_text):
    fo_code = build_fo_program(parties, negligent, caused_damage, base_kb_text=base_kb_text)
    result = run_idp(fo_code, max_models=5)

    if not result["sat"]:
        return False, set()

    liable_set = parse_liable_from_models(result["models"])
    return True, liable_set



# Convenience wrapper that extracts the required fields from a normalized `case` dict
# and calls `decide_liability`. Keeps upstream pipeline code cleaner.
#
# Params:
#   case (dict): Normalized case object with keys:
#     - "parties": list[str]
#     - "negligent": list[str]
#     - "caused_damage": list[str]
#
# Returns:
#   tuple[bool, set[str]]: Same as decide_liability(sat, liable_set).


def decide_liability_from_case(case, base_kb_text):
    parties = case["parties"]
    negligent = case["negligent"]
    caused_damage = case["caused_damage"]
    return decide_liability(parties, negligent, caused_damage, base_kb_text=base_kb_text)


if __name__ == "__main__":
    parties = ["alice", "bob"]
    negligent = ["alice"]
    caused_damage = ["alice", "bob"]

    sat, liable = decide_liability(parties, negligent, caused_damage)

    print("SAT?", sat)
    print("Liable parties:", ", ".join(sorted(liable)) if liable else "none")
