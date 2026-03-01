import re


_callname = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_neg_atom = re.compile(r"^\s*(?:not|~|¬)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_pos_atom = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_bad_star_call = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\*\s*\(")


def _norm_str_list(xs, field_name):
    if not isinstance(xs, list):
        raise ValueError("Expected list for " + field_name + ", got " + str(type(xs)))
    out = []
    for x in xs:
        if not isinstance(x, str):
            raise ValueError("Expected strings in " + field_name)
        y = x.strip()
        if y:
            out.append(y)
    return out


def _schema_symbol_sets(kb_schema):
    preds = set()
    funs = set()
    if not kb_schema:
        return preds, funs

    for p in kb_schema.get("predicates", []):
        name = p.get("name")
        if name:
            preds.add(name)

    for f in kb_schema.get("functions", []):
        name = f.get("name")
        if name:
            funs.add(name)

    return preds, funs


def _schema_symbol_lookup(kb_schema):
    """Build case-insensitive mapping: lowercase_name -> canonical_name (unique only)."""
    lookup = {}
    all_symbols = []
    if kb_schema:
        for p in kb_schema.get("predicates", []) or []:
            n = p.get("name")
            if n:
                all_symbols.append(n)
        for f in kb_schema.get("functions", []) or []:
            n = f.get("name")
            if n:
                all_symbols.append(n)

    for canonical in all_symbols:
        key = canonical.lower()
        if key in lookup and lookup[key] != canonical:
            lookup[key] = None  # ambiguous, don't use
        else:
            lookup[key] = canonical

    return {k: v for k, v in lookup.items() if v is not None}


def _normalize_symbol_casing_in_fact(line, symbol_lookup):
    """Replace symbol names with canonical schema names when case-insensitive match exists."""
    if not symbol_lookup:
        return line

    def repl(m):
        name = m.group(1)
        canonical = symbol_lookup.get(name.lower())
        return canonical if canonical else name

    return _callname.sub(lambda m: repl(m) + "(", line)


def _check_symbols_in_fact_line(line, allowed_predicates, allowed_functions, symbol_lookup=None):
    if _bad_star_call.search(line):
        raise ValueError("Invalid symbol token in case facts (unexpected '*'): " + line)

    for m in _callname.finditer(line):
        name = m.group(1)
        if name in ["max", "min", "abs"]:
            continue
        if name in allowed_predicates or name in allowed_functions:
            continue
        if symbol_lookup and name.lower() in symbol_lookup:
            continue
        raise ValueError("Unknown symbol in case facts: " + name)


def normalize_and_validate_case(raw_case, kb_schema=None):
    """Schema-driven case normalization.

    Expected shape:
      {"facts": ["pred(a).", "f(a) = 3.", ...], "entities": {... optional ...}}

    Design
    - Facts are FO(.) structure lines (must end with '.')
    - If kb_schema is provided, every called symbol must exist in kb_schema
    - Symbol names are normalized to canonical schema casing (e.g. intentionalinjury -> IntentionalInjury)
    """
    if not isinstance(raw_case, dict):
        raise ValueError("case must be a dict")

    if "facts" not in raw_case:
        raise ValueError("case missing key: facts")

    facts = _norm_str_list(raw_case.get("facts"), "case.facts")

    for ln in facts:
        if not ln.endswith("."):
            raise ValueError("Each case fact must end with '.' (got: " + ln + ")")

    symbol_lookup = _schema_symbol_lookup(kb_schema) if kb_schema else {}
    allowed_predicates, allowed_functions = _schema_symbol_sets(kb_schema) if kb_schema else (set(), set())

    normalized_facts = []
    for ln in facts:
        norm_ln = _normalize_symbol_casing_in_fact(ln, symbol_lookup)
        if kb_schema:
            _check_symbols_in_fact_line(norm_ln, allowed_predicates, allowed_functions, symbol_lookup)
        normalized_facts.append(norm_ln)

    # Remove contradictions: if both pred(x) and not pred(x) exist, keep only not pred(x)
    def _args_key(s):
        return tuple(a.strip() for a in (s or "").split(",") if a.strip())

    neg_keys = set()
    for ln in normalized_facts:
        mneg = _neg_atom.match(ln.strip())
        if mneg:
            neg_keys.add((mneg.group(1), _args_key(mneg.group(2))))

    deduped = []
    for ln in normalized_facts:
        mpos = _pos_atom.match(ln.strip())
        if mpos and "=" not in ln:
            key = (mpos.group(1), _args_key(mpos.group(2)))
            if key in neg_keys:
                continue  # drop pos when we have neg
        deduped.append(ln)

    out = {"facts": deduped}

    # Entities are optional and used for domain seeding in the symbolic layer.
    ents = raw_case.get("entities")
    if isinstance(ents, dict):
        out["entities"] = ents

    return out


def normalize_and_validate_query(raw_query, case, kb_schema=None):
    """Normalize and validate a query.

    Supports:
      - predicate queries (schema-driven)
      - intent queries (satisfiable, propagation, ...)
    """
    if not isinstance(raw_query, dict):
        raise ValueError("query must be a dict")

    q_type = str(raw_query.get("type", "")).strip().lower()
    explain = bool(raw_query.get("explain", False))

    if q_type == "intent":
        intent = str(raw_query.get("intent", "")).strip().lower()
        if not intent:
            raise ValueError("intent query requires query.intent")

        symbol = str(raw_query.get("symbol", "")).strip()
        if intent == "get_range":
            if not symbol:
                raise ValueError("get_range intent requires query.symbol")
            if kb_schema:
                funcs = [f.get("name") for f in (kb_schema.get("functions") or []) if f.get("name")]
                def _norm_name(s):
                    return (s or "").lower().replace("_", "")
                symbol_match = next((f for f in funcs if f == symbol or (f and _norm_name(f) == _norm_name(symbol))), None)
                if not symbol_match:
                    raise ValueError("get_range symbol must be a function from kb_schema: " + symbol)
                symbol = symbol_match

        out = dict(raw_query)
        out["type"] = "intent"
        out["intent"] = intent
        out["explain"] = explain
        if intent == "get_range":
            out["symbol"] = symbol
            out["entity"] = str(raw_query.get("entity", "")).strip().lower()
        return out

    if q_type != "predicate":
        raise ValueError("Unsupported query.type: " + str(raw_query.get("type")))

    predicate = str(raw_query.get("predicate", "")).strip()
    mode = str(raw_query.get("mode", "set") or "set").strip().lower()
    args = raw_query.get("args", [])
    if args is None:
        args = []

    if not predicate:
        raise ValueError("predicate query requires query.predicate")
    if mode not in ["set", "boolean"]:
        raise ValueError("query.mode must be 'set' or 'boolean'")
    if not isinstance(args, list):
        raise ValueError("query.args must be a list")

    args_norm = []
    for a in args:
        if not isinstance(a, str):
            raise ValueError("query.args must contain strings")
        a2 = a.strip().lower()
        if a2:
            args_norm.append(a2)

    if kb_schema:
        sig = None
        predicate_canonical = predicate
        def _norm_name(s):
            return (s or "").lower().replace("_", "")
        for p in kb_schema.get("predicates", []):
            n = p.get("name")
            if n == predicate:
                sig = p
                predicate_canonical = n
                break
            if n and (_norm_name(n) == _norm_name(predicate)):
                sig = p
                predicate_canonical = n
                break
        if sig is None:
            raise ValueError("Unknown predicate in query (not in kb_schema): " + predicate)
        predicate = predicate_canonical

        arity = len(sig.get("args", []))
        if mode == "boolean" and len(args_norm) != arity:
            raise ValueError("Predicate arity mismatch for " + predicate + ": expected " + str(arity) + " args")
        if mode == "set" and len(args_norm) != 0:
            raise ValueError("set mode requires args=[]")

    return {
        "type": "predicate",
        "predicate": predicate,
        "mode": mode,
        "args": args_norm,
        "explain": explain,
    }


def build_structure_block_from_facts(fact_lines):
    if not isinstance(fact_lines, list) or not fact_lines:
        raise ValueError("fact_lines must be a non-empty list")

    cleaned = []
    for ln in fact_lines:
        if not isinstance(ln, str):
            raise ValueError("fact line must be a string")
        s = ln.strip()
        if not s:
            continue
        if not s.endswith("."):
            raise ValueError("fact line must end with '.': " + s)
        cleaned.append(s)

    body = "\n  ".join(cleaned)
    return f"""
structure S:V {{
  {body}
}}
""".strip()
