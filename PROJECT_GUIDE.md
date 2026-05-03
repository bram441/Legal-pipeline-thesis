# Project guide (sanity map)

Quick map of the current architecture after the JSON-IR integration.

## 1) Unified backend modes

Use `--pipeline-backend` (preferred):

- `legacy`: legacy KB + legacy extraction
- `json_ir`: JSON-IR KB + JSON-IR extraction

`--kb-backend` still exists for backward compatibility, but unified mode is the intended switch.

## 2) End-to-end flow

`main.py` -> `pipeline/app/pipeline.py::answer_legal_prompt(...)`

1. KB compile/load (`pipeline/kb/cache.py`)
2. KB schema extraction (`pipeline/kb/schema.py`)
3. Case extraction (`pipeline/extraction/extractor.py`)
4. Query extraction (`pipeline/extraction/extractor.py`)
5. Case/query validation (`pipeline/validation/fo_validation.py`)
6. Symbolic routing (`pipeline/symbolic/router.py`)
7. IDP-Z3 execution (`idp_z3/tasks.py`, `idp_z3/intents/*`)
8. Rendering (`pipeline/rendering/answer_renderer.py`)

## 3) LLM vs Python vs IDP-Z3

- LLM:
  - KB generation (or KB JSON-IR generation)
  - Case/query extraction (legacy direct JSON or extraction JSON-IR)
  - Repair retries (with structured feedback)
- Python:
  - deterministic normalization/sanitization
  - schema enforcement, arity/type checks
  - backend selection, retry orchestration, caching, scoring
- IDP-Z3:
  - FO(.) parse/type checks
  - satisfiability and deduction checks

## 4) Extraction backends

### Legacy extraction

- LLM returns final case/query shapes directly.
- Python validates and applies generic corrections.

### JSON-IR extraction

- LLM returns constrained IR:
  - case IR: entities + assertions
  - query IR: predicate hint + mode + args
- Python deterministically resolves to canonical schema symbols and validated query objects.

Files:
- `pipeline/extraction/openai_extractor.py`
- `pipeline/extraction/json_ir.py`
- `pipeline/extraction/extractor.py`

## 5) Symbolic core

- Router: `pipeline/symbolic/router.py`
  - predicate boolean -> `deduction`
  - predicate set -> `deduction_set`
- Predicate solver: `idp_z3/predicate_solver.py`
  - builds selector constraints (`__sel0`, ...)
- Tasks: `idp_z3/tasks.py`
  - composes KB + structure + query theory
- Structure builder: `idp_z3/case_structure.py`

## 6) Strategy knobs

- KB strategy (`--kb-strategy` / run metadata):
  - `direct_single`, `direct_two_phase`, `le_single`, `le_two_phase`
- Pipeline backend (`--pipeline-backend`):
  - `legacy`, `json_ir`

Run metadata now includes:
- `kb_compile_strategy`
- `kb_compile_backend`
- `kb_compile_flags`
- `pipeline_backend_mode`

## 7) Debugging

Set `PIPELINE_DEBUG=1` to print trace logs.

`run_trace.txt` + `results.json` + `score.json` are the primary diagnostics.
