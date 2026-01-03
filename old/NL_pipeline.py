# nl_pipeline.py
#
# Minimal Versus-LM–style outer loop:
# NL text -> extraction (stub) -> {case, query} -> validation/normalization
# -> symbolic inference (IDP) -> NL answer (+ optional explanation)
#
# Notes:
# - This file is intentionally minimal and debuggable.
# - It supports ONE predicate query right now: liable(p)
# - It already supports different question modes (set vs boolean) and "explain".
# - Extending to new predicates later should be incremental (add a new handler).

import re
import json

from legal_kb import decide_liability_from_case


EXTRACTION_PROMPT_TEMPLATE = """
You are a legal assistant. You receive:
(1) A short description of a civil case (facts in natural language)
(2) A legal question from the user

Your job is to extract a minimal structured object with TWO parts:
- "case": facts for the knowledge base
- "query": what the user is asking, in a structured way

Return ONLY valid JSON with this schema:

{{
  "case": {{
    "parties": ["alice", "bob"],
    "negligent": ["alice"],
    "caused_damage": ["alice"]
  }},
  "query": {{
    "type": "predicate",
    "predicate": "liable",
    "mode": "set",
    "args": [],
    "explain": false
  }}
}}

Rules:
- Use lowercase identifiers (alice, bob, charlie)
- Use underscores instead of spaces
- No extra keys beyond those shown
- "negligent" and "caused_damage" must be subsets of "parties"
- If unknown, use empty lists
- query.mode is either:
  - "set" for "who is liable?"
  - "boolean" for "is X liable?"
- For boolean mode, put the party in query.args, e.g. ["alice"]

Case:
{case_text}

User question:
{user_question}
""".strip()


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
    """
    Validates and canonicalizes the 'case' part.
    Returns a canonical dict, or raises ValueError.
    """
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
    """
    Validates and canonicalizes the 'query' part.
    Returns canonical dict, or raises ValueError.
    """
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


def extract_case_and_query_dummy(case_text, user_question):
    """
    Stub extractor (LLM stand-in).
    It returns a dict with keys: "case" and "query".
    Replace this later with a real LLM call returning JSON.
    """
    text = (case_text or "").lower()
    q = (user_question or "").lower()

    parties = []
    for name in ["alice", "bob", "charlie", "dave"]:
        if name in text or name in q:
            parties.append(name)

    negligent = []
    caused_damage = []

    # Very naive heuristics for the toy model
    if "alice" in parties and ("speed" in text or "violat" in text or "fault" in text or "neglig" in text):
        negligent.append("alice")

    if "bob" in parties and ("neglig" in text or "fault" in text):
        # This is intentionally simplistic; keep it as a stub.
        pass

    if "alice" in parties and ("damage" in text or "crash" in text or "hit" in text):
        caused_damage.append("alice")

    # Query inference (still minimal):
    # - "who is liable" -> set mode
    # - "is alice liable" -> boolean mode args=["alice"]
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
        # Try to detect "is X liable?"
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
            # Default fallback: "who is liable?"
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


def run_query(case, query):
    """
    Routes the query to the appropriate symbolic handler.
    Returns (sat, result).
    """
    if query["type"] != "predicate":
        raise ValueError("Unsupported query.type: " + str(query["type"]))

    if query["predicate"] == "liable":
        sat, liable_set = decide_liability_from_case(case)

        if query["mode"] == "set":
            return sat, {"liable_set": sorted(list(liable_set))}

        # boolean mode
        target = query["args"][0]
        is_liable = target in liable_set
        return sat, {"target": target, "is_liable": is_liable, "liable_set": sorted(list(liable_set))}

    raise ValueError("Unsupported predicate: " + str(query["predicate"]))


def _explain_liable(case, query, result):
    """
    Minimal explanation generator for the toy rule:
      negligent(p) & causedDamage(p) => liable(p)
    This is not a formal proof trace; it's a grounded witness explanation.
    """
    facts_negligent = set(case["negligent"])
    facts_caused = set(case["caused_damage"])

    lines = []
    lines.append("Toy rule used: if a party is negligent and caused damage, then they are liable.")

    if not result:
        return "\n".join(lines)

    if query["mode"] == "set":
        liable = result.get("liable_set", [])
        if not liable:
            lines.append("No party satisfied both conditions (negligent and caused_damage).")
            return "\n".join(lines)

        lines.append("Witnesses:")
        for p in liable:
            lines.append("- " + p + " is liable because negligent(" + p + ") is true and causedDamage(" + p + ") is true.")
        return "\n".join(lines)

    target = result.get("target", "")
    is_liable = bool(result.get("is_liable", False))

    if not target:
        return "\n".join(lines)

    if is_liable:
        lines.append(
            target
            + " is liable because negligent("
            + target
            + ") and causedDamage("
            + target
            + ") are both true."
        )
        return "\n".join(lines)

    missing = []
    if target not in facts_negligent:
        missing.append("negligent(" + target + ")")
    if target not in facts_caused:
        missing.append("causedDamage(" + target + ")")

    if missing:
        lines.append(target + " is not liable because the following required condition(s) were not established: " + ", ".join(missing) + ".")
    else:
        lines.append(target + " is not liable under the toy rule.")
    return "\n".join(lines)


def render_answer(case, query, sat, result):
    """
    Turns the symbolic result into a user-facing NL answer.
    Optionally appends an explanation.
    """
    if not sat:
        return {
            "answer": "The extracted facts lead to an inconsistent knowledge base, so the question cannot be answered.",
            "explanation": None,
        }

    if query["type"] != "predicate":
        return {
            "answer": "Unsupported query type.",
            "explanation": None,
        }

    explanation_text = None

    if query["predicate"] == "liable":
        if query["mode"] == "set":
            liable = result.get("liable_set", [])
            if not liable:
                answer = "Based on the extracted facts and the toy rule, no party is liable."
            elif len(liable) == 1:
                answer = "Based on the extracted facts and the toy rule, " + liable[0] + " is liable."
            else:
                answer = "Based on the extracted facts and the toy rule, the liable parties are: " + ", ".join(liable) + "."
        else:
            target = result.get("target", "")
            is_liable = bool(result.get("is_liable", False))
            if is_liable:
                answer = "Yes. Based on the extracted facts and the toy rule, " + target + " is liable."
            else:
                answer = "No. Based on the extracted facts and the toy rule, " + target + " is not liable."

        if query.get("explain", False):
            explanation_text = _explain_liable(case, query, result)

        return {
            "answer": answer,
            "explanation": explanation_text,
        }

    return {
        "answer": "Unsupported predicate: " + str(query["predicate"]),
        "explanation": None,
    }


def answer_legal_prompt(case_text, user_question):
    """
    End-to-end minimal pipeline:
    NL -> (stub extractor) -> normalized {case, query} -> symbolic -> NL (+ explain)
    """
    extraction_prompt = EXTRACTION_PROMPT_TEMPLATE.format(case_text=case_text, user_question=user_question)

    raw = extract_case_and_query_dummy(case_text, user_question)

    case = normalize_and_validate_case(raw.get("case"))
    query = normalize_and_validate_query(raw.get("query"), case)

    sat, result = run_query(case, query)
    rendered = render_answer(case, query, sat, result)

    return {
        "sat": sat,
        "case": case,
        "query": query,
        "symbolic_result": result,
        "natural_language": rendered["answer"],
        "explanation": rendered["explanation"],
        "extraction_prompt": extraction_prompt,
        "raw_extracted": raw,
    }


if __name__ == "__main__":
    case_text = (
        "Alice was speeding and crashed into Bob's parked car. "
        "Alice clearly violated the traffic rules and admits fault. "
        "Bob's car suffered significant damage."
    )

    user_question_1 = "Who is liable?"
    user_question_2 = "Is Alice liable?"
    user_question_3 = "Why is Alice liable? Please explain."

    for q in [user_question_1, user_question_2, user_question_3]:
        print("\n---")
        print("Q:", q)
        r = answer_legal_prompt(case_text, q)
        print("SAT?", r["sat"])
        print("Case:", json.dumps(r["case"], indent=2))
        print("Query:", json.dumps(r["query"], indent=2))
        print("Answer:", r["natural_language"])
        if r["explanation"]:
            print("Explanation:\n" + r["explanation"])
