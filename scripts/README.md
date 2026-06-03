# Utility scripts

Run all commands from the **project root** (`Legal-pipeline/`).

## Overview

| Script | Run directly? | Role |
|--------|:-------------:|------|
| [`run_evaluation.py`](#run_evaluationpy) | yes | **Main benchmark runner** — JSON runs × strategies → matrix, CSV, report |
| [`run_config_ablation.py`](#run_config_ablationpy) | yes | Compare config profiles (`cheap` / `balanced` / `heavy`) |
| [`run_model_sweep.py`](#run_model_sweeppy) | yes | Compare LLM models on the same strategy + config |
| [`run_plain_llm_baseline.py`](#run_plain_llm_baselinepy) | yes | Plain LLM baseline (law + case + question, no symbolic pipeline) |
| [`run_non_boolean_probe.py`](#run_non_boolean_probepy) | yes | Non-boolean / intent probe set (manual review, no auto-score) |
| [`convert_json_final_to_verus_lm.py`](#verus-lm-adapter) | yes | Convert thesis test set → VERUS-LM input layout |
| [`run_verus_lm_evaluation.py`](#verus-lm-adapter) | yes | Run VERUS-LM on converted test set |
| [`validate_test_set.py`](#validate_test_setpy) | yes | Static validation of benchmark folders (no LLM) |
| [`diagnose_unsat.py`](#diagnose_unsatpy) | yes | Manual UNSAT debugging for one run folder |
| [`eval_support.py`](#internal-libraries) | no | Shared helpers for `run_evaluation.py` |
| [`eval_grouped_metrics.py`](#internal-libraries) | no | Tier/group metrics for `inputs/json_final*` manifests |

### What you need for the thesis

| Phase | Script | Typical output |
|-------|--------|----------------|
| Config selection | `run_config_ablation.py` | `results/final/config_selection/` |
| Strategy selection | `run_evaluation.py` | `results/final/strategy_selection_final/` |
| Model selection | `run_model_sweep.py` | `results/final/model_selection_final/` |
| Final JSON-IR eval | `run_evaluation.py` | `results/final/...` |
| Plain LLM baseline | `run_plain_llm_baseline.py` | `results/final/plain_llm_baseline/` |
| Non-boolean probe | `run_non_boolean_probe.py` | `results/final/non_boolean_probe_test/` |
| VERUS-LM comparison | `convert_json_final_to_verus_lm.py` + `run_verus_lm_evaluation.py` | converted inputs + eval report |

### Debug-only (not needed for benchmark runs)

- **`diagnose_unsat.py`** — manual UNSAT investigation for a single run folder.

---

## `run_evaluation.py`

Main evaluation harness. Runs `main.py` for each `(run, strategy)` cell, scores when possible, and writes an aggregate report.

**Outputs** (under `--output-dir`, default `results/reports/evaluation_<timestamp>/`):

- `matrix.json` — full cell results + LLM call summary
- `report.md`, `summary.csv` — human-readable tables
- `grouped_summary.json` — tier metrics when `manifest.json` is present
- `work/<run>/<strategy>/` — per-cell artifacts (`results.json`, `score.json`, …)

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

Compare all four JSON-IR strategies:

```powershell
python scripts/run_evaluation.py `
  --config config/heavy.json `
  --ignore-local-config `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --strategies all `
  --output-dir results/final/strategy_selection_final `
  --clean `
  --no-fail-on-missing-score
```

Notes:

- `--input-dir` is an alias for `--runs-dir`.
- Model/provider come from `.env` (`LLM_PROVIDER`, `LLM_MODEL`, …).
- Use `--ignore-local-config` for reproducible thesis runs.

---

## `run_config_ablation.py`

Runs `run_evaluation.py` once per config profile without editing `config/local.json`. Passes `--ignore-local-config` automatically.

Default output root: `results/reports/config_<timestamp>/` (override with `--output-root`).

```powershell
python scripts/run_config_ablation.py `
  --profiles config/cheap.json config/balanced.json config/heavy.json `
  --runs all `
  --runs-dir inputs/json_final_clean `
  --strategies direct_json_ir_no_translate `
  --output-root results/final/config_selection_final
```

Each profile gets a subfolder named after the config stem (`cheap`, `balanced`, `heavy`).

---

## `run_model_sweep.py`

Runs `run_evaluation.py` once per model and aggregates `model_sweep_summary.json` / `.csv` / `model_sweep_report.md`.

```powershell
python scripts/run_model_sweep.py `
  --provider openrouter `
  --models-file config/model_sweep_top3.txt `
  --input-dir inputs/json_final_clean `
  --runs all `
  --strategies direct_json_ir_no_translate `
  --config config/heavy.json `
  --ignore-local-config `
  --clean `
  --no-fail-on-missing-score `
  --output-root results/final/model_selection_final
```

Model list files: `config/model_sweep_top3.txt` (thesis top-3) or copy `config/model_sweep_models.example.txt` to a custom list. One model id per line; `#` comments allowed.

---

## `run_plain_llm_baseline.py`

Direct LLM baseline: prompt = law + case + question only (no KB compile, no IDP-Z3, no gold label in prompt). Answers must be `TRUE` / `FALSE` / `UNKNOWN`.

Loads `.env` automatically (e.g. `OPENROUTER_API_KEY`).

```powershell
python scripts/run_plain_llm_baseline.py `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --models "anthropic/claude-sonnet-4.6,openai/gpt-5.5,google/gemini-3.1-pro-preview" `
  --output-dir results/final/plain_llm_baseline `
  --base-url "https://openrouter.ai/api/v1" `
  --temperature 0 `
  --max-tokens 32
```

Dry-run / task inspection:

```powershell
python scripts/run_plain_llm_baseline.py `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --models "anthropic/claude-sonnet-4.6" `
  --output-dir results/final/plain_llm_baseline_debug `
  --dry-run `
  --debug-dump-tasks 3
```

---

## `run_non_boolean_probe.py`

Runs the JSON-IR pipeline on `inputs/non_boolean_same_laws_testset/` (set/range/explain intents). Converts probe JSON → temporary `run.json` folders, calls `main.py`, writes manual-review summaries. **No automatic scoring.**

```powershell
python scripts/run_non_boolean_probe.py `
  --input-dir inputs/non_boolean_same_laws_testset `
  --output-dir results/final/non_boolean_probe_test `
  --model anthropic/claude-sonnet-4.6 `
  --strategy direct_json_ir_no_translate `
  --config config/heavy.json `
  --explain `
  --limit 3 `
  --clean
```

---

## VERUS-LM adapter

External baseline comparison against [VERUS-LM](https://github.com/...) (separate install required).

**1. Convert test set**

```powershell
python scripts/convert_json_final_to_verus_lm.py `
  --input-dir inputs/json_final_clean `
  --output-dir inputs/verus_lm_from_json_final_clean
```

**2. Run VERUS-LM evaluation**

```powershell
python scripts/run_verus_lm_evaluation.py `
  --input-dir inputs/verus_lm_from_json_final_clean `
  --output-dir results/final/verus_lm_eval
```

These scripts are only needed if the thesis includes a VERUS-LM comparison chapter.

---

## `validate_test_set.py`

Static checks on benchmark folders: manifest consistency, `run.json` shape, no stray generated artifacts. No LLM, no IDP.

```powershell
python scripts/validate_test_set.py --input-dir inputs/json_final_clean
python scripts/validate_test_set.py --input-dir inputs/json_final_clean --strict
```

Run this before large evaluations or after editing the test set.

---

## `diagnose_unsat.py`

Manual debugging when KB + case is UNSAT. Uses the real compiled KB and case structure from a run folder.

```powershell
python scripts/diagnose_unsat.py inputs/json_final_clean/run_003
```

See also `pipeline/kb/semantic_check.py` (referenced from pipeline code).

---

## Internal libraries

Do **not** run these directly:

| Module | Imported by |
|--------|-------------|
| `eval_support.py` | `run_evaluation.py` — failure classification, matrix helpers |
| `eval_grouped_metrics.py` | `run_evaluation.py` — tier/group metrics from `manifest.json` |

---

## Single-run alternative

For one run / one question, use `main.py` directly instead of `run_evaluation.py`:

```powershell
python main.py `
  --mode json `
  --run inputs/json_final_clean/run_001 `
  --config config/heavy.json `
  --ignore-local-config `
  --kb-strategy direct_json_ir_no_translate `
  --no-translate
```

---

## Tests

```powershell
python -m pytest tests/test_eval_support.py tests/test_validate_test_set.py tests/test_ignore_local_config.py tests/test_run_model_sweep.py -q
```
