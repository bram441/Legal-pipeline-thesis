import re


_callname = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
_atom_args = re.compile(r"\((.*)\)")
_neg_atom = re.compile(r"^\s*(?:not|~|¬)\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_pos_atom = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\.\s*$")
_bad_star_call = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*\*\s*\(")
_bool_assign_false = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*\([^)]*\)\s*=\s*(?:false|False)\s*\.\s*$")
_QUERY_WILDCARDS = frozenset({"?", "_", "*", "any"})


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


# Invalid patterns for fact arguments (negation must wrap the predicate, not the entity)
_INVALID_ARG_PREFIXES = ("not ", "~", "¬")
_INVALID_ARG_EXACT = frozenset({"not", "~", "¬"})


def _validate_fact_args(line, args_str):
    """Reject arguments like 'not jan' — negation applies to the predicate, not the entity."""
    if not args_str or "=" in line:
        return
    for part in args_str.split(","):
        a = part.strip().strip("'\"").lower()
        if not a:
            continue
        if a == "_":
            raise ValueError(
                "Invalid wildcard argument '_' in case fact. "
                "Use concrete entity names only (e.g. 'anna', 'bert'). "
                "Fix: " + line
            )
        if a in _INVALID_ARG_EXACT or any(a.startswith(p) for p in _INVALID_ARG_PREFIXES):
            raise ValueError(
                "Invalid argument in case fact: negation applies to the predicate, not the entity. "
                "Use 'not Predicate(entity).' never 'Predicate(not entity).' "
                "Fix: " + line
            )


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
        s = ln.strip()
        if _bool_assign_false.match(s):
            raise ValueError(
                "Use 'not Predicate(entity).' instead of 'Predicate(entity) = false.'. "
                "Fix: " + ln
            )
        m_args = _atom_args.search(ln)
        if m_args:
            _validate_fact_args(ln, m_args.group(1))
        norm_ln = _normalize_symbol_casing_in_fact(ln, symbol_lookup)
        if kb_schema:
            _check_symbols_in_fact_line(norm_ln, allowed_predicates, allowed_functions, symbol_lookup)
        normalized_facts.append(norm_ln)

    # Semantic check: detect contradictions (P(x) and not P(x)) and raise for repair
    def _args_key(s):
        return tuple(a.strip().lower() for a in (s or "").split(",") if a.strip())

    neg_keys = set()
    for ln in normalized_facts:
        mneg = _neg_atom.match(ln.strip())
        if mneg:
            neg_keys.add((mneg.group(1), _args_key(mneg.group(2))))

    for ln in normalized_facts:
        mpos = _pos_atom.match(ln.strip())
        if mpos and "=" not in ln:
            key = (mpos.group(1), _args_key(mpos.group(2)))
            if key in neg_keys:
                raise ValueError(
                    "Case facts contain contradiction: {} and not {} both present. "
                    "Remove one based on the case description.".format(
                        mpos.group(1) + "(" + ", ".join(key[1]) + ")",
                        mpos.group(1) + "(" + ", ".join(key[1]) + ")",
                    )
                )

    from pipeline.semantic.legal_question import domain_heuristics_enabled

    if domain_heuristics_enabled():

        def _norm_pred_branch(name):
            return re.sub(r"_", "", (name or "").lower())

        _EXCLUSIVE_SUCCESSION_BRANCHES = frozenset(
            {
                "deceasedleavesdescendants",
                "deceasedleavesrelativesascendingorclosecollateral",
                "deceasedleavesascendantsorcollateral",
                "deceasedleavesotherheirsornoheirs",
            }
        )
        unary_pos_by_arg = {}
        for ln in normalized_facts:
            mpos = _pos_atom.match(ln.strip())
            if not mpos or "=" in ln:
                continue
            pred_n = _norm_pred_branch(mpos.group(1))
            ak = _args_key(mpos.group(2))
            if len(ak) != 1:
                continue
            ent = ak[0]
            unary_pos_by_arg.setdefault(ent, set()).add(pred_n)
        for ent, preds in unary_pos_by_arg.items():
            hit = preds & _EXCLUSIVE_SUCCESSION_BRANCHES
            if len(hit) > 1:
                raise ValueError(
                    "Case facts assert incompatible succession branches for the same person ({}): {}. "
                    "Only one mutually exclusive classification branch should apply.".format(
                        ent, ", ".join(sorted(hit))
                    )
                )

    deduped = normalized_facts

    out = {"facts": deduped}

    meta_keys = ("case_given_factual_inputs",)
    for key in meta_keys:
        if key in raw_case:
            out[key] = raw_case[key]

    # Entities are optional and used for domain seeding in the symbolic layer.
    ents = raw_case.get("entities")
    if isinstance(ents, dict):
        if kb_schema:
            # Canonicalize entity type keys to schema type names (case-insensitive).
            type_lookup = {}
            for t in (kb_schema.get("types") or []):
                if isinstance(t, str) and t.strip():
                    key = t.strip().lower()
                    if key not in type_lookup:
                        type_lookup[key] = t.strip()
            canon_ents = {}
            for t_name, vals in ents.items():
                if not isinstance(vals, list):
                    continue
                k = str(t_name).strip()
                t_canon = type_lookup.get(k.lower(), k)
                canon_ents.setdefault(t_canon, [])
                canon_ents[t_canon].extend(vals)
            out["entities"] = canon_ents
        else:
            out["entities"] = ents

    return out


def _entities_from_case(case):
    """Extract entity names (lowercase, no quotes) that appear in case facts."""
    entities = set()
    facts = list((case or {}).get("facts") or []) if isinstance(case, dict) else []
    for ln in facts:
        if not isinstance(ln, str):
            continue
        m = _atom_args.search(ln)
        if m:
            for part in m.group(1).split(","):
                e = part.strip().strip("'\"").lower()
                if e and not e.isdigit():
                    entities.add(e)
    return entities


def _case_entity_set(case):
    """All entity names (lowercase) from case: facts and case.entities."""
    out = set(_entities_from_case(case))
    for key, vals in (case.get("entities") or {}).items():
        if isinstance(vals, list):
            for v in vals:
                if isinstance(v, str) and v.strip():
                    out.add(v.strip().lower())
    return out


def normalize_and_validate_query(raw_query, case, kb_schema=None):
    """Normalize and validate a query (predicate or public intent)."""
    from pipeline.symbolic.query_validate import validate_and_finalize_query

    return validate_and_finalize_query(raw_query, case, kb_schema)


