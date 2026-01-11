from pipeline.rendering.explanations import explain_liable

# Converts symbolic results into a user-facing natural-language answer.
# Delegates predicate-specific explanation generation to pipeline/rendering/explanations.py.
# Keeps the rest of the pipeline independent from presentation formatting.
#
# Params:
#   case (dict): Normalized case facts.
#   query (dict): Normalized query.
#   sat (bool): Whether the composed FO(.) theory is satisfiable for the case.
#   result (dict): Symbolic result payload returned by pipeline/symbolic/router.py.
#
# Returns:
#   dict: {"answer": str, "explanation": str | None}
#         - answer: short direct response
#         - explanation: optional explanation text (when query["explain"] is True)

def render_answer(case, query, sat, result, base_kb_text=None):
    if not sat:
        return {"answer": "The knowledge base is inconsistent with the case facts (UNSAT).", "explanation": None}

    if query["predicate"] == "liable":
        if query["mode"] == "set":
            liable_set = result.get("liable_set") or []
            if liable_set:
                ans = "Liable parties: " + ", ".join(liable_set) + "."
            else:
                ans = "No parties are liable."
        else:
            target = result.get("target")
            is_li = result.get("is_liable")
            ans = ("Yes. " if is_li else "No. ") + (str(target) + " is " + ("" if is_li else "not ") + "liable.")

        explanation = None
        if query.get("explain"):
            explanation = explain_liable(case, query, result, base_kb_text=base_kb_text)

        return {"answer": ans, "explanation": explanation}

    return {"answer": "Unsupported query.", "explanation": None}
