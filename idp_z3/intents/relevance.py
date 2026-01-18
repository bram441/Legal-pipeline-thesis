from idp_z3.tasks import _compose_program
from idp_z3.idp_backend import run_relevance
from debug import debug_log

def run(case, base_kb_text, query):
    """Run relevance analysis (if supported by bindings)."""
    fo_code = _compose_program(case, base_kb_text)
    debug_log("intents.relevance.run", "relevance")
    out = run_relevance(fo_code)
    return True, {"relevance": out.get("relevance")}
