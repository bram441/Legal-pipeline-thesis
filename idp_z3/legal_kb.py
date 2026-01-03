from .idp_backend import run_idp


LEGAL_VOCAB_AND_RULES = """
vocabulary V {
  type Party
  negligent: Party -> Bool
  causedDamage: Party -> Bool
  liable: Party -> Bool
}

theory T:V {
  // A party is liable iff they are negligent and caused damage
  ! p in Party: liable(p) <=> negligent(p) & causedDamage(p).
}
"""


def build_structure_block(parties, negligent, caused_damage):
    party_elems = ", ".join(parties)
    negligent_elems = ", ".join(negligent)
    caused_elems = ", ".join(caused_damage)

    structure = f"""
        structure S:V {{
        Party := {{{party_elems}}}.
        negligent := {{{negligent_elems}}}.
        causedDamage := {{{caused_elems}}}.
        }}
        """
    return structure


def build_fo_program(parties, negligent, caused_damage):
    struct_block = build_structure_block(parties, negligent, caused_damage)
    return LEGAL_VOCAB_AND_RULES + "\n\n" + struct_block


def parse_liable_from_models(models):
    """
    Very naive parser for lines like:
      liable := {alice, bob}.

    Returns a set of party names that are liable
    in the *first* model (for this deterministic example).
    """
    liable_set = set()

    for line in "\n".join(models).splitlines():
        line = line.strip()
        if line.startswith("liable :="):
            # Example line: 'liable := {alice, bob}.'
            left, right = line.split(":=", 1)
            right = right.strip()
            # Drop trailing '.' and surrounding braces
            if right.endswith("."):
                right = right[:-1]
            if right.startswith("{") and right.endswith("}"):
                inner = right[1:-1].strip()
                if inner:
                    parts = [p.strip() for p in inner.split(",")]
                    liable_set.update(parts)
            break

    return liable_set


def decide_liability(parties, negligent, caused_damage):
    fo_code = build_fo_program(parties, negligent, caused_damage)

    result = run_idp(fo_code, max_models=5)

    if not result["sat"]:
        return False, set()

    liable_set = parse_liable_from_models(result["models"])
    return True, liable_set


def decide_liability_from_case(case):
    parties = case["parties"]
    negligent = case["negligent"]
    caused_damage = case["caused_damage"]

    return decide_liability(parties, negligent, caused_damage)



if __name__ == "__main__":
    # Example case:
    parties = ["alice", "bob"]
    negligent = ["alice"]
    caused_damage = ["alice", "bob"]

    sat, liable = decide_liability(parties, negligent, caused_damage)

    print("SAT?", sat)
    print("Liable parties:", ", ".join(sorted(liable)) if liable else "none")
