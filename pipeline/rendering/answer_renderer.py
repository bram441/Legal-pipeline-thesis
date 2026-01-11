from pipeline.rendering.explanations import explain_liable

# pipeline/rendering/answer_renderer.py
#
# Converts symbolic results into a user-facing natural-language answer.
# Delegates predicate-specific explanation generation to pipeline/rendering/explanations.py.

def render_answer(case, query, sat, result, base_kb_text=None):
    if query.get("type") == "intent":
        intent = query.get("intent")

        if intent == "satisfiable":
            if sat:
                return {"answer": "Yes. The law and case facts are satisfiable (a model exists).", "explanation": None}
            return {"answer": "No. The law and case facts are inconsistent (no model exists).", "explanation": None}

        return {"answer": "Unsupported intent.", "explanation": None}

    if query["type"] == "predicate":
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
