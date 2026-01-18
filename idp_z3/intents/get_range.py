from idp_z3.tasks import _compose_program
from idp_z3.idp_backend import run_get_range
from debug import debug_log

def run(case, base_kb_text, query):
    """Get a range for a symbol (if supported by bindings).

    Expected query:
      {"type":"intent","intent":"get_range","symbol":"<name>"}

    Returns:
      {"range": "<raw idp output>"}
    """
    symbol = (query.get("symbol") or "").strip()
    if not symbol:
        raise ValueError("get_range intent requires query.symbol")

    fo_code = _compose_program(case, base_kb_text)
    debug_log("intents.get_range.run", "symbol=" + symbol)
    out = run_get_range(fo_code, symbol_name=symbol)
    return True, {"symbol": symbol, "range": out.get("range")}
