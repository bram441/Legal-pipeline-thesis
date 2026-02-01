# Architecture

This project implements a symbolic-first legal reasoning pipeline inspired by Versus-LM, using IDP-Z3 (FO(.)) as the sole reasoning backend.

Core principles:

- Symbolic-first: all reasoning is performed by IDP-Z3, not by Python or the LLM.
- Open vocabulary: no hard-coded predicate or type ontology in Python.
- Schema-driven extraction & strict validation: case facts and queries must use only symbols present in the extracted KB schema.
- Intent-based routing: natural-language questions are routed to solver tasks by intent (deduction, propagation, etc.), not by predicate-specific code.
- Constants cannot appear in the FO(.) theory: selection predicates (e.g., `__sel0`) are used for grounded queries.

---

## High-level flow

Inputs:
- `law_text` (plain text)
- `case_text` (plain text)
- `question_text` (plain text)

Pipeline:
1. **KB compilation (LLM)**: `law_text` → FO(.) KB (`kb.fo`)
2. **Schema extraction (parser)**: `kb.fo` → `kb_schema.json` (types, predicates, functions)
3. **Case extraction (LLM, schema-driven)**: `case_text` → `{ facts, entities }`
4. **Query extraction (LLM, schema-driven)**: `question_text` → normalized query object (predicate-mode queries are normalized into intents)
5. **Strict validation**:
   - Unknown symbol → hard error
   - Arity/type mismatch → hard error
   - Invalid FO(.) syntax → hard error
6. **Domain seeding**:
   - Uses `case.entities` keyed by KB types (e.g., `"Person": ["alice","bob"]`)
   - No hard-coded `"Party"` type in code
7. **Symbolic reasoning (IDP-Z3)**:
   - Construct FO(.) program with KB + structure + task constraints
   - Run IDP-Z3 to get SAT/UNSAT or models/propagations
8. **Rendering**:
   - Format answer
   - Optionally generate explanation and NL paraphrase (LLM) using grounded, minimal prompt templates

Outputs:
- Answer text
- Optional explanation (rule snippets + relevant facts + constraint checked + possible/certain)
- Optional natural-language paraphrase

---

## Packages and responsibilities

### `pipeline/app/`
**Single obvious pipeline entrypoint**
- `pipeline.py`
  - top-down orchestration: compile/load KB → extract schema → extract case/query → validate → seed domain → call symbolic tasks → render output

### `pipeline/kb/`
**Law → FO(.)**
- `compiler.py`
  - calls the LLM to compile law text into FO(.) KB
- `schema.py`
  - parses the vocabulary in `kb.fo` into `kb_schema.json`
- `cache.py`
  - `get_or_compile_kb(run_dir, law_text, model)` loads cached KB/schema or compiles anew

### `pipeline/extraction/`
**Schema-driven extraction**
- `extractor.py`
  - provider routing, retries, and feedback loops (if enabled)
- `openai_extractor.py`
  - OpenAI-specific calls for case extraction and query extraction

### `pipeline/validation/`
**Strict schema-driven validation**
- `fo_validation.py`
  - validates:
    - `case.facts` (symbols exist in schema, arity, FO(.) atom syntax)
    - `case.entities` (type keys exist in schema types)
    - `query` object (known predicate and arg types or intent fields)

### `pipeline/domain/`
**Domain seeding**
- `seeding.py`
  - heuristics to extract candidate entity names from case text
  - attaches them under a KB type derived from schema (e.g. first type)

### `pipeline/symbolic/`
**Intent routing**
- `router.py`
  - converts predicate queries into canonical intents
  - dispatches to IDP-Z3 tasks based on intent

### `pipeline/rendering/`
**Answer formatting and explanations**
- `answer_renderer.py`
  - formats boolean / set answers consistently
- `explanations.py`
  - composes grounded explanation objects
- `nl_paraphrase.py`
  - optional LLM paraphrase from grounded content only (prompt-driven)

### `pipeline/utils/`
**Helpers**
- `prompt_loader.py`
  - loads prompt files from `/prompts` and renders only explicit `{placeholders}`

---

## Prompts

All LLM prompts live in `/prompts`.

Goals:
- No prompt strings embedded in Python
- Prompts are editable without code changes
- Prompts enforce FO(.) output constraints (especially for KB compilation)

---

## Deduction semantics (boolean predicate queries)

For boolean queries such as “Is Alice liable?”:

Let φ be the grounded statement (implemented via selection predicate constraints).

We check:
- SAT(T ∧ Case ∧ φ)
- SAT(T ∧ Case ∧ ¬φ)

Then:
- `certain = True` iff first is SAT and second is UNSAT
- `possible = True` iff first is SAT

Set queries (“Who is liable?”) return two sets:
- `certain` set: entailed instances
- `possible` set: satisfiable instances

---

## Design constraints (non-negotiable)

- No hard-coded legal predicates/types in Python.
- No ontology layer.
- IDP-Z3 is the only reasoning engine.
- Strict validation is intentional (later used for feedback loops).
- Constants must not appear in theory; selection predicates are used.
