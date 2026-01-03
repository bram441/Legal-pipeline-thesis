from pipeline.rendering.explanations import explain_liable


def render_answer(case, query, sat, result):
    if not sat:
        return {
            "answer": "The extracted facts lead to an inconsistent knowledge base, so the question cannot be answered.",
            "explanation": None,
        }

    if query["type"] != "predicate":
        return {"answer": "Unsupported query type.", "explanation": None}

    explanation_text = None

    if query["predicate"] == "liable":
        if query["mode"] == "set":
            liable = result.get("liable_set", [])
            if not liable:
                answer = "Based on the extracted facts and the toy rule, no party is liable."
            elif len(liable) == 1:
                answer = "Based on the extracted facts and the toy rule, " + liable[0] + " is liable."
            else:
                answer = "Based on the extracted facts and the toy rule, the liable parties are: " + ", ".join(liable) + "."
        else:
            target = result.get("target", "")
            is_liable = bool(result.get("is_liable", False))
            if is_liable:
                answer = "Yes. Based on the extracted facts and the toy rule, " + target + " is liable."
            else:
                answer = "No. Based on the extracted facts and the toy rule, " + target + " is not liable."

        if query.get("explain", False):
            explanation_text = explain_liable(case, query, result)

        return {"answer": answer, "explanation": explanation_text}

    return {"answer": "Unsupported predicate: " + str(query["predicate"]), "explanation": None}
