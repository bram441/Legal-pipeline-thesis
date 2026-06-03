# Final thesis evaluation test set (`inputs/json_final_clean`)

This folder is the **clean, tiered primary benchmark** used for the thesis evaluation. Law texts use paths under:

```text
example_laws_clean/
```

The folder contains curated benchmark inputs only:

- `manifest.json` — run metadata, including group, difficulty, domain, phenomena and optional family information.
- `run_XXX/run.json` — law path, case text, questions, expected Boolean answers and `expected.reason`.
- `README_TEST_SET.md` — this documentation file.

The primary benchmark contains 37 runs from three legal domains:

| Domain | Runs |
|--------|-----:|
| Inheritance law | 12 |
| Immigration law | 11 |
| Company law | 14 |
| **Total** | **37** |

The gold labels are Boolean (`TRUE` / `FALSE`). The symbolic pipeline may additionally output `UNKNOWN` when neither the queried conclusion nor its explicit negation is entailed; `UNKNOWN` is not a gold-label category in this primary benchmark.

Generated evaluation artefacts, such as `results.json`, `kb.fo` and `score.json`, are written to separate evaluation output directories and are not part of this benchmark input folder.

## Tiered groups

| Group | Purpose |
|-------|---------|
| **core** | Basic functioning: definitions, direct legal effects and simple thresholds |
| **challenge** | Richer reasoning: multi-criterion cases, procedural rules and structural exclusions |
| **stress** | Intentionally difficult cases: temporal rules, first-year estimates, helper closure and hard thresholds |
| **external_verus_lm** | Reserved metadata category; the completed VERUS-LM comparison uses `inputs/verus_lm_from_json_final_clean/` and `results/final/verus_lm_test/`, rather than additional primary-benchmark runs |

Results should be reportable per group, difficulty, domain and phenomenon, rather than only as one aggregate score.

## Design choices

- **Hard runs were not removed.** Stress-tier cases remain in the benchmark so the thesis can show where the pipeline struggles.
- **New core runs (`run_201`–`run_208`)** are explicit sanity checks added for the thesis. They demonstrate basic pipeline behaviour; they are not hidden replacements for difficult benchmark cases.
- **Legacy duplicate runs**, such as `run_001` and `run_101`, remain documented through `related_runs` metadata for transparency.
- **Cleaned law excerpts** remove editorial noise and historical markup while preserving the normative content used for the evaluated questions.

## Validate before evaluating

Static validation, without LLM calls or IDP-Z3 execution:

```powershell
python scripts/validate_test_set.py --input-dir inputs/json_final_clean
```

To fail on warnings:

```powershell
python scripts/validate_test_set.py --input-dir inputs/json_final_clean --strict
```

To write a machine-readable validation summary:

```powershell
python scripts/validate_test_set.py `
  --input-dir inputs/json_final_clean `
  --json-output results/reproduction/testset_validation.json
```

## Run the selected JSON-IR setting

Use a separate reproduction output folder so that the committed thesis artefacts remain unchanged:

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

When `manifest.json` is present, grouped metrics are written to:

```text
grouped_summary.json
```

under the chosen evaluation output directory.

The committed artefacts used for the thesis tables are retained under:

```text
results/final/
```

## VERUS-LM comparison

The VERUS-LM comparison does not add extra runs to the primary benchmark. Instead, the same benchmark content is converted into the technical layout required by VERUS-LM:

```text
inputs/verus_lm_from_json_final_clean/
```

The committed comparison results are stored in:

```text
results/final/verus_lm_test/
```