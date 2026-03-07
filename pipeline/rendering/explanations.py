# pipeline/rendering/explanations.py
import re

from pipeline.rendering.nl_paraphrase import (
    paraphrase_liability_explanation,
    paraphrase_range_explanation,
    NLExplanationError,
)


def _extract_rules_for_symbol(kb_text, symbol):
    """Extract KB theory lines that define the given symbol. Used for get_range explanation."""
    if not kb_text or not symbol:
        return ""
    symbol_escaped = re.escape(symbol.strip())
    lines = kb_text.splitlines()
    in_theory = False
    out = []
    for ln in lines:
        s = ln.strip()
        if s.startswith("theory ") and "T:V" in s:
            in_theory = True
            continue
        if in_theory:
            if s.startswith("}"):
                break
            if s and not s.startswith("//") and re.search(r"\b" + symbol_escaped + r"\b", s):
                out.append(ln.strip())
    return "\n".join(out) if out else "(no rules found for " + symbol + ")"


def _atom_predicate(atom):
    """Extract predicate name from atom string like 'punishedArt398(pieter)' -> 'punishedArt398'."""
    if not atom or not isinstance(atom, str):
        return ""
    m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(", atom.strip())
    return m.group(1) if m else ""


def _extract_rule_for_predicate(kb_text, predicate):
    """Extract the FULL rule that defines the predicate (conclusion in <=> or =>).
    Returns the quantifier line + full body until the period. Required for correct explanation.
    """
    if not kb_text or not predicate:
        return ""
    pred_escaped = re.escape(predicate.strip())
    lines = kb_text.splitlines()
    in_theory = False
    last_quantifier = None
    collecting = False
    out = []

    for ln in lines:
        s = ln.strip()
        if s.startswith("theory ") and "T:V" in s:
            in_theory = True
            continue
        if not in_theory:
            continue
        if s.startswith("}"):
            break
        if not s or s.startswith("//"):
            continue

        if re.match(r"^!\s+\w+\s+in\s+\w+\s*:?\s*$", s):
            last_quantifier = s
            collecting = False
            continue

        if re.search(r"\b" + pred_escaped + r"\s*\(", s) and ("<=>" in s or "=>" in s):
            collecting = True
            if last_quantifier:
                out.append(last_quantifier)
            out.append(ln.strip())
            if s.rstrip().endswith("."):
                break
            continue

        if collecting:
            out.append(ln.strip())
            if s.rstrip().endswith("."):
                break

    return "\n".join(out) if out else ""


def _kb_theory_snippet(kb_text):
    """Deprecated: returns only first line. Use _extract_rule_for_predicate for predicate-specific rules."""
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
                break
            if s and not s.startswith("//"):
                return s
    return None


def explain_generic(case, query, sat, result, base_kb_text=None):
    predicate = (query.get("predicate") or "").strip() or _atom_predicate(result.get("atom"))
    rule = _extract_rule_for_predicate(base_kb_text or "", predicate) if predicate else ""
    if not rule:
        rule = _kb_theory_snippet(base_kb_text) or "(KB rule unavailable)"
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
        rule_for_paraphrase = rule

        if conclusion:
            nl = paraphrase_liability_explanation(rule_for_paraphrase, fact_lines, conclusion)
            parts.append("")
            parts.append("Natural-language paraphrase:")
            parts.append(nl)

    except NLExplanationError:
        # Silent by design: explanation still works without LLM.
        pass

    return "\n".join(parts)


def explain_get_range(case, query, result, base_kb_text=None):
    """
    Generate grounded explanation for get_range. Uses ONLY: KB rules for the symbol,
    case facts, and the exact computed result. No invention.
    """
    symbol = (result or {}).get("symbol", "")
    rng = (result or {}).get("range", "")
    entity = (query or {}).get("entity", "")

    rules_block = _extract_rules_for_symbol(base_kb_text or "", symbol)
    facts = list((case or {}).get("facts") or []) if isinstance(case, dict) else []
    facts_block = "\n".join("- " + f for f in facts) if facts else "(no facts)"
    entity_part = f"({entity})" if entity else ""
    result_line = f"{symbol}{entity_part} = {rng}"

    parts = []
    parts.append("Rules from KB:")
    parts.append(rules_block)
    parts.append("")
    parts.append("Case facts:")
    parts.append(facts_block)
    parts.append("")
    parts.append("Computed result:")
    parts.append(result_line)

    try:
        nl = paraphrase_range_explanation(rules_block, facts_block, result_line)
        parts.append("")
        parts.append("Explanation:")
        parts.append(nl)
    except NLExplanationError:
        pass

    return "\n".join(parts)


def explain_set(case, query, result, base_kb_text=None):
    """Grounded explanation for set queries. Reuses explain_generic pattern."""
    return explain_generic(case, query, True, result, base_kb_text=base_kb_text)


def explain_on_demand(case, query, result, base_kb_text=None):
    """
    Generate explanation on demand. Dispatches by query type. 100% grounded:
    uses ONLY the actual KB rules, case facts, and symbolic result.
    """
    if not result or not case or not query:
        return "Explanation unavailable (missing case, query, or result)."

    qtype = (query.get("type") or "").strip().lower()
    intent = (query.get("intent") or "").strip().lower()

    if qtype == "intent" and intent == "get_range":
        return explain_get_range(case, query, result, base_kb_text=base_kb_text)

    if qtype == "predicate" and (query.get("mode") or "").strip().lower() == "set":
        return explain_set(case, query, result, base_kb_text=base_kb_text)

    if qtype == "predicate" and (query.get("mode") or "").strip().lower() == "boolean":
        return explain_generic(case, query, True, result, base_kb_text=base_kb_text)

    return "Explanation not available for this query type."
