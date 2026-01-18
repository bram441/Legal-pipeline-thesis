# pipeline/rendering/explanations.py

from pipeline.rendering.llm_nl_explainer import paraphrase_liability_explanation, NLExplanationError


def _kb_theory_snippet(kb_text):
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
        parts.extend(facts if facts else ["(none)"])
    else:
        parts.append("(case facts unavailable)")

    if isinstance(result, dict) and result.get("constraint"):
        parts.append("")
        parts.append("Constraint checked:")
        parts.append(str(result.get("constraint")) + ".")

    if isinstance(result, dict) and "possible" in result and "certain" in result:
        parts.append("")
        parts.append("Status:")
        parts.append("possible = " + str(bool(result.get("possible"))))
        parts.append("certain = " + str(bool(result.get("certain"))))

    # -------- NL paraphrase (optional) --------
    try:
        conclusion = None

        atom = result.get("atom") if isinstance(result, dict) else None
        args = query.get("args") or []

        if atom and len(args) == 1:
            grounded_atom = f"{query.get('predicate')}({args[0]})"
        else:
            grounded_atom = atom

        if grounded_atom:
            if result.get("certain") is True:
                conclusion = "Conclusion: " + grounded_atom + " is entailed."
            elif result.get("possible") is False:
                conclusion = "Conclusion: not(" + grounded_atom + ") is entailed."
            else:
                conclusion = "Conclusion: " + grounded_atom + " is not determined."

        fact_lines = list((case or {}).get("facts") or []) if isinstance(case, dict) else []
        rule_line = rule

        if conclusion:
            nl = paraphrase_liability_explanation(rule_line, fact_lines, conclusion)
            parts.append("")
            parts.append("Natural-language paraphrase:")
            parts.append(nl)

    except NLExplanationError:
        pass

    return "\n".join(parts)
