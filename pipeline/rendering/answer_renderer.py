# pipeline/rendering/answer_renderer.py

from pipeline.rendering.explanations import explain_generic, explain_on_demand
from pipeline.rendering.intent_renderers import render_normalized_result


def render_answer(case, query, sat, result, base_kb_text=None, kb_schema=None):
    """Render user-facing answer from normalized symbolic_result when possible."""
    if isinstance(result, dict) and result.get("output_kind"):
        answer = render_normalized_result(result, query, kb_schema=kb_schema)
        explanation = None
        if result.get("output_kind") == "epistemic_boolean" and query and query.get("explain"):
            explanation = explain_generic(case, query, sat, result, base_kb_text=base_kb_text)
        elif result.get("output_kind") == "explanation":
            explanation = result.get("explanation")
        elif query and query.get("explain"):
            explanation = explain_on_demand(case, query, result, base_kb_text=base_kb_text)
        if result.get("status") in ("unsupported", "error"):
            return {"answer": answer, "explanation": explanation}
        return {"answer": answer, "explanation": explanation}

    # Legacy payloads (pre-normalization)
    if query.get("type") == "intent":
        intent = (query.get("intent") or "").strip().lower()
        if intent == "satisfiable":
            sat_val = result.get("satisfiable") if isinstance(result, dict) else sat
            if sat_val:
                return {"answer": "Yes. The law and case facts are satisfiable (a model exists).", "explanation": None}
            return {"answer": "No. The law and case facts are inconsistent (no model exists).", "explanation": None}
        if isinstance(result, dict) and result.get("error") == "intent_not_implemented":
            return {"answer": "Intent not implemented: " + str(result.get("intent")), "explanation": None}
        return {"answer": "Unsupported intent.", "explanation": None}

    if query.get("type") == "predicate":
        from pipeline.rendering.intent_renderers import render_epistemic_boolean, render_entity_set

        mode = (query.get("mode") or "").strip().lower()
        if mode == "boolean" and isinstance(result, dict):
            return {
                "answer": render_epistemic_boolean(result, query, kb_schema=kb_schema),
                "explanation": None,
            }
        if mode == "set" and isinstance(result, dict):
            legacy = {
                "predicate": result.get("predicate") or query.get("predicate"),
                "entailed": result.get("certain") or result.get("entailed") or [],
                "unknown": result.get("possible") or result.get("unknown") or [],
            }
            return {"answer": render_entity_set(legacy), "explanation": None}

    return {"answer": "Unsupported query.", "explanation": None}
