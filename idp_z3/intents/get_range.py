from idp_z3.tasks import _compose_program
from idp_z3.idp_backend import run_get_range
from debug import debug_log

def run(case, base_kb_text, query):
    """Get a range for a symbol (if supported by bindings).

    Expected query:
      {"type":"intent","intent":"get_range","symbol":"<name>","entity":"<optional>"}

    When entity is set, only that entity's value is returned (filters full mapping).
    """
    symbol = (query.get("function") or query.get("symbol") or "").strip()
    if not symbol:
        raise ValueError("get_range intent requires query.function or query.symbol")
    entity = (query.get("entity") or "").strip().lower()
    args = query.get("args") or []
    if args and not entity and len(args) == 1:
        entity = str(args[0]).strip().lower()

    fo_code = _compose_program(case, base_kb_text)
    debug_log("intents.get_range.run", "symbol=" + symbol + " entity=" + entity)
    try:
        out = run_get_range(fo_code, symbol_name=symbol, filter_entity=entity)
    except Exception as e:
        return None, {"status": "unsupported", "message": str(e)}
    return True, {"symbol": symbol, "function": symbol, "args": args, "range": out.get("range"), "entity": entity}
