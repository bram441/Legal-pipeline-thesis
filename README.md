# Legal-pipeline

Symbolic-first legal reasoning pipeline for thesis evaluation: an LLM compiles law text to a JSON-IR knowledge base, extracts case facts and queries under strict schema validation, and answers via **IDP-Z3** (FO(.)) rather than by free-form LLM reasoning.

## Quick start (local setup)

### 1. Prerequisites

- **Python 3.11+** (3.12 tested)
- **Git**
- An LLM API key (**OpenRouter** recommended, or OpenAI direct)

### 2. Install

```powershell
cd Legal-pipeline
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure secrets

```powershell
copy .env.example .env
# Edit .env: set OPENROUTER_API_KEY (or OPENAI_API_KEY) and LLM_MODEL
```

Optional local config overrides, not required for reproducible runs:

```powershell
copy config\local.json.example config\local.json
```

### 4. Smoke test: single run

```powershell
python main.py `
  --mode json `
  --run inputs/json_final_clean/run_001 `
  --config config/heavy.json `
  --ignore-local-config `
  --kb-strategy direct_json_ir_no_translate `
  --no-translate
```

### 5. Validate the benchmark folder

```powershell
python scripts/validate_test_set.py --input-dir inputs/json_final_clean
```

### 6. Run a small evaluation

```powershell
python scripts/run_evaluation.py `
  --config config/heavy.json `
  --ignore-local-config `
  --runs-dir inputs/json_final_clean `
  --runs run_001,run_002,run_003 `
  --strategies direct_json_ir_no_translate `
  --output-dir results/reproduction/smoke_eval `
  --clean `
  --no-fail-on-missing-score
```

See **`scripts/README.md`** for budget comparison, model sweep, plain LLM baseline, non-Boolean probe, and VERUS-LM adapter commands.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `main.py` | CLI entry for single text/JSON runs |
| `pipeline/` | Core pipeline: KB compilation, extraction, validation, symbolic routing and scoring |
| `idp_z3/` | IDP-Z3 task wrappers |
| `prompts/` | LLM prompts; prompt text is kept outside Python code |
| `config/` | `default.json` plus thesis budget profiles: `cheap`, `balanced` and `heavy` |
| `inputs/json_final_clean/` | **Primary thesis benchmark**: 37 runs using cleaned law texts |
| `inputs/json_final/` | Equivalent run structure using raw-law paths; retained for optional comparison |
| `inputs/non_boolean_same_laws_testset/` | Set/range/explain capability probe for manual review |
| `inputs/verus_lm_from_json_final_clean/` | Converted input layout for VERUS-LM |
| `example_laws_clean/` | Cleaned law corpora referenced by the primary benchmark |
| `scripts/` | Evaluation harnesses and baselines |
| `tests/` | Unit tests; see `tests/README.md` |
| `results/final/` | Committed thesis result artefacts used for the reported evaluations |

Further reading: **`PROJECT_GUIDE.md`**, **`config/README.md`**, **`scripts/README.md`** and **`inputs/json_final_clean/README_TEST_SET.md`**.

---

## Configuration

Merge order:

```text
config/default.json
→ optional config/local.json
→ optional --config profile
→ environment variables from .env
```

| Source | Purpose |
|--------|---------|
| `.env` | API keys, `LLM_PROVIDER`, `LLM_MODEL` and provider settings |
| `config/default.json` | Repository baseline: scope mode, extraction backend and scoring behaviour |
| `config/heavy.json` | Selected thesis LLM budget overlay |
| `config/local.json` | Optional gitignored local development overrides |

For reproducible thesis runs, always pass:

```text
--config config/heavy.json --ignore-local-config
```

Each run writes **`effective_config.json`**, containing the merged configuration and `llm_runtime` information, but never API keys.

---

## KB strategies: JSON-IR

| Strategy | Translation | Logical English (LE) |
|----------|:-----------:|:--------------------:|
| `direct_json_ir_no_translate` | no | no |
| `direct_json_ir_translate` | yes | no |
| `le_json_ir_no_translate` | no | yes |
| `le_json_ir_translate` | yes | yes |

`LE` refers to the optional **Logical English** preprocessing step performed before JSON-IR generation.

Thesis final choice:

```text
strategy: direct_json_ir_no_translate
config:   config/heavy.json
model:    anthropic/claude-sonnet-4.6
```

---

## Thesis evaluation workflow

The reported thesis evaluation follows this sequence:

1. **Budget-profile selection** — `scripts/run_config_ablation.py` with `cheap`, `balanced` and `heavy`.
2. **Strategy selection** — `scripts/run_evaluation.py --strategies all`.
3. **Model selection** — comparison of Claude Sonnet 4.6, GPT-5.5 and Gemini 3.1 Pro Preview under the selected profile and strategy.
4. **System comparison** — selected JSON-IR pipeline versus direct LLM baselines and VERUS-LM.
5. **Capability probe** — limited non-Boolean probe for manual inspection.

The committed folders under `results/final/` preserve the artefacts used for the thesis tables.

In the reported model comparison, the Claude Sonnet 4.6 observation was reused from the strategy-selection experiment because it had already been produced under the identical selected configuration and strategy. The current `config/model_sweep_top3.txt` contains all three models so that a new user can perform a complete fresh rerun.

New reproduction runs can be written to a separate output directory, while the committed thesis artefacts remain available under `results/final/`:

```powershell
python scripts/run_evaluation.py `
  --config config/heavy.json `
  --ignore-local-config `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --strategies direct_json_ir_no_translate `
  --output-dir results/reproduction/final_json_ir `
  --clean `
  --no-fail-on-missing-score
```

Reports include:

- `matrix.json`
- `summary.csv`
- `report.md`
- `grouped_summary.json`, when a manifest with groups is present.

---

## Pipeline overview

1. **Law scoping** — identify the relevant part of the supplied law excerpt.
2. **Optional language preprocessing** — optional translation and optional Logical English.
3. **KB compilation** — law text to JSON-IR symbols and rules.
4. **Validation and repair** — validate JSON-IR and execute bounded repair attempts.
5. **Deterministic rendering** — valid JSON-IR to FO(.) knowledge base.
6. **Schema environment** — expose valid typed symbols for case and query processing.
7. **Case and query extraction** — extract validated facts and question targets.
8. **Pre-query checks** — validate consistency and satisfiability before answering.
9. **Symbolic reasoning** — route the query to IDP-Z3.
10. **Scoring and diagnostics** — record answer categories, technical failures and proof-gap diagnostics.

Core principles:

- Symbolic-first: IDP-Z3 performs entailment; the LLM does not directly decide the legal answer.
- Open vocabulary: no fixed legal ontology is hard-coded as the thesis task definition.
- Strict schema-driven extraction with bounded LLM repair.
- Open-world semantics with safeguards against unsupported negative legal-output rules.
- Reproducible artefacts for each evaluation cell.

Canonical KB-generation prompts:

```text
prompts/kb/json_ir/generation/symbols.txt
prompts/kb/json_ir/generation/rules.txt
```

---

## Scoring notes

- `UNKNOWN` / inconclusive is a possible pipeline output, but is not a correct gold label in the primary 37-run benchmark.
- `model_expansion` outputs indicate possibility and are diagnostics, not Boolean entailment.
- Technical failures without a valid interpretable answer are reported separately from inconclusive answers.
- For the neuro-symbolic evaluations, answer coverage counts correct decisive, incorrect decisive and inconclusive outputs, but not technical failures without an interpretable answer.

---

## Tests

Run thesis-critical tests:

```powershell
python -m pytest tests/test_json_ir_prompts.py tests/test_query_target_selection.py tests/test_ignore_local_config.py tests/test_validate_test_set.py tests/test_run_model_sweep.py -q
```

Run the complete test suite:

```powershell
python -m pytest tests/ -q
```

See `tests/README.md` for test scope and optional environment requirements.

---

## Deduction semantics for Boolean queries

For a grounded Boolean query φ:

- `certain = True` iff `SAT(T ∧ Case ∧ φ)` and `UNSAT(T ∧ Case ∧ ¬φ)`.
- `possible = True` iff `SAT(T ∧ Case ∧ φ)`.

Set queries return entailed (`certain`) and satisfiable (`possible`) instance sets separately.
