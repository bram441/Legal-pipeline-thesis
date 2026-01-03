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
