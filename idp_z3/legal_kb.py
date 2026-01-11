# idp_z3/legal_kb.py

from .idp_backend import run_idp
from .case_structure import build_structure_block, build_structure_block_from_facts


def build_fo_program(parties, negligent, caused_damage, base_kb_text):
    """
    Legacy demo builder: Composes full FO(.) program = base KB (law) + legacy case structure.
    base_kb_text must contain vocabulary+theory only.
    """
    if not base_kb_text:
        raise ValueError("base_kb_text is required (no hardcoded KB fallback).")

    struct_block = build_structure_block(parties, negligent, caused_damage)
    return base_kb_text.strip() + "\n\n" + struct_block


def build_fo_program_from_case(case, base_kb_text):
    """
    New generic builder:
    - If case has "facts": uses build_structure_block_from_facts
    - Else: falls back to legacy demo format
    """
    if not base_kb_text:
        raise ValueError("base_kb_text is required (no hardcoded KB fallback).")

    if isinstance(case, dict) and "facts" in case:
        struct_block = build_structure_block_from_facts(case["facts"])
        return base_kb_text.strip() + "\n\n" + struct_block

    # legacy fallback
    parties = case["parties"]
    negligent = case["negligent"]
    caused_damage = case["caused_damage"]
    return build_fo_program(parties, negligent, caused_damage, base_kb_text)


def parse_liable_from_models(models):
    """
    Extracts the extension of the predicate `liable` from IDP's expanded model output.

    NOTE: This is still a toy/demo parser.
    """
    liable_set = set()

    if not models:
        return liable_set

    # Search through the model chunks for a line that contains "liable := { ... }"
    for chunk in models:
        if not isinstance(chunk, str):
            continue

        for raw_line in chunk.splitlines():
            line = raw_line.strip()

            # Typical IDP model output often contains: "liable := {alice,bob}."
            if line.startswith("liable") and ":=" in line:
                # naive parse of {...}
                lb = line.find("{")
                rb = line.find("}", lb + 1)
                if lb >= 0 and rb > lb:
                    inner = line[lb + 1 : rb].strip()
                    if inner:
                        parts = [p.strip() for p in inner.split(",")]
                        liable_set.update([p for p in parts if p])
                return liable_set

    return liable_set


def decide_liability(parties, negligent, caused_damage, base_kb_text):
    """
    Legacy demo entrypoint: returns (sat, liable_set).
    """
    fo_code = build_fo_program(parties, negligent, caused_damage, base_kb_text=base_kb_text)
    result = run_idp(fo_code, max_models=1)
    sat = bool(result.get("sat"))
    liable = parse_liable_from_models(result.get("models") or [])
    return sat, liable


def decide_liability_from_case(case, base_kb_text):
    """
    NEW: Works with both:
      - legacy case: {"parties":[...], "negligent":[...], "caused_damage":[...]}
      - schema-driven case: {"facts":[ "negligent(alice).", "causedDamage(alice)." ]}
    """
    fo_code = build_fo_program_from_case(case, base_kb_text=base_kb_text)
    result = run_idp(fo_code, max_models=1)
    sat = bool(result.get("sat"))
    liable = parse_liable_from_models(result.get("models") or [])
    return sat, liable


if __name__ == "__main__":
    parties = ["alice", "bob"]
    negligent = ["alice"]
    caused_damage = ["alice", "bob"]

    # NOTE: this will require a base KB text to run, so it's not a standalone runnable demo anymore.
    print("This module is intended to be called via the pipeline.")
