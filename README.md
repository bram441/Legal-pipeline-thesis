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
3. **Case extraction**: JSON-IR IR → validated facts (`extraction/json_ir.py`)
4. **Query extraction**: query IR → canonical predicate/args (`query_target_selection.py`, etc.)
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
- Run artifacts: `effective_config.json`, diagnostics (`schema_environment.json`, `symbolic_proof_gap.json`, …)

---

## Configuration (v2)

| Source | Purpose |
|--------|---------|
| `.env` | Secrets: `OPENAI_API_KEY` or `OPENROUTER_API_KEY`; optional `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_MODEL` |
| `config/default.json` | Versioned pipeline behavior (JSON-IR repair limits, extraction backend, scoring, trace) |
| `config/local.json` | Optional gitignored local overrides |
| Environment variables | Backward-compatible overrides (`JSON_IR_*`, `PIPELINE_*`, `SCORE_*`) merged by `pipeline/config.py` |

Each JSON benchmark run writes **`effective_config.json`** (merged config + `llm_runtime` provider/model; no API keys).

**Primary path:** JSON-IR (`--pipeline-backend json_ir`). Legacy direct-FO is **deprecated** — see `docs/DEPRECATED_COMPONENTS.md`.

### Strategy matrix (JSON-IR)

| Strategy | Translation | Legal English |
|----------|-------------|---------------|
| `direct_json_ir_translate` | yes | no |
| `direct_json_ir_no_translate` | no | no |
| `le_json_ir_translate` | yes | yes |
| `le_json_ir_no_translate` | no | yes |

### Thesis test set

Curated tiered benchmarks: **`inputs/json_final/`** (core / challenge / stress). See `inputs/json_final/README_TEST_SET.md` and `manifest.json`.

### Quick start

```bash
pip install -r requirements.txt
cp config/local.json.example config/local.json
# .env: OPENAI_API_KEY=...

python main.py --mode json --run inputs/json_final/run_201 --kb-strategy direct_json_ir_no_translate --no-translate
```

### Evaluation

```bash
# Full matrix (final thesis)
python scripts/run_evaluation.py --runs-dir inputs/json_final --runs all --strategies direct_json_ir_no_translate
```

Reports: `results/reports/evaluation_<timestamp>/` — see `grouped_summary.json` for tier metrics.

**Compare models** (same strategies/config/test set; use a subset first):

```powershell
$env:LLM_PROVIDER="openrouter"
$env:OPENROUTER_API_KEY="..."
python scripts/run_model_sweep.py --provider openrouter `
  --models-file config/model_sweep_models.txt `
  --input-dir inputs/json_final_clean `
  --strategies direct_json_ir_no_translate le_json_ir_no_translate `
  --config config/ablation_balanced.json --ignore-local-config --clean `
  --no-fail-on-missing-score --output-root results/reports/model_sweep_clean_law
```

See `scripts/README.md` and `config/README.md` for OpenAI vs OpenRouter env vars.

### Scoring warnings

- **Unknown / inconclusive is not correct** in default decisive scoring.
- **`model_expansion` possible outputs are not Boolean entailment** — diagnostics only.
- Cells without valid `score.json` are **not** successful runs (`law_compilation`, `evaluation_no_score`, …).

---

## Packages and responsibilities

### `pipeline/app/`
**Single obvious pipeline entrypoint**
- `pipeline.py`
  - top-down orchestration: compile/load KB → extract schema → extract case/query → validate → seed domain → call symbolic tasks → render output

### `pipeline/kb/`
**Law → FO(.) (JSON-IR primary)**
- `json_ir_compile_loop.py` — structured symbol/rules repair loop (limits from config)
- `schema_environment.py` — typed environment for extraction + pre-solver validation
- `factual_case_input.py`, `case_given_bridge.py` — controlled qualitative case inputs
- `compiler.py`, `cache.py`, `schema.py` — compile, cache, FO vocabulary parsing

### `pipeline/validation/`
**Pre-solver contract enforcement**
- `entity_type_mapping.py` — map case entities to KB types
- `pre_solver_validation.py` — domain/signature checks before IDP-Z3

### `pipeline/diagnostics/`
- `symbolic_proof_gap.py` — why a query is unknown/inconclusive

### `pipeline/config.py`
**Central configuration** — loads `config/default.json`, applies env overrides

### `pipeline/extraction/`
**JSON-IR extraction**
- `extractor.py`
  - provider routing, retries, repair feedback loops, backend selection
- `openai_extractor.py`
  - OpenAI calls for JSON-IR extraction schemas
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

See `scripts/README.md` for `run_evaluation.py`, `diagnose_unsat.py`, and how UNSAT explanation relates to `pipeline/kb/semantic_check.py`.

## Prompts

All LLM prompts live under `/prompts` in subfolders (`kb/`, `le/`, `extraction/`, `translation/`, `nl/`); see `pipeline/utils/prompt_loader.py`.

Goals:
- No prompt strings embedded in Python
- Prompts are editable without code changes
- Prompts enforce FO(.) output constraints (especially for KB compilation)

**KB compilation** uses a single canonical symbols-then-rules prompt pair (`prompts/kb/json_ir/generation/symbols.txt` and `rules.txt`), including an illustrative examples appendix and open-world guidance (directly observable status facts, prerequisite closure, safe negative legal-output rules). Optional LE: set `PIPELINE_USE_LE=1` or use `le_json_ir_*` strategies (law → LE → JSON-IR).

CLI:
```text
python main.py --mode json --run inputs/json_final/run_001 --kb-strategy direct_json_ir_no_translate --no-translate
```

Evaluation:
```text
python scripts/run_evaluation.py --runs-dir inputs/json_final --runs run_001 --strategies direct_json_ir_no_translate
```

For many runs, use `scripts/run_evaluation.py` (see `scripts/README.md`) instead of invoking `main.py` per run.

`--kb-backend` is still supported for backward compatibility and experiments, but `--pipeline-backend` is the preferred switch.

**Optional `run.json` fields (JSON runs)**  
- `kb_compile_strategy`: one of `direct_single`, `direct_two_phase`, `le_single`, `le_two_phase`. Used when you do not pass `--kb-strategy` on the CLI.  
- After each successful JSON run, `run.json` is merged with `kb_compile_strategy`, `kb_compile_flags`, `kb_compile_backend`, `extraction_backend`, and `pipeline_backend_mode`.

**CLI override**  
```text
python main.py --mode json --run inputs/json/run_001 --kb-strategy le_two_phase
```
`--kb-strategy` overrides both `run.json` and `.env` for that invocation only.

**Compare strategies on one or many JSON runs** (writes `results/reports/evaluation_<timestamp>/`):

```text
python scripts/run_evaluation.py --runs-dir inputs/json_final --runs run_003 --strategies all
```

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
