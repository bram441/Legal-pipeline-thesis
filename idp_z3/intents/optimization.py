from idp_z3.tasks import _compose_program
from idp_z3.idp_backend import run_optimize
from debug import debug_log

def run(case, base_kb_text, query):
    """Run optimization (if supported by bindings).

    This intent simply forwards to the IDP bindings. Your KB must contain
    an optimization statement for meaningful results.
    """
    fo_code = _compose_program(case, base_kb_text)
    debug_log("intents.optimization.run", "optimize")
    out = run_optimize(fo_code)
    return True, {"result": out.get("result")}
