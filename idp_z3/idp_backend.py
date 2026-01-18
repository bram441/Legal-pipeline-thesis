# idp_backend.py
from idp_engine import IDP
from idp_engine.Run import model_check, model_expand

# Executes an FO(.) program with IDP-Z3 and returns satisfiability + expanded models.
# This is the low-level backend wrapper around IDP.from_str, model_check, and model_expand.
# It is intentionally generic: it does not assume any particular legal domain predicates.
#
# Params:
#   fo_code (str): Full FO(.) program as a string (vocabulary + theory + structure).
#   theory_name (str | None): Optional name of the theory to check/expand (if your FO code contains multiple theories).
#   struct_name (str | None): Optional name of the structure to use (if your FO code contains multiple structures).
#   max_models (int): Maximum number of models to expand/return.
#   timeout_seconds (int | None): Optional timeout guard for IDP operations.
#
# Returns:
#   dict: A result dictionary with:
#     - "sat" (bool): Whether the theory is satisfiable in the given structure.
#     - "models" (list[str]): One or more expanded model(s) rendered as text.
#     - optionally other debug fields depending on your implementation.

def run_idp(fo_code, theory_name="T", struct_name="S", max_models=10, timeout_seconds=5):
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


def run_get_range(fo_code, symbol_name, theory_name="T", struct_name="S", timeout_seconds=5):
    """Compute a range (if supported) for a symbol in the current problem."""
    kb = IDP.from_str(fo_code)
    if isinstance(theory_name, (list, tuple)):
        theories = [kb.theories[name] for name in theory_name]
    else:
        theories = [kb.theories[theory_name]]
    S = kb.structures[struct_name]
    get_range = _load_optional_run_fn("get_range")
    try:
        out = get_range(*theories, S, symbol_name, timeout_seconds=timeout_seconds)
    except TypeError:
        out = get_range(*theories, S, symbol_name, timeout=timeout_seconds)
    return {"range": str(out)}


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
