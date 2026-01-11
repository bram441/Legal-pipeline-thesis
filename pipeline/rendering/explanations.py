# Produces a minimal human-readable explanation for liability results
# under the current toy rule(s). This is intentionally simple and should evolve
# as you add more rules/predicates (e.g., rule labels, missing-premise reporting).
#
# NEW (incremental): optional LLM-based paraphrase layer for explanations.
# The paraphrase is always grounded because we *always* include the exact FO(.) rule snippet
# and the exact case facts used for the explanation. The LLM only rewrites those into NL.
#
# Params:
#   case (dict): Normalized case facts (e.g., parties, negligent, caused_damage).
#   query (dict): Normalized query (predicate/mode/args/explain).
#   result (dict): Symbolic result from the router (e.g., liable_set / is_liable).
#
# Returns:
#   str: Explanation text describing why the answer holds (or what premise is missing).

# pipeline/rendering/explanations.py

from pipeline.rendering.llm_nl_explainer import paraphrase_liability_explanation, NLExplanationError


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


def _liability_fact_lines(case, parties):
    """
    Builds a list of exact fact-lines (strings) that are allowed in the NL paraphrase.
    If the case is schema-driven, we return those exact facts (grounded).
    """
    if isinstance(case, dict) and "facts" in case:
        return list(case.get("facts") or [])

    negligent_set = set(case.get("negligent") or [])
    caused_set = set(case.get("caused_damage") or [])

    facts = []
    for p in parties:
        facts.append("negligent(" + str(p) + ") = " + ("true" if p in negligent_set else "false") + ".")
        facts.append("causedDamage(" + str(p) + ") = " + ("true" if p in caused_set else "false") + ".")
    return facts



def explain_liable(case, query, result, base_kb_text=None):
    rule = _kb_rule_snippet(base_kb_text)
    rule_block = rule if rule else "(KB rule snippet unavailable)"
    header = "Rule(s) from KB:\n" + rule_block

    # --- Mode: set query (who is liable?) ---
    if query["mode"] == "set":
        liable_set = result.get("liable_set") or []
        parties = liable_set[:]  # explain only the derived liable parties for now
        fact_lines = _liability_fact_lines(case, parties) if parties else []

        conclusion = "Derived liable parties: " + (", ".join(liable_set) if liable_set else "none") + "."

        try:
            paraphrase = paraphrase_liability_explanation(rule_block, fact_lines, conclusion)
            return (
                header
                + "\n\nRelevant case facts:\n"
                + ("\n".join(fact_lines) if fact_lines else "(none)")
                + "\n\nParaphrase:\n"
                + paraphrase
            )
        except NLExplanationError:
            return header + "\n\n" + conclusion

    # --- Mode: individual query (is X liable?) ---
    target = result.get("target")
    is_liable = result.get("is_liable")

    parties = [target] if target is not None else []
    fact_lines = _liability_fact_lines(case, parties) if parties else []

    conclusion = str(target) + " is " + ("" if is_liable else "not ") + "liable."

    try:
        paraphrase = paraphrase_liability_explanation(rule_block, fact_lines, conclusion)
        return (
            header
            + "\n\nRelevant case facts:\n"
            + ("\n".join(fact_lines) if fact_lines else "(none)")
            + "\n\nParaphrase:\n"
            + paraphrase
        )
    except NLExplanationError:
        return header + "\n\n" + str(target) + " is " + ("" if is_liable else "not ") + "liable given the case facts."
