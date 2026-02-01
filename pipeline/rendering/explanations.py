# pipeline/rendering/explanations.py
from pipeline.rendering.nl_paraphrase import paraphrase_liability_explanation, NLExplanationError

def _kb_theory_snippet(kb_text):
    """
    Return a human-readable snippet from the KB theory block.
    We keep it simple + grounded: first non-empty non-comment line inside theory T:V.
    """
    if not kb_text:
        return None

    lines = kb_text.splitlines()
    in_theory = False

    for ln in lines:
        s = ln.strip()

        if s.startswith("theory ") and "T:V" in s:
            in_theory = True
            continue

        if in_theory:
            if s.startswith("}"):
                in_theory = False
                continue
            if not s or s.startswith("//"):
                continue
            return s

    return None


def explain_generic(case, query, sat, result, base_kb_text=None):
    rule = _kb_theory_snippet(base_kb_text) or "(KB rule snippet unavailable)"
    parts = []
    parts.append("Rule(s) from KB:")
    parts.append(rule)
    parts.append("")
    parts.append("Relevant case facts:")

    if isinstance(case, dict) and "facts" in case:
        facts = list(case.get("facts") or [])
        if facts:
            parts.extend(facts)
        else:
            parts.append("(none)")
    else:
        parts.append("(case facts unavailable)")

    # Include constraint used by deduction if available (very useful for debugging)
    if isinstance(result, dict) and result.get("constraint"):
        parts.append("")
        parts.append("Constraint checked:")
        parts.append(str(result.get("constraint")) + ".")

    # Include 3-valued status
    if isinstance(result, dict) and "possible" in result and "certain" in result:
        parts.append("")
        parts.append("Status:")
        parts.append("possible = " + str(bool(result.get("possible"))))
        parts.append("certain = " + str(bool(result.get("certain"))))

        # Optional grounded NL paraphrase (LLM). Does NOT affect solver output.
    try:
        conclusion = None
        if isinstance(result, dict) and result.get("atom"):
            # Keep conclusion strictly grounded to the computed status.
            if result.get("certain") is True:
                conclusion = "Conclusion: " + str(result.get("atom")) + " is entailed."
            elif result.get("possible") is False:
                conclusion = "Conclusion: not(" + str(result.get("atom")) + ") is entailed."
            else:
                conclusion = "Conclusion: " + str(result.get("atom")) + " is not determined."

        fact_lines = list((case or {}).get("facts") or []) if isinstance(case, dict) else []
        rule_line = _kb_theory_snippet(base_kb_text) or "(KB rule snippet unavailable)"

        if conclusion:
            nl = paraphrase_liability_explanation(rule_line, fact_lines, conclusion)
            parts.append("")
            parts.append("Natural-language paraphrase:")
            parts.append(nl)

    except NLExplanationError:
        # Silent by design: explanation still works without LLM.
        pass

    return "\n".join(parts)
