
from idp_z3.legal_kb import decide_liability_from_case


def run_query(case, query):
    if query["type"] != "predicate":
        raise ValueError("Unsupported query.type: " + str(query["type"]))

    if query["predicate"] == "liable":
        sat, liable_set = decide_liability_from_case(case)

        if query["mode"] == "set":
            return sat, {"liable_set": sorted(list(liable_set))}

        target = query["args"][0]
        is_liable = target in liable_set
        return sat, {"target": target, "is_liable": is_liable, "liable_set": sorted(list(liable_set))}

    raise ValueError("Unsupported predicate: " + str(query["predicate"]))
