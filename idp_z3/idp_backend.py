# idp_backend.py
from idp_engine import IDP
from idp_engine.Run import model_check, model_expand

from pipeline.utils.unicode_sanitize import sanitize_for_output

def run_idp(fo_code, theory_name="T", struct_name="S", max_models=10, timeout_seconds=5):
    """Run an FO(.) program with IDP-Z3 and return satisfiability and model output."""
    kb = IDP.from_str(fo_code)

    if isinstance(theory_name, (list, tuple)):
        theories = [kb.theories[name] for name in theory_name]
    else:
        theories = [kb.theories[theory_name]]

    S = kb.structures[struct_name]

    sat_status = model_check(*theories, S)

    models = []
    for chunk in model_expand(*theories, S, max=max_models, timeout_seconds=timeout_seconds):
        models.append(chunk)

    return {"sat": sat_status == "sat", "models": models}


def _load_optional_run_fn(fn_name):
    """Load an optional IDP-Z3 run helper from idp_engine.Run.

    Different idp_engine versions expose different helpers. We keep these
    imports local so the rest of the pipeline stays usable even if a helper
    is missing.
    """
    try:
        import idp_engine.Run as _R
    except Exception as e:
        raise RuntimeError("Could not import idp_engine.Run (IDP-Z3 python bindings missing?): " + str(e))

    fn = getattr(_R, fn_name, None)
    if fn is None:
        raise RuntimeError("This IDP python binding does not expose Run." + fn_name)
    return fn


def run_propagate(fo_code, theory_name="T", struct_name="S", timeout_seconds=5):
    """Run IDP propagation if available.

    Returns:
      {"structure": str} (rendered propagated structure) or raises.
    """
    kb = IDP.from_str(fo_code)

    if isinstance(theory_name, (list, tuple)):
        theories = [kb.theories[name] for name in theory_name]
    else:
        theories = [kb.theories[theory_name]]

    S = kb.structures[struct_name]
    propagate = _load_optional_run_fn("propagate")
    # Some versions use timeout_seconds, others use timeout.
    try:
        out = propagate(*theories, S, timeout_seconds=timeout_seconds)
    except TypeError:
        out = propagate(*theories, S, timeout=timeout_seconds)
    return {"structure": str(out)}


def run_get_range(fo_code, symbol_name, theory_name="T", struct_name="S", timeout_seconds=5, filter_entity=None):
    """Compute a range for a function symbol. Uses Run.get_range if available, else falls back to model_expand.

    When filter_entity is set, extracts only that entity's value from the mapping.
    """
    import re

    kb = IDP.from_str(fo_code)
    if isinstance(theory_name, (list, tuple)):
        theories = [kb.theories[name] for name in theory_name]
    else:
        theories = [kb.theories[theory_name]]
    S = kb.structures[struct_name]

    try:
        get_range_fn = _load_optional_run_fn("get_range")
        try:
            out = get_range_fn(*theories, S, symbol_name, timeout_seconds=timeout_seconds)
        except TypeError:
            out = get_range_fn(*theories, S, symbol_name, timeout=timeout_seconds)
        raw = sanitize_for_output(str(out))
        if filter_entity:
            raw = _filter_range_to_entity(raw, filter_entity)
        return {"range": raw}
    except RuntimeError:
        pass

    # Fallback: use model_expand and extract function values from the expanded model
    sat_status = model_check(*theories, S)
    if sat_status != "sat":
        return {"range": "No model exists (theory is unsatisfiable)."}
    models = list(model_expand(*theories, S, max=1, timeout_seconds=timeout_seconds))
    if not models:
        return {"range": "Could not expand model.", "via_model_expand": True}
    model_str = sanitize_for_output(str(models[0]))
    pat = re.compile(r"\b" + re.escape(symbol_name) + r"\s*:=\s*(\{[^}]*\}|\d+)")
    m = pat.search(model_str)
    if m:
        raw = m.group(1).strip()
        if filter_entity:
            raw = _filter_range_to_entity(raw, filter_entity)
        return {"range": raw, "via_model_expand": True}
    return {"range": "Symbol " + symbol_name + " not found in model output.", "via_model_expand": True}


def _filter_range_to_entity(range_str, entity):
    """Extract only entity's value from a mapping like {'a' -> 1, 'b' -> 2}."""
    import re
    entity_clean = entity.strip().lower().replace("'", "").replace('"', "")
    if not entity_clean:
        return range_str
    # Match 'entity' -> value, "entity" -> value, or entity -> value
    for pattern in [
        r"['\"]" + re.escape(entity_clean) + r"['\"]\s*->\s*(-?\d+)",
        r"\b" + re.escape(entity_clean) + r"\s*->\s*(-?\d+)",
    ]:
        m = re.search(pattern, range_str)
        if m:
            return m.group(1)
    return range_str


def run_relevance(fo_code, theory_name="T", struct_name="S", timeout_seconds=5):
    """Run a relevance computation if available."""
    kb = IDP.from_str(fo_code)
    if isinstance(theory_name, (list, tuple)):
        theories = [kb.theories[name] for name in theory_name]
    else:
        theories = [kb.theories[theory_name]]
    S = kb.structures[struct_name]
    relevance = _load_optional_run_fn("relevance")
    try:
        out = relevance(*theories, S, timeout_seconds=timeout_seconds)
    except TypeError:
        out = relevance(*theories, S, timeout=timeout_seconds)
    return {"relevance": str(out)}


def run_optimize(fo_code, theory_name="T", struct_name="S", timeout_seconds=5):
    """Run optimization if available.

    NOTE: IDP optimization APIs differ across bindings. This function returns
    the raw output as text.
    """
    kb = IDP.from_str(fo_code)
    if isinstance(theory_name, (list, tuple)):
        theories = [kb.theories[name] for name in theory_name]
    else:
        theories = [kb.theories[theory_name]]
    S = kb.structures[struct_name]
    optimize = _load_optional_run_fn("optimize")
    try:
        out = optimize(*theories, S, timeout_seconds=timeout_seconds)
    except TypeError:
        out = optimize(*theories, S, timeout=timeout_seconds)
    return {"result": str(out)}



if __name__ == "__main__":
    # Very small self-test, reusing the likes example.
    FO_CODE = """
    vocabulary V {
      type Person
      likes: Person -> Bool
    }

    structure S:V {
      Person := {alice, bob}.
    }

    theory T:V {
      ? p in Person: likes(p).
    }
    """

    result = run_idp(FO_CODE)
    print("SAT?", result["sat"])
    print("\n--- MODELS ---")
    for m in result["models"]:
        print(m)
