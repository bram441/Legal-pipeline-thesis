# pipeline/rendering/answer_renderer.py

from pipeline.rendering.explanations import explain_generic


def render_answer(case, query, sat, result, base_kb_text=None):
    # ---- Intent queries ----
    if query.get("type") == "intent":
        intent = (query.get("intent") or "").strip().lower()

        if intent == "satisfiable":
            if sat:
                return {"answer": "Yes. The law and case facts are satisfiable (a model exists).", "explanation": None}
            return {"answer": "No. The law and case facts are inconsistent (no model exists).", "explanation": None}

        # Generic fallback for other intents (until you implement them)
        if isinstance(result, dict) and result.get("error") == "intent_not_implemented":
            return {
                "answer": "Intent not implemented: " + str(result.get("intent")),
                "explanation": None,
            }

        return {"answer": "Unsupported intent.", "explanation": None}

    # ---- Predicate queries (schema-driven, generic) ----
    if query.get("type") == "predicate":
        mode = (query.get("mode") or "").strip().lower()

        # If symbolic layer returned an intent-not-implemented payload (common for set queries right now)
        if isinstance(result, dict) and result.get("error") == "intent_not_implemented":
            ans = "Cannot answer yet: intent not implemented (" + str(result.get("intent")) + ")."
            return {"answer": ans, "explanation": None}

        # Boolean: this is routed to deduction and returns possible/certain/atom
        if mode == "boolean":
            atom = None
            possible = None
            certain = None

            if isinstance(result, dict):
                atom = result.get("atom")
                possible = result.get("possible")
                certain = result.get("certain")

            # Defensive fallback
            if possible is None or certain is None:
                return {"answer": "Unsupported predicate result format.", "explanation": None}

            # 3-valued style:
            # - certain=True  => entailed
            # - possible=False => impossible (entailed negation under satisfiable KB+case)
            # - otherwise => unknown / not provable
            if certain:
                ans = "Yes. " + (atom if atom else "The statement") + " is entailed by the law and case facts."
            elif possible is False:
                ans = "No. " + (atom if atom else "The statement") + " cannot hold given the law and case facts."
            else:
                ans = "Unknown. " + (atom if atom else "The statement") + " is not determined by the law and case facts."

            explanation = None
            if query.get("explain"):
                explanation = explain_generic(case, query, sat, result, base_kb_text=base_kb_text)

            return {"answer": ans, "explanation": explanation}

        # Set: routed to model_expansion (next step). For now we avoid misleading “No parties…”
        if mode == "set":
            # Once model_expansion is implemented, you’ll return something like:
            # result = {"predicate": "liable", "tuples": [["alice"],["bob"]]}
            if isinstance(result, dict) and "tuples" in result:
                pred = result.get("predicate") or query.get("predicate")
                tuples = result.get("tuples") or []
                if not tuples:
                    return {"answer": "No results for " + str(pred) + ".", "explanation": None}

                # Pretty print unary vs n-ary
                if all(isinstance(t, list) and len(t) == 1 for t in tuples):
                    vals = [t[0] for t in tuples]
                    return {"answer": str(pred) + ": " + ", ".join(vals) + ".", "explanation": None}

                pretty = [("(" + ",".join(t) + ")") for t in tuples if isinstance(t, list)]
                return {"answer": str(pred) + ": " + ", ".join(pretty) + ".", "explanation": None}

            return {"answer": "Set query requires model_expansion (not implemented yet).", "explanation": None}

    return {"answer": "Unsupported query.", "explanation": None}
