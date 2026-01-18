from idp_z3.tasks import _compose_program
from idp_z3.idp_backend import run_propagate
from debug import debug_log

def run(case, base_kb_text, query):
    """Run IDP propagation over T ∧ Case.

    This intent is a thin wrapper around the IDP python bindings.
    If your installed idp_engine does not expose propagation, this intent
    raises a clear error telling you what's missing.
    """
    fo_code = _compose_program(case, base_kb_text)
    debug_log("intents.propagation.run", "propagate")
    out = run_propagate(fo_code)
    # Keep output as text; upstream can render or parse later.
    return True, {"structure": out.get("structure")}
