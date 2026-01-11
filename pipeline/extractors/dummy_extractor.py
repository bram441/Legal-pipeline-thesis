# Produces a deterministic, hard-coded (or heuristic) extraction result for development.
# This bypasses any LLM calls and returns a minimal structured object with:
#   - "case": facts (parties/negligent/caused_damage)
#   - "query": what to ask the symbolic layer (predicate/mode/args/explain)
# Used for debugging the pipeline end-to-end without external dependencies.
#
# Params:
#   case_text (str): Natural-language case description (currently ignored or minimally parsed).
#   user_question (str): Natural-language user question (used to choose query shape).
#
# Returns:
#   dict: {"case": {...}, "query": {...}} in the same format expected by schema validation.

def extract_case_and_query_dummy(case_text, user_question):
    text = (case_text or "").lower()
    q = (user_question or "").lower()

    parties = []
    for name in ["alice", "bob", "charlie", "dave"]:
        if name in text or name in q:
            parties.append(name)

    negligent = []
    caused_damage = []

    if "alice" in parties and ("speed" in text or "violat" in text or "fault" in text or "neglig" in text):
        negligent.append("alice")

    if "alice" in parties and ("damage" in text or "crash" in text or "hit" in text):
        caused_damage.append("alice")

    explain = False
    if "why" in q or "explain" in q or "because" in q:
        explain = True

    if "who" in q and "liable" in q:
        query = {
            "type": "predicate",
            "predicate": "liable",
            "mode": "set",
            "args": [],
            "explain": explain,
        }
    else:
        arg = None
        for p in parties:
            if p in q:
                arg = p
                break

        if "liable" in q and arg is not None:
            query = {
                "type": "predicate",
                "predicate": "liable",
                "mode": "boolean",
                "args": [arg],
                "explain": explain,
            }
        else:
            query = {
                "type": "predicate",
                "predicate": "liable",
                "mode": "set",
                "args": [],
                "explain": explain,
            }

    return {
        "case": {
            "parties": parties,
            "negligent": negligent,
            "caused_damage": caused_damage,
        },
        "query": query,
    }
