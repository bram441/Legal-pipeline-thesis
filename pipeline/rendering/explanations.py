# Produces a minimal human-readable explanation for liability results
# under the current toy rule(s). This is intentionally simple and should evolve
# as you add more rules/predicates (e.g., rule labels, missing-premise reporting).
#
# Params:
#   case (dict): Normalized case facts (e.g., parties, negligent, caused_damage).
#   query (dict): Normalized query (predicate/mode/args/explain).
#   result (dict): Symbolic result from the router (e.g., liable_set / is_liable).
#
# Returns:
#   str: Explanation text describing why the answer holds (or what premise is missing).

# pipeline/rendering/explanations.py

def _kb_rule_snippet(kb_text):
    """
    Returns a human-readable snippet of the actual rule(s) from the KB theory.
    Preference order:
      1) first non-comment line in theory containing 'liable('
      2) first non-comment line in theory containing '<=>' or '=>' or '<-'
      3) fallback: first non-empty non-comment line containing 'liable(' anywhere
    """
    if not kb_text:
        return None

    lines = kb_text.splitlines()

    # Find theory block boundaries (naive but works for our current format)
    in_theory = False
    theory_lines = []

    for ln in lines:
        s = ln.strip()

        if s.startswith("theory ") and "T:V" in s:
            in_theory = True
            continue

        if in_theory:
            if s.startswith("}"):
                in_theory = False
                continue

            # skip empty/comment
            if not s or s.startswith("//"):
                continue

            theory_lines.append(s)

    # 1) Look for a liability rule line
    for s in theory_lines:
        if "liable(" in s:
            return s

    # 2) Any implication/equivalence line
    for s in theory_lines:
        if "<=>" in s or "=>" in s or "<-" in s:
            return s

    # 3) Fallback: any line containing liable(
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("//") and "liable(" in s:
            return s

    return None



def explain_liable(case, query, result, base_kb_text=None):
    rule = _kb_rule_snippet(base_kb_text)
    header = "Rule(s) from KB:\n" + (rule if rule else "(KB rule snippet unavailable)")

    if query["mode"] == "set":
        liable_set = result.get("liable_set") or []
        return header + "\n\nDerived liable parties: " + (", ".join(liable_set) if liable_set else "none") + "."

    target = result.get("target")
    is_liable = result.get("is_liable")

    if is_liable:
        return header + "\n\n" + str(target) + " is liable given the case facts."
    return header + "\n\n" + str(target) + " is not liable given the case facts."
