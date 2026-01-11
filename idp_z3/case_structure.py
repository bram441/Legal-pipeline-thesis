# idp_z3/case_structure.py

# Builds the FO(.) "structure" block (case facts) for IDP-Z3.
# This encodes the concrete parties and predicate extensions for the current case,
# matching the vocabulary used in the base KB (V).
#
# Params:
#   parties (list[str]): Domain constants for type Party (e.g., ["alice", "bob"]).
#   negligent (list[str]): Parties for which negligent(p) is true.
#   caused_damage (list[str]): Parties for which causedDamage(p) is true.
#
# Returns:
#   str: A FO(.) structure block (e.g., `structure S:V { ... }`) that can be concatenated
#        with the base KB (vocabulary + theory) into a full FO(.) program.

def _mk_set(elems):
    if not elems:
        return "{}"
    return "{" + ", ".join(elems) + "}"


def build_structure_block(parties, negligent, caused_damage):
    party_set = _mk_set(parties)
    negligent_set = _mk_set(negligent)
    caused_set = _mk_set(caused_damage)

    return f"""
structure S:V {{
  Party := {party_set}.
  negligent := {negligent_set}.
  causedDamage := {caused_set}.
}}
""".strip()
