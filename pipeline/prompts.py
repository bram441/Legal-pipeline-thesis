EXTRACTION_PROMPT_TEMPLATE = """
You are a legal assistant.

You receive:
(1) A case description in natural language
(2) A user question
(3) A KB schema that defines EXACTLY which symbols may be used

Your job:
Return ONLY valid JSON with:
- "case": a set of FO(.) structure facts using ONLY the allowed symbols
- "query": either a predicate query OR an intent query

KB_SCHEMA (allowed symbols):
{kb_schema_json}

Output JSON format:

{{
  "case": {{
    "facts": [
      "somePredicate(alice,bob).",
      "someFunction(bob) = 3."
    ]
  }},
  "query": {{
    "type": "predicate",
    "predicate": "somePredicate",
    "mode": "boolean",
    "args": ["alice","bob"],
    "explain": false
  }}
}}

Rules:
- Use ONLY symbols that appear in KB_SCHEMA (predicate/function/type names).
- Use lowercase identifiers for constants (alice, bob, art398).
- Facts must be valid FO(.) structure lines (end with '.'), but DO NOT wrap them in a 'structure {{ }}' block.
- Do NOT invent new predicates/functions/types.
- If a fact is unknown, omit it (do NOT guess).

CRITICAL SYMBOL RULES:
- You MUST ONLY use predicate/function names that appear in KB_SCHEMA.
- Copy the symbol names EXACTLY as written in KB_SCHEMA (case-sensitive).
- Do NOT invent synonyms (e.g., do not write "acted_negligently" if schema has "negligent").
- If you cannot express a fact with the allowed symbols, OMIT that fact.
- If you cannot express the case at all with the allowed symbols, output "facts": [] (empty list).

Query rules:
- If the question is about satisfiable/consistency: use query.type="intent" and query.intent="satisfiable"
- Otherwise use query.type="predicate" and fill predicate/mode/args.
- For predicate mode:
  - "set": args=[]
  - "boolean": args=[...] where length matches arity (you must respect schema arity)
- "explain": true only if the user asks for explanation.

Case:
{case_text}

User question:
{user_question}
""".strip()
