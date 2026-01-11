from idp_z3.legal_kb import decide_liability_from_case

# Routes a normalized query to the appropriate symbolic solver and returns structured results.
# This is the dispatch layer between the general pipeline and specific symbolic KB modules.
# In the current minimal version, it supports liability queries and calls idp_z3/legal_kb.py.
#
# Params:
#   case (dict): Normalized case facts.
#   query (dict): Normalized query specification (predicate/mode/args/explain).
#
# Returns:
#   tuple[bool, dict]:
#     - sat (bool): Whether the FO(.) theory is satisfiable for the case
#     - result (dict): Structured symbolic result (e.g., liable_set, is_liable, target, etc.)
#
# Raises:
#   ValueError: If the query is unsupported or malformed.
#   Other exceptions may propagate from the IDP backend if the FO(.) program fails.

# pipeline/symbolic/router.py



def run_query(case, query, base_kb_text):
    """
    Dispatches query to the relevant solver using the provided base KB.
    """
    if query["type"] != "predicate":
        raise ValueError("Unsupported query.type: " + str(query["type"]))

    if query["predicate"] != "liable":
        raise ValueError("Unsupported predicate: " + str(query["predicate"]))

    sat, liable_set = decide_liability_from_case(case, base_kb_text=base_kb_text)

    if not sat:
        return False, {}

    if query["mode"] == "set":
        return True, {"liable_set": sorted(list(liable_set))}

    target = query["args"][0]
    return True, {"target": target, "is_liable": target in liable_set, "liable_set": sorted(list(liable_set))}
