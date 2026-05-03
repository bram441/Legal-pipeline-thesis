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
1. **KB compilation (LLM + Python hardening)**: `law_text` → FO(.) KB (`kb.fo`)
2. **Schema extraction (parser)**: `kb.fo` → `kb_schema.json` (types, predicates, functions)
3. **Case extraction**:
   - `legacy` backend: LLM returns `{facts, entities}`
   - `json_ir` backend: LLM returns structured case IR, Python deterministically renders facts
4. **Query extraction**:
   - `legacy` backend: LLM returns query object directly
   - `json_ir` backend: LLM returns query IR (`predicate_hint`, `mode`, `args`, ...), Python resolves canonical predicate/args
5. **Strict validation + repair loop**:
   - Unknown symbol → hard error
   - Arity/type mismatch → hard error
   - Invalid FO(.) syntax → hard error
   - Validation failures are fed back to the LLM for bounded retries
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
**Schema-driven extraction (legacy + JSON-IR backends)**
- `extractor.py`
  - provider routing, retries, repair feedback loops, backend selection
- `openai_extractor.py`
  - OpenAI-specific calls for legacy and JSON-IR extraction schemas
- `json_ir.py`
  - deterministic normalization from extraction IR → validated case/query objects

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

## Scripts

See `scripts/README.md` for `compare_kb_strategies.py`, `diagnose_unsat.py`, and how UNSAT explanation relates to `pipeline/kb/semantic_check.py`.

## Prompts

All LLM prompts live under `/prompts` in subfolders (`kb/`, `le/`, `extraction/`, `translation/`, `nl/`); see `pipeline/utils/prompt_loader.py`.

Goals:
- No prompt strings embedded in Python
- Prompts are editable without code changes
- Prompts enforce FO(.) output constraints (especially for KB compilation)

**KB compilation modes** (set env vars, then run; use separate cache dirs or runs to compare)

| `PIPELINE_USE_LE` | `PIPELINE_KB_TWO_PHASE` | Pipeline |
|-------------------|-------------------------|----------|
| off | off | Law → single-shot FO (`kb/kb_compilation.txt`) |
| off | on | Law → vocab → theory (`kb/kb_*_only.txt`), fallback single-shot |
| on | off | Law → LE → single-shot FO (`le/le_to_fo.txt`) |
| on | on | Law → LE → vocab → theory (`le/le_*_only.txt`), fallback `le_to_fo` |

Repair after validation failure always uses full KB + `kb/kb_compilation_repair_symbolic.txt` (parse/syntax) or `kb/kb_compilation_repair_semantic.txt` (unsat / semantic check), with machine-detected hints (e.g. stray `*`) appended.

To **recompile** and compare modes on the same run, remove the cached `kb.fo` (and optionally `kb_schema.json`) under that run’s `translated/le/` or `translated/` folder, or use a fresh run directory.

## Backend modes (recommended)

Use one unified mode switch for the whole stack:

- `legacy`: legacy KB compiler + legacy extraction
- `json_ir`: JSON-IR KB compiler + JSON-IR extraction

CLI:
```text
python main.py --mode json --run inputs/json/run_001 --pipeline-backend json_ir
```

Evaluation:
```text
python scripts/run_evaluation.py --runs all --pipeline-backend json_ir
```

`--kb-backend` is still supported for backward compatibility and experiments, but `--pipeline-backend` is the preferred switch.

**Optional `run.json` fields (JSON runs)**  
- `kb_compile_strategy`: one of `direct_single`, `direct_two_phase`, `le_single`, `le_two_phase`. Used when you do not pass `--kb-strategy` on the CLI.  
- After each successful JSON run, `run.json` is merged with `kb_compile_strategy`, `kb_compile_flags`, `kb_compile_backend`, and `pipeline_backend_mode`.

**CLI override**  
```text
python main.py --mode json --run inputs/json/run_001 --kb-strategy le_two_phase
```
`--kb-strategy` overrides both `run.json` and `.env` for that invocation only.

**Compare all four strategies on one JSON run** (writes separate folders + `compare_summary.json`):

```text
python scripts/compare_kb_strategies.py --run inputs/json/run_003
```

Output: `inputs/json/run_003/kb_strategy_compare/<strategy>/` for each of `direct_single`, `direct_two_phase`, `le_single`, `le_two_phase`. Use `--clean` to wipe a previous compare folder first.

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
