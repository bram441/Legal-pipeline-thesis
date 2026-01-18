from idp_z3.tasks import _compose_program
from idp_z3.idp_backend import run_idp
from debug import debug_log

def run(case, base_kb_text, query):
    """Return SAT(T ∧ Case). No model enumeration."""
    fo_code = _compose_program(case, base_kb_text)
    debug_log("intents.model_checking.run", "model_check only")
    res = run_idp(fo_code, max_models=0)
    sat = bool(res.get("sat"))
    return sat, {"sat": sat}
