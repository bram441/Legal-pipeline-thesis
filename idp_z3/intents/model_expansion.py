from idp_z3.tasks import _compose_program
from idp_z3.idp_backend import run_idp
from debug import debug_log

def run(case, base_kb_text, query):
    """Expand up to N models for T ∧ Case.

    Query options:
      - max_models (int)
    """
    max_models = query.get("max_models")
    if max_models is None:
        max_models = 3
    if not isinstance(max_models, int) or max_models < 0:
        raise ValueError("model_expansion.max_models must be a non-negative int")

    fo_code = _compose_program(case, base_kb_text)
    debug_log("intents.model_expansion.run", "max_models=" + str(max_models))
    res = run_idp(fo_code, max_models=max_models)
    sat = bool(res.get("sat"))
    return sat, {"sat": sat, "models": res.get("models") or []}
