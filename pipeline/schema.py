import re


_identifier = re.compile("^[a-z][a-z0-9_]*$")
_callname = re.compile(r"\b([A-Za-z_]\w*)\s*\(")


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


_bad_star_call = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\*\s*\(")

def _check_symbols_in_fact_line(line, allowed_predicates, allowed_functions):
    if _bad_star_call.search(line):
        raise ValueError("Invalid symbol token in case facts (unexpected '*'): " + line)

    for m in _callname.finditer(line):
        name = m.group(1)
        if name in ["max", "min", "abs"]:
            continue
        if name not in allowed_predicates and name not in allowed_functions:
            raise ValueError("Unknown symbol in case facts: " + name)



def normalize_and_validate_case(raw_case, kb_schema=None):
    """
    Supports TWO formats:

    1) Legacy demo format:
       {"parties":[...], "negligent":[...], "caused_damage":[...]}

    2) Schema-driven format:
       {"facts":[ "pred(a,b).", "f(a)=3." ]}
    """
    if not isinstance(raw_case, dict):
        raise ValueError("case must be a dict")

    # ---- schema-driven path ----
    if "facts" in raw_case:
        facts = _norm_str_list(raw_case.get("facts"), "case.facts")

        # basic line constraints
        for ln in facts:
            if not ln.endswith("."):
                raise ValueError("Each case fact must end with '.' (got: " + ln + ")")

        allowed_predicates, allowed_functions = _schema_symbol_sets(kb_schema)
        if kb_schema:
            for ln in facts:
                _check_symbols_in_fact_line(ln, allowed_predicates, allowed_functions)

        return {"facts": facts}

    # ---- legacy path ----
    required = ["parties", "negligent", "caused_damage"]
    missing = [k for k in required if k not in raw_case]
    if missing:
        raise ValueError("case missing keys: " + ", ".join(missing))

    def _norm_identifier_list(xs, field_name):
        if not isinstance(xs, list):
            raise ValueError("Expected list for " + field_name)
        out = []
        for x in xs:
            if not isinstance(x, str):
                raise ValueError("Expected strings in " + field_name)
            y = x.strip().lower()
            if y:
                out.append(y)
        return out

    parties = sorted(set(_norm_identifier_list(raw_case["parties"], "case.parties")))
    negligent = sorted(set(_norm_identifier_list(raw_case["negligent"], "case.negligent")))
    caused_damage = sorted(set(_norm_identifier_list(raw_case["caused_damage"], "case.caused_damage")))

    bad = [p for p in parties if not _identifier.match(p)]
    if bad:
        raise ValueError("Invalid party identifiers in case.parties: " + ", ".join(bad))

    party_set = set(parties)
    if not set(negligent).issubset(party_set):
        raise ValueError("case.negligent contains names not in case.parties")
    if not set(caused_damage).issubset(party_set):
        raise ValueError("case.caused_damage contains names not in case.parties")

    return {"parties": parties, "negligent": negligent, "caused_damage": caused_damage}


def normalize_and_validate_query(raw_query, case, kb_schema=None):
    """
    Supports:
      - predicate queries (generic, schema-driven)
      - intent queries (satisfiable, propagation, etc.)
    """
    if not isinstance(raw_query, dict):
        raise ValueError("query must be a dict")

    q_type = str(raw_query.get("type", "")).strip().lower()
    explain = bool(raw_query.get("explain", False))

    if q_type == "intent":
        intent = str(raw_query.get("intent", "")).strip().lower()
        if not intent:
            raise ValueError("intent query requires query.intent")
        return {"type": "intent", "intent": intent, "explain": explain}

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

    # basic normalization (lowercase args)
    args_norm = []
    for a in args:
        if not isinstance(a, str):
            raise ValueError("query.args must contain strings")
        a2 = a.strip().lower()
        if a2:
            args_norm.append(a2)

    # schema-based predicate existence/arity check
    if kb_schema:
        sig = None
        for p in kb_schema.get("predicates", []):
            if p.get("name") == predicate:
                sig = p
                break
        if sig is None:
            raise ValueError("Unknown predicate in query (not in kb_schema): " + predicate)

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

