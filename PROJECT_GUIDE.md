# Project guide (sanity map)

This file is a *quick map* of what each module does in the current codebase.
It is meant to reduce cognitive load while you iterate.

## KB compilation

See README: four modes from `PIPELINE_USE_LE` × `PIPELINE_KB_TWO_PHASE` (direct single-shot, direct two-phase, LE single-shot, LE + two-phase). Implementation: `pipeline/kb/compiler.py`, `pipeline/kb/staged_compile.py`, `pipeline/kb/compile_strategy.py`.

JSON runs: optional `run.json` field `kb_compile_strategy`; CLI `--kb-strategy` overrides it and `.env`. Results include `kb_compile_strategy` / `kb_compile_flags`; `run.json` is merged after a successful run.

## Scripts (`scripts/`)

See `scripts/README.md`. Notable: **`diagnose_unsat.py` is not run by the pipeline**—it is a manual tool. KB compilation uses `pipeline/kb/semantic_check.py` (`check_kb_semantic`, `explain_unsat_fo`) on **KB + minimal structure**; `diagnose_unsat.py` composes **KB + case** for reasoning-time UNSAT debugging.

## End-to-end flow

`main.py` (demo runner)
  -> `pipeline/app/pipeline.py::answer_legal_prompt(...)`
     1) **Extraction prompt** built from `prompts/extraction/extraction_debug_prompt.txt` (for result metadata; actual extraction uses `prompts/extraction/openai_extract_*` prompts)
     2) **Extraction** via `pipeline/extraction/extractor.py` (case) and `pipeline/extraction/openai_extractor.py` (LLM calls)
     3) **Validation & normalization** via `pipeline/validation/fo_validation.py`
        - schema-driven symbol/arity checks use `kb_schema.json` from `pipeline/kb/schema.py`
     4) **Routing** to a *symbolic intent* via `pipeline/symbolic/router.py`
     5) **IDP-Z3 execution** (generic) via `idp_z3/*`
     6) **Rendering** into a final answer via `pipeline/rendering/answer_renderer.py`

## Where the symbolic logic lives

### Router

`pipeline/symbolic/router.py`
  - Translates "predicate" queries (UI surface form) into intent queries
    (backend semantic job).
  - Current mapping:
    - predicate + mode=boolean -> intent `deduction`
    - predicate + mode=set     -> intent `deduction_set`
  - Intent queries are passed through directly.

### Intents

`idp_z3/intents/*.py`
  - One file per intent.
  - All intent handlers implement:

    `def run(case, base_kb_text, query) -> (sat_or_ok, payload_dict)`

  - Implemented:
    - `satisfiable`     : SAT(T ∧ Case)
    - `model_checking`  : alias of satisfiable, without model list
    - `model_expansion` : returns up to N models for T ∧ Case
    - `deduction`       : entailment-style SAT checks for a ground atom
    - `deduction_set`   : runs `deduction` over all constants found in facts
    - `propagation`, `get_range`, `relevance`, `optimization`:
      thin wrappers that call optional helpers in the IDP python bindings.

### Predicate solving (generic)

`idp_z3/predicate_solver.py`
  - Takes a schema-agnostic predicate + args and builds a constraint
    using auxiliary selection predicates (`__sel0`, ...), so constants never
    appear in the theory.
  - Calls into `idp_z3/tasks.satisfiable_check_with_constraint` twice:
    SAT(T ∧ Case ∧ φ) and SAT(T ∧ Case ∧ ¬φ)
  - Returns {possible, certain}.

### Structure builder

`idp_z3/case_structure.py`
  - `build_structure_block_from_facts()`: canonical builder used by `idp_z3/tasks.py`.
  - Parses case facts, builds predicate extensions, infers domain, close-world for condition predicates.

### IDP calls

`idp_z3/tasks.py`
  - Builds the final FO(.) program string:
    KB text + structure from facts + optional injected helpers + optional Q theory.
  - Uses `idp_z3/idp_backend.py::run_idp(...)`.

## Debug mode

Set environment variable:

`PIPELINE_DEBUG=1`

This enables low-noise traces like:

`[DEBUG] router.run_query: type=predicate`
`[DEBUG] intents.model_expansion.run: max_models=3`

In debug mode, `tasks.satisfiable_check_with_constraint` also prints the **exact
FO(.) program** passed to IDP (this is your main sanity-check tool).
