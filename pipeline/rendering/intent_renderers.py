"""Render normalized symbolic intent results to natural language."""

from __future__ import annotations

from pipeline.eval.boolean_belief import summarize_boolean_symbolic
from pipeline.rendering.nl_answer import render_boolean_nl, render_get_range_nl, render_set_nl


def _fmt_atom(item: dict) -> str:
    pred = item.get("predicate") or ""
    args = item.get("args") or []
    return pred + "(" + ", ".join(str(a) for a in args) + ")"


def render_epistemic_boolean(
    result: dict,
    query: dict | None = None,
    kb_schema: dict | None = None,
) -> str:
    pred = result.get("predicate") or (query or {}).get("predicate") or ""
    args = result.get("args") or (query or {}).get("args") or []
    certain = result.get("certain")
    possible = result.get("possible")
    label = result.get("label")
    if label == "entailed" or certain is True:
        if pred and args:
            return render_boolean_nl(pred, args, True, True, kb_schema=kb_schema)
        return "Yes. The statement is entailed by the law and case facts."
    if label == "contradicted" or possible is False:
        if pred and args:
            return render_boolean_nl(pred, args, False, False, kb_schema=kb_schema)
        return "No. The statement cannot hold given the law and case facts."
    b = summarize_boolean_symbolic(result)
    shown = pred + "(" + ", ".join(str(a) for a in args) + ")" if pred and args else "The statement"
    return (
        "Cannot determine with certainty. "
        + shown
        + " is not logically forced either way (label: "
        + str(b.get("label", "unknown"))
        + ")."
    )


def render_entity_set(result: dict) -> str:
    pred = result.get("predicate") or "predicate"
    entailed = result.get("entailed") or result.get("certain") or []
    unknown = result.get("unknown") or result.get("possible") or []
    if not entailed and not unknown:
        return "No entities satisfy " + str(pred) + " with the current facts."
    parts = [render_set_nl(pred, entailed, unknown)]
    if unknown:
        parts.append("Entities with unknown status: " + ", ".join(unknown) + ".")
    return " ".join(parts)


def render_propagation(result: dict) -> str:
    if result.get("status") == "unsupported":
        return "Propagation is not available: " + str(result.get("message", ""))
    true_atoms = result.get("certain_true") or []
    false_atoms = result.get("certain_false") or []
    if not true_atoms and not false_atoms:
        return "No certain legal conclusions were derived across all models."
    lines = ["The following conclusions are certain (true in all models):"]
    for item in true_atoms:
        lines.append("- " + _fmt_atom(item))
    if false_atoms:
        lines.append("The following are certainly false in all models:")
        for item in false_atoms:
            lines.append("- " + _fmt_atom(item))
    return "\n".join(lines)


def render_model_expansion(result: dict) -> str:
    if result.get("status") == "unsupported":
        return "Model expansion is not available: " + str(result.get("message", ""))
    models = result.get("models") or []
    if not models:
        return "No model could be expanded for the case and law."
    m0 = models[0]
    lines = ["One possible completion of the case under the law (not necessarily the only outcome):"]
    for item in m0.get("true_atoms") or []:
        lines.append("- " + _fmt_atom(item) + " (possible)")
    for item in m0.get("function_values") or []:
        fn = item.get("function", "")
        args = item.get("args") or []
        val = item.get("value", "")
        lines.append("- " + fn + "(" + ", ".join(str(a) for a in args) + ") = " + str(val) + " (possible)")
    lines.append("These are possible assignments, not legally certain conclusions.")
    return "\n".join(lines)


def render_range(result: dict) -> str:
    if result.get("status") == "unsupported":
        return "Range query is not available: " + str(result.get("message", ""))
    fn = result.get("function") or result.get("symbol") or ""
    values = result.get("values") or []
    if values:
        return str(fn) + " possible values: " + ", ".join(str(v) for v in values) + "."
    rng = result.get("range")
    if rng:
        entity = result.get("entity") or ""
        return render_get_range_nl(fn, str(rng), entity)
    return "No range values could be determined for " + str(fn) + "."


def render_satisfiable(result: dict) -> str:
    sat = result.get("satisfiable") if "satisfiable" in result else result.get("sat")
    if sat:
        return "Yes. The law and case facts are satisfiable (at least one model exists)."
    return "No. The law and case facts are inconsistent (no model exists)."


def render_optimization(result: dict) -> str:
    if result.get("status") == "unsupported":
        return "Optimization is not available: " + str(result.get("message", ""))
    direction = result.get("direction") or "opt"
    val = result.get("value")
    obj = result.get("objective") or {}
    fn = obj.get("function", "")
    return f"The {direction}imum value for {fn} is {val}."


def render_relevance(result: dict) -> str:
    if result.get("status") == "unsupported":
        return "Relevance analysis is not available: " + str(result.get("message", ""))
    syms = result.get("relevant_symbols") or []
    if not syms:
        return "No relevant symbols were identified."
    return "Relevant symbols: " + ", ".join(str(s) for s in syms) + "."


def render_explanation(result: dict) -> str:
    if result.get("status") == "unsupported":
        return "Explanation is not available: " + str(result.get("message", ""))
    text = result.get("explanation") or ""
    support = result.get("support") or []
    lines = [text]
    if support:
        lines.append("Supporting certain facts:")
        for item in support:
            if isinstance(item, dict):
                lines.append("- " + _fmt_atom(item))
    if not text:
        lines[0] = "No detailed explanation is available from the solver."
    return "\n".join(lines)


_RENDERERS = {
    "epistemic_boolean": render_epistemic_boolean,
    "entity_set": render_entity_set,
    "certain_facts": render_propagation,
    "models": render_model_expansion,
    "range": render_range,
    "boolean": render_satisfiable,
    "optimum": render_optimization,
    "symbols": render_relevance,
    "explanation": render_explanation,
}


def render_normalized_result(
    result: dict,
    query: dict | None = None,
    kb_schema: dict | None = None,
) -> str:
    kind = result.get("output_kind") or ""
    fn = _RENDERERS.get(kind)
    if fn:
        if kind == "epistemic_boolean":
            return fn(result, query, kb_schema=kb_schema)
        return fn(result)
    if result.get("status") == "error":
        return "Symbolic reasoning error: " + str(result.get("message", ""))
    return "Unsupported symbolic output kind: " + str(kind)
