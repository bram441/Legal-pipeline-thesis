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

        if intent == "get_range":
            if isinstance(result, dict) and "range" in result:
                sym = result.get("symbol", "")
                rng = str(result.get("range", ""))
                return {"answer": str(sym) + ": " + rng, "explanation": None}
            return {"answer": "Could not compute range.", "explanation": None}

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
            
            display_atom = atom
            args = query.get("args") or []
            pred = query.get("predicate") or ""
            if pred and args:
                display_atom = pred + "(" + ", ".join(str(a) for a in args) + ")"


            # 3-valued style:
            # - certain=True  => entailed
            # - possible=False => impossible (entailed negation under satisfiable KB+case)
            # - otherwise => unknown / not provable
            shown = display_atom if display_atom else "The statement"

            if certain:
                ans = "Yes. " + shown + " is entailed by the law and case facts."
            elif possible is False:
                ans = "No. " + shown + " cannot hold given the law and case facts."
            else:
                ans = "Unknown. " + shown + " is not determined by the law and case facts."

            explanation = None
            if query.get("explain"):
                explanation = explain_generic(case, query, sat, result, base_kb_text=base_kb_text)

            return {"answer": ans, "explanation": explanation}

        # Set: routed to model_expansion (next step). For now we avoid misleading “No parties…”
        if mode == "set":
            # Preferred representation for set queries in this project:
            #   result = {"predicate":"liable","mode":"set","certain":[...],"possible":[...]}
            if isinstance(result, dict) and "possible" in result and "certain" in result:
                pred = result.get("predicate") or query.get("predicate")
                certain = result.get("certain") or []
                possible = result.get("possible") or []

                if not certain and not possible:
                    return {"answer": "No results for " + str(pred) + ".", "explanation": None}

                # Keep it simple and explicit (useful for debugging).
                parts = []
                if certain:
                    parts.append("certain=" + ", ".join(certain))
                if possible:
                    parts.append("possible=" + ", ".join(possible))

                ans = str(pred) + " -> " + " | ".join(parts)
                return {"answer": ans, "explanation": None}

            # Legacy/alternate representation (tuple list)
            if isinstance(result, dict) and "tuples" in result:
                pred = result.get("predicate") or query.get("predicate")
                tuples = result.get("tuples") or []
                if not tuples:
                    return {"answer": "No results for " + str(pred) + ".", "explanation": None}

                if all(isinstance(t, list) and len(t) == 1 for t in tuples):
                    vals = [t[0] for t in tuples]
                    return {"answer": str(pred) + ": " + ", ".join(vals) + ".", "explanation": None}

                pretty = [("(" + ",".join(t) + ")") for t in tuples if isinstance(t, list)]
                return {"answer": str(pred) + ": " + ", ".join(pretty) + ".", "explanation": None}

            return {"answer": "Unsupported set-result format.", "explanation": None}

    return {"answer": "Unsupported query.", "explanation": None}
