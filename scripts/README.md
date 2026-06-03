# Utility scripts

Run all commands from the **project root**:

```text
Legal-pipeline/
```

## Overview

| Script | Run directly? | Role |
|--------|:-------------:|------|
| [`run_evaluation.py`](#run_evaluationpy) | yes | Main benchmark runner: JSON runs × strategies to reports and artefacts |
| [`run_config_ablation.py`](#run_config_ablationpy) | yes | Compare budget profiles: `cheap`, `balanced`, `heavy` |
| [`run_model_sweep.py`](#run_model_sweeppy) | yes | Compare LLM models under one strategy and profile |
| [`run_plain_llm_baseline.py`](#run_plain_llm_baselinepy) | yes | Direct LLM baseline without symbolic pipeline |
| [`run_non_boolean_probe.py`](#run_non_boolean_probepy) | yes | Non-Boolean capability probe for manual review |
| [`convert_json_final_to_verus_lm.py`](#verus-lm-adapter) | yes | Convert the primary thesis benchmark to VERUS-LM input layout |
| [`run_verus_lm_evaluation.py`](#verus-lm-adapter) | yes | Execute VERUS-LM on the converted benchmark |
| [`validate_test_set.py`](#validate_test_setpy) | yes | Static benchmark validation without LLM or IDP-Z3 |
| [`diagnose_unsat.py`](#diagnose_unsatpy) | yes | Manual UNSAT debugging for one run folder |
| [`eval_support.py`](#internal-libraries) | no | Shared helpers for `run_evaluation.py` |
| [`eval_grouped_metrics.py`](#internal-libraries) | no | Group/domain metrics based on `manifest.json` |

## Thesis result artefacts

| Phase | Script | Committed thesis artefacts |
|-------|--------|----------------------------|
| Budget-profile selection | `run_config_ablation.py` | `results/final/config_selection_final/` |
| Strategy selection | `run_evaluation.py` | `results/final/strategy_selection_final/` |
| Model selection | `run_model_sweep.py` | `results/final/model_selection_final/` |
| Plain LLM baseline | `run_plain_llm_baseline.py` | `results/final/plain_llm_baseline/` |
| Non-Boolean probe | `run_non_boolean_probe.py` | `results/final/non_boolean_probe_test/` |
| VERUS-LM comparison | `convert_json_final_to_verus_lm.py` and `run_verus_lm_evaluation.py` | `inputs/verus_lm_from_json_final_clean/` and `results/final/verus_lm_test/` |

The committed folders under `results/final/` preserve the artefacts used for the thesis tables. The fresh-rerun commands below therefore use `results/reproduction/` output folders where appropriate.

The reported model comparison reused the Claude Sonnet 4.6 observation from `results/final/strategy_selection_final/`, because it was produced under the identical selected configuration and strategy. The updated `config/model_sweep_top3.txt` contains all three models so that a new user can execute a complete fresh rerun.

---

## `run_evaluation.py`

Main evaluation harness. It runs `main.py` for each `(run, strategy)` cell, scores the output when possible, and writes aggregate reports.

Outputs under `--output-dir`:

- `matrix.json` — complete cell results and LLM call summary.
- `report.md` — human-readable report.
- `summary.csv` — tabular report.
- `grouped_summary.json` — grouped metrics when a manifest is present.
- `work/<run>/<strategy>/` — per-cell artefacts such as `results.json`, `score.json` and the generated knowledge base.

### Fresh rerun of the selected JSON-IR setting

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

### Fresh rerun of all four strategies

```powershell
python scripts/run_evaluation.py `
  --config config/heavy.json `
  --ignore-local-config `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --strategies all `
  --output-dir results/reproduction/strategy_selection_rerun `
  --clean `
  --no-fail-on-missing-score
```

Notes:

- `--input-dir` is an alias for `--runs-dir`.
- Model and provider settings are read from `.env`, for example `LLM_PROVIDER` and `LLM_MODEL`.
- Use `--ignore-local-config` for reproducible thesis runs.
- The reported thesis strategy-selection artefacts remain in `results/final/strategy_selection_final/`.

---

## `run_config_ablation.py`

This script compares budget profiles without editing `config/local.json`. It automatically passes `--ignore-local-config`.

The script name retains the original technical name `run_config_ablation.py`; in the thesis text the three profiles are described as **beperkt**, **gebalanceerd** and **ruim**.

### Fresh rerun of the three budget profiles

```powershell
python scripts/run_config_ablation.py `
  --profiles config/cheap.json config/balanced.json config/heavy.json `
  --runs all `
  --runs-dir inputs/json_final_clean `
  --strategies direct_json_ir_no_translate `
  --output-root results/reproduction/config_selection_rerun
```

Each profile receives a subfolder named after the configuration stem:

```text
cheap/
balanced/
heavy/
```

The artefacts used in the thesis are preserved in:

```text
results/final/config_selection_final/
```

---

## `run_model_sweep.py`

This script runs `run_evaluation.py` once per model and aggregates the results into:

- `model_sweep_summary.json`
- `model_sweep_summary.csv`
- `model_sweep_report.md`

### Complete fresh rerun of all three selected models

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
  --output-root results/reproduction/model_selection_full_rerun
```

The file:

```text
config/model_sweep_top3.txt
```

contains:

```text
anthropic/claude-sonnet-4.6
openai/gpt-5.5
google/gemini-3.1-pro-preview
```

This allows a new user to rerun the complete three-model comparison.

For the results reported in the thesis, Claude Sonnet 4.6 was already available from the strategy-selection run under the same selected profile (`config/heavy.json`) and the same selected strategy (`direct_json_ir_no_translate`). The committed `results/final/model_selection_final/` folder therefore contains the newly executed remaining model cells, while the thesis comparison combines those results with the matching Claude observation from `results/final/strategy_selection_final/`.

Custom model lists can be created by copying:

```text
config/model_sweep_models.example.txt
```

One model id must be listed per line; lines beginning with `#` are ignored.

---

## `run_plain_llm_baseline.py`

Direct LLM baseline. The prompt contains law, case and question only, without JSON-IR knowledge-base compilation or IDP-Z3 execution. Answers must be:

```text
TRUE
FALSE
UNKNOWN
```

The script loads `.env` automatically, for example `OPENROUTER_API_KEY`.

### Fresh rerun

```powershell
python scripts/run_plain_llm_baseline.py `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --models "anthropic/claude-sonnet-4.6,openai/gpt-5.5,google/gemini-3.1-pro-preview" `
  --output-dir results/reproduction/plain_llm_baseline_rerun `
  --base-url "https://openrouter.ai/api/v1" `
  --temperature 0 `
  --max-tokens 32
```

The committed artefacts used in the thesis are stored in:

```text
results/final/plain_llm_baseline/
```

### Dry-run or task inspection

```powershell
python scripts/run_plain_llm_baseline.py `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --models "anthropic/claude-sonnet-4.6" `
  --output-dir results/reproduction/plain_llm_baseline_debug `
  --dry-run `
  --debug-dump-tasks 3
```

---

## `run_non_boolean_probe.py`

Runs the JSON-IR pipeline on:

```text
inputs/non_boolean_same_laws_testset/
```

This probe targets set, range and explanation intents. It converts probe JSON to temporary `run.json` folders, calls `main.py`, and writes summaries for manual review.

No automatic scoring is applied.

### Fresh rerun

```powershell
python scripts/run_non_boolean_probe.py `
  --input-dir inputs/non_boolean_same_laws_testset `
  --output-dir results/reproduction/non_boolean_probe_rerun `
  --model anthropic/claude-sonnet-4.6 `
  --strategy direct_json_ir_no_translate `
  --config config/heavy.json `
  --explain `
  --limit 3 `
  --clean
```

The committed artefacts used for the thesis discussion are stored in:

```text
results/final/non_boolean_probe_test/
```

---

## VERUS-LM adapter

External baseline comparison against the official VERUS-LM implementation:

```text
https://gitlab.com/EAVISE/bca/verus-lm
```

A separate VERUS-LM installation is required.

### 1. Convert the primary benchmark

```powershell
python scripts/convert_json_final_to_verus_lm.py `
  --input-dir inputs/json_final_clean `
  --output-dir inputs/verus_lm_from_json_final_clean
```

### 2. Execute a fresh VERUS-LM evaluation

```powershell
python scripts/run_verus_lm_evaluation.py `
  --input-dir inputs/verus_lm_from_json_final_clean `
  --output-dir results/reproduction/verus_lm_test_rerun
```

The committed VERUS-LM artefacts used in the thesis are stored in:

```text
results/final/verus_lm_test/
```

The conversion changes only the technical input layout. It does not change the law text, case text, question or expected answer.

---

## `validate_test_set.py`

Static benchmark validation. It checks the manifest, `run.json` structure and absence of stray generated artefacts. It does not call an LLM or IDP-Z3.

```powershell
python scripts/validate_test_set.py --input-dir inputs/json_final_clean
python scripts/validate_test_set.py --input-dir inputs/json_final_clean --strict
```

Run this command before large evaluations and after editing benchmark inputs or the manifest.

---

## `diagnose_unsat.py`

Manual debugging helper for a run where knowledge base and case become unsatisfiable.

```powershell
python scripts/diagnose_unsat.py inputs/json_final_clean/run_003
```

See also:

```text
pipeline/kb/semantic_check.py
```

---

## Internal libraries

Do not execute these directly:

| Module | Imported by |
|--------|-------------|
| `eval_support.py` | `run_evaluation.py`; failure classification and matrix helpers |
| `eval_grouped_metrics.py` | `run_evaluation.py`; grouped metrics from `manifest.json` |

---

## Single-run alternative

For one run and one question, use `main.py` directly:

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
