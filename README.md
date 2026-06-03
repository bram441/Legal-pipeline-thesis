# Legal-pipeline

Symbolic-first legal reasoning pipeline for thesis evaluation: LLM compiles law text to a JSON-IR knowledge base, extracts case facts and queries under strict schema validation, and answers via **IDP-Z3** (FO(.)) — not by free-form LLM reasoning.

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

Optional local config overrides (not required for reproducible runs):

```powershell
copy config\local.json.example config\local.json
```

### 4. Smoke test (single run)

```powershell
python main.py `
  --mode json `
  --run inputs/json_final_clean/run_001 `
  --config config/heavy.json `
  --ignore-local-config `
  --kb-strategy direct_json_ir_no_translate `
  --no-translate
```

Artifacts appear under the run folder (or a working copy if the evaluator creates one).

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
  --output-dir results/reports/smoke_eval `
  --no-fail-on-missing-score
```

See **`scripts/README.md`** for config ablation, model sweep, plain LLM baseline, non-boolean probe, and VERUS-LM adapter commands.

---

## Repository layout

| Path | Purpose |
|------|---------|
| `main.py` | CLI entry for single text/JSON runs |
| `pipeline/` | Core pipeline (KB compile, extraction, symbolic router, scoring) |
| `idp_z3/` | IDP-Z3 task wrappers |
| `prompts/` | All LLM prompts (no prompt strings in Python) |
| `config/` | `default.json` + thesis budget profiles (`cheap` / `balanced` / `heavy`) |
| `inputs/json_final_clean/` | **Primary thesis benchmark** (37 runs, clean law texts) |
| `inputs/json_final/` | Same runs with raw law file paths (optional comparison) |
| `inputs/non_boolean_same_laws_testset/` | Set/range/explain probe (manual review) |
| `inputs/verus_lm_from_json_final_clean/` | Converted VERUS-LM inputs |
| `example_laws_clean/` | Law corpora referenced by `json_final_clean` |
| `scripts/` | Evaluation harnesses and baselines |
| `tests/` | Unit tests — see `tests/README.md` |
| `results/final/` | Thesis selection artifacts (gitignored; keep locally) |

Further reading: **`PROJECT_GUIDE.md`**, **`config/README.md`**, **`scripts/README.md`**.

---

## Configuration

Merge order: **`config/default.json`** → optional **`config/local.json`** → optional **`--config` profile** → **environment variables** (`.env`).

| Source | Purpose |
|--------|---------|
| `.env` | API keys, `LLM_PROVIDER`, `LLM_MODEL` |
| `config/default.json` | Repo baseline (scope mode, extraction backend, scoring) |
| `config/heavy.json` | Selected thesis LLM budget overlay |
| `config/local.json` | Optional gitignored dev overrides |

For reproducible thesis runs, always pass **`--config config/heavy.json --ignore-local-config`**.

Each run writes **`effective_config.json`** (merged config + `llm_runtime`; never API keys).

---

## KB strategies (JSON-IR)

| Strategy | Translation | Legal English (LE) |
|----------|:-----------:|:------------------:|
| `direct_json_ir_no_translate` | no | no |
| `direct_json_ir_translate` | yes | no |
| `le_json_ir_no_translate` | no | yes |
| `le_json_ir_translate` | yes | yes |

Thesis final choice: **`direct_json_ir_no_translate`** with **`config/heavy.json`**.

Deprecated / removed paths: see **`docs/DEPRECATED_COMPONENTS.md`**.

---

## Thesis evaluation workflow

Typical selection sequence (outputs under `results/final/`):

1. **Config selection** — `scripts/run_config_ablation.py` with `cheap` / `balanced` / `heavy`
2. **Strategy selection** — `scripts/run_evaluation.py --strategies all`
3. **Model selection** — `scripts/run_model_sweep.py` with `config/model_sweep_top3.txt`
4. **Final run** — full `json_final_clean` matrix with winning config + strategy + model
5. **Baselines** — `scripts/run_plain_llm_baseline.py`, optional VERUS-LM via `convert_json_final_to_verus_lm.py`

Example final eval command:

```powershell
python scripts/run_evaluation.py `
  --config config/heavy.json `
  --ignore-local-config `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --strategies direct_json_ir_no_translate `
  --output-dir results/final/final_main `
  --clean `
  --no-fail-on-missing-score
```

Reports: `matrix.json`, `summary.csv`, `report.md`, and `grouped_summary.json` (tier metrics from `manifest.json`).

---

## Pipeline overview

1. **KB compilation** — law text → JSON-IR symbols + rules → FO(.) (`pipeline/kb/`)
2. **Schema environment** — typed symbols for extraction and validation
3. **Case / query extraction** — JSON-IR IR with repair loops (`pipeline/extraction/`)
4. **Pre-solver validation** — entities, domains, signatures
5. **Symbolic reasoning** — intent routing → IDP-Z3 (`pipeline/symbolic/`, `idp_z3/`)
6. **Scoring** — decisive Boolean match vs gold label (`pipeline/eval/`)

Core principles:

- Symbolic-first: IDP-Z3 performs entailment; the LLM does not decide the answer.
- Open vocabulary: no hard-coded legal ontology in Python.
- Strict schema-driven extraction with bounded LLM repair.
- Open-world semantics with guards against unsafe inverse negative legal-output rules.

KB prompts: single canonical pair `prompts/kb/json_ir/generation/symbols.txt` and `rules.txt` (includes illustrative examples appendix).

---

## Scoring notes

- **Unknown / inconclusive is not correct** under default decisive scoring.
- **`model_expansion` possible outputs are diagnostics**, not Boolean entailment.
- Cells without valid `score.json` count as failures (`law_compilation`, `evaluation_no_score`, …).

---

## Tests

```powershell
python -m pytest tests/test_json_ir_prompts.py tests/test_query_target_selection.py tests/test_ignore_local_config.py tests/test_validate_test_set.py tests/test_run_model_sweep.py -q
```

Full suite: `python -m pytest tests/ -q` (some legacy tests may fail; see `tests/README.md`).

---

## Deduction semantics (boolean queries)

For grounded boolean query φ:

- `certain = True` iff SAT(T ∧ Case ∧ φ) and UNSAT(T ∧ Case ∧ ¬φ)
- `possible = True` iff SAT(T ∧ Case ∧ φ)

Set queries return entailed (`certain`) and satisfiable (`possible`) instance sets separately.
