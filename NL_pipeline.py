# nl_pipeline.py

import json
from legal_kb import decide_liability_from_case


EXTRACTION_PROMPT_TEMPLATE = """
You are a legal assistant. You receive a short description of a civil case.
Your job is to extract a VERY small set of facts for a toy liability model.

The model assumes:
- A finite set of parties, named in lowercase, with no spaces (e.g. "alice", "bob").
- For each party: whether they were negligent.
- For each party: whether they caused damage.

Return ONLY valid JSON with the following keys:
- "parties": list of strings
- "negligent": list of strings (subset of parties)
- "caused_damage": list of strings (subset of parties)
- "question": the original or simplified question the user is asking

Example input:
"Alice was speeding and hit Bob's parked car. Alice admitted fault. Bob's car was badly damaged. Who is liable?"

Example output:
{{
  "parties": ["alice", "bob"],
  "negligent": ["alice"],
  "caused_damage": ["alice"],
  "question": "Who is liable?"
}}

Now process this case:

{case_text}
"""


def extract_case_from_text_dummy(case_text):
    """
    Temporary stub.
    Replace this later with a real LLM call that uses EXTRACTION_PROMPT_TEMPLATE.
    """
    return {
        "parties": ["alice", "bob"],
        "negligent": ["alice"],
        "caused_damage": ["alice", "bob"],
        "question": "Who is liable?"
    }


def answer_legal_prompt(case_text):
    case = extract_case_from_text_dummy(case_text)

    sat, liable_set = decide_liability_from_case(case)

    if not sat:
        return {
            "sat": False,
            "symbolic_answer": None,
            "natural_language": "The knowledge base is inconsistent or under-specified for this case."
        }

    liable_list = sorted(list(liable_set))

    if not liable_list:
        nl_answer = "According to the current liability rule, no party is liable."
    elif len(liable_list) == 1:
        nl_answer = f"According to the current liability rule, {liable_list[0]} is liable."
    else:
        joined = ", ".join(liable_list)
        nl_answer = f"According to the current liability rule, the following parties are liable: {joined}."

    return {
        "sat": True,
        "symbolic_answer": liable_list,
        "natural_language": nl_answer,
        "case": case
    }


if __name__ == "__main__":
    description = (
        "Alice was speeding and crashed into Bob's parked car. "
        "Alice clearly violated the traffic rules and admits fault. "
        "Bob's car suffered significant damage. Who is liable?"
    )

    result = answer_legal_prompt(description)
    print("SAT?", result["sat"])
    print("Case facts:", result["case"])
    print("Symbolic liable set:", result["symbolic_answer"])
    print("Answer:", result["natural_language"])
