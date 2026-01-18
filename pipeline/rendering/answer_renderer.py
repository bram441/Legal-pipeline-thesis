# pipeline/rendering/answer_renderer.py

from pipeline.rendering.explanations import explain_generic


def _format_atom_for_display(query, atom):
    """
    Replace internal variable-based atom (e.g. liable(x0))
    with user-facing grounded atom (e.g. liable(alice)) when possible.
    """
    if not atom:
        return None

    args = query.get("args") or []
    if len(args) == 1:
        # Unary predicate case
        pred = query.get("predicate")
        if pred:
            return f"{pred}({args[0]})"

    return atom


def render_answer(case, query, sat, result, base_kb_text=None):
    # ---- Intent queries ----
    if query.get("type") == "intent":
        intent = (query.get("intent") or "").strip().lower()

        if intent == "satisfiable":
            if sat:
                return {
                    "answer": "Yes. The law and case facts are satisfiable (a model exists).",
                    "explanation": None,
                }
            return {
                "answer": "No. The law and case facts are inconsistent (no model exists).",
                "explanation": None,
            }

        if isinstance(result, dict) and result.get("error") == "intent_not_implemented":
            return {
                "answer": "Intent not implemented: " + str(result.get("intent")),
                "explanation": None,
            }

        return {"answer": "Unsupported intent.", "explanation": None}

    # ---- Predicate queries ----
    if query.get("type") == "predicate":
        mode = (query.get("mode") or "").strip().lower()

        if isinstance(result, dict) and result.get("error") == "intent_not_implemented":
            ans = "Cannot answer yet: intent not implemented (" + str(result.get("intent")) + ")."
            return {"answer": ans, "explanation": None}

        # ---------- Boolean ----------
        if mode == "boolean":
            atom = result.get("atom") if isinstance(result, dict) else None
            possible = result.get("possible") if isinstance(result, dict) else None
            certain = result.get("certain") if isinstance(result, dict) else None

            if possible is None or certain is None:
                return {"answer": "Unsupported predicate result format.", "explanation": None}

            display_atom = _format_atom_for_display(query, atom) or "The statement"

            if certain:
                ans = f"Yes. {display_atom} is entailed by the law and case facts."
            elif possible is False:
                ans = f"No. {display_atom} cannot hold given the law and case facts."
            else:
                ans = f"Unknown. {display_atom} is not determined by the law and case facts."

            explanation = None
            if query.get("explain"):
                explanation = explain_generic(case, query, sat, result, base_kb_text=base_kb_text)

            return {"answer": ans, "explanation": explanation}

        # ---------- Set ----------
        if mode == "set":
            if isinstance(result, dict) and "possible" in result and "certain" in result:
                pred = result.get("predicate") or query.get("predicate")
                certain = result.get("certain") or []
                possible = result.get("possible") or []

                if not certain and not possible:
                    return {
                        "answer": f"No entities satisfy {pred}.",
                        "explanation": None,
                    }

                lines = []

                if certain:
                    lines.append("Certain " + pred + ": " + ", ".join(certain))
                else:
                    lines.append("Certain " + pred + ": (none)")

                if possible:
                    lines.append("Possible " + pred + ": " + ", ".join(possible))
                else:
                    lines.append("Possible " + pred + ": (none)")

                return {
                    "answer": "\n".join(lines),
                    "explanation": None,
                }

            # Legacy tuple-based representation
            if isinstance(result, dict) and "tuples" in result:
                pred = result.get("predicate") or query.get("predicate")
                tuples = result.get("tuples") or []

                if not tuples:
                    return {"answer": f"No entities satisfy {pred}.", "explanation": None}

                if all(isinstance(t, list) and len(t) == 1 for t in tuples):
                    vals = [t[0] for t in tuples]
                    return {
                        "answer": f"{pred}: " + ", ".join(vals),
                        "explanation": None,
                    }

                pretty = [("(" + ",".join(t) + ")") for t in tuples if isinstance(t, list)]
                return {
                    "answer": f"{pred}: " + ", ".join(pretty),
                    "explanation": None,
                }

            return {"answer": "Unsupported set-result format.", "explanation": None}

    return {"answer": "Unsupported query.", "explanation": None}
