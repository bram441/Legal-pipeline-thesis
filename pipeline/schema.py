import re


_identifier = re.compile("^[a-z][a-z0-9_]*$")


def _norm_identifier_list(xs, field_name):
    if not isinstance(xs, list):
        raise ValueError("Expected list for " + field_name + ", got " + str(type(xs)))

    out = []
    for x in xs:
        if not isinstance(x, str):
            raise ValueError("Expected strings in " + field_name)
        y = x.strip().lower()
        if y:
            out.append(y)
    return out


def normalize_and_validate_case(raw_case):
    if not isinstance(raw_case, dict):
        raise ValueError("case must be a dict")

    required = ["parties", "negligent", "caused_damage"]
    missing = [k for k in required if k not in raw_case]
    if missing:
        raise ValueError("case missing keys: " + ", ".join(missing))

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

    return {
        "parties": parties,
        "negligent": negligent,
        "caused_damage": caused_damage,
    }


def normalize_and_validate_query(raw_query, case):
    if not isinstance(raw_query, dict):
        raise ValueError("query must be a dict")

    required = ["type", "predicate", "mode", "args", "explain"]
    missing = [k for k in required if k not in raw_query]
    if missing:
        raise ValueError("query missing keys: " + ", ".join(missing))

    q_type = str(raw_query["type"]).strip().lower()
    predicate = str(raw_query["predicate"]).strip()
    mode = str(raw_query["mode"]).strip().lower()
    explain = bool(raw_query["explain"])

    if q_type != "predicate":
        raise ValueError("Only query.type == 'predicate' is supported right now")

    if not predicate:
        raise ValueError("query.predicate must be a non-empty string")

    if mode not in ["set", "boolean"]:
        raise ValueError("query.mode must be 'set' or 'boolean'")

    args = raw_query["args"]
    if not isinstance(args, list):
        raise ValueError("query.args must be a list")

    args_norm = []
    for a in args:
        if not isinstance(a, str):
            raise ValueError("query.args must contain strings")
        a2 = a.strip().lower()
        if a2:
            args_norm.append(a2)

    if mode == "boolean":
        if len(args_norm) != 1:
            raise ValueError("boolean mode requires exactly one argument, e.g. args=['alice']")
        if args_norm[0] not in set(case["parties"]):
            raise ValueError("boolean arg must be a known party in case.parties")

    if mode == "set":
        if len(args_norm) != 0:
            raise ValueError("set mode requires args=[]")

    return {
        "type": "predicate",
        "predicate": predicate,
        "mode": mode,
        "args": args_norm,
        "explain": explain,
    }
