# idp_z3/kb_base.py

# Returns the reusable (static) base knowledge base in FO(.) form: vocabulary + theory.
# This file represents the "law side" of the system: domain predicates and general rules.
# Case-specific facts should NOT be added here; they belong in the structure block.
#
# Params:
#   (none)
#
# Returns:
#   str: FO(.) code containing the vocabulary V and theory T (laws/rules) only.
#        This string is intended to be concatenated with a case structure block.

def get_base_kb():
    """
    Static, reusable KB part: vocabulary + theory (laws/rules).
    No case facts go here.
    """

    vocab = """
vocabulary V {
  type Party
  negligent: Party -> Bool
  causedDamage: Party -> Bool
  liable: Party -> Bool
}
""".strip()

    theory = """
theory T:V {
  // A party is liable iff they are negligent and caused damage
  ! p in Party: liable(p) <=> negligent(p) & causedDamage(p).
}
""".strip()

    return vocab + "\n\n" + theory
