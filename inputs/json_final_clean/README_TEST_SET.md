# Final thesis evaluation test set (`inputs/json_final_clean`)

This folder is the **clean, tiered** benchmark input for thesis evaluation. Law texts use **`example_laws_clean/`** paths. It contains only curated inputs:

- `manifest.json` — run metadata (group, difficulty, domain, phenomena, optional `family`)
- `run_XXX/run.json` — law path, case text, questions with expected answers and `expected.reason`
- `README_TEST_SET.md` — this file

The pipeline writes all generated artifacts under `results/` during evaluation. **Do not** store `results.json`, `kb.fo`, `score.json`, or similar files here.

## Tiered groups

| Group | Purpose |
|-------|---------|
| **core** | Basic functioning: definitions, direct legal effects, simple thresholds |
| **challenge** | Richer reasoning: multi-criterion cases, procedural rules, structural exclusions |
| **stress** | Intentionally difficult: temporal rules, first-year estimates, helper closure, hard thresholds |
| **external_verus_lm** | Reserved for future VERUS-LM comparison (empty for now) |

Report results **per group** (and per difficulty / domain / phenomenon), not only as one aggregate score.

## Design choices

- **Hard runs were not removed.** Stress-tier cases (e.g. temporal company law, immigration edge cases) remain; they were relabeled so the thesis can show where the pipeline struggles.
- **New core runs (`run_201`–`run_208`)** are explicit sanity checks added for the thesis. They demonstrate basic pipeline behaviour; they are **not** hidden replacements for hard benchmarks.
- **Legacy duplicate runs** (e.g. `run_001` / `run_101`) stay documented via `related_runs` in the manifest for transparency.

## Validate before evaluating

Static check (no LLM, no IDP):

```bash
python scripts/validate_test_set.py --input-dir inputs/json_final_clean
```

Use `--strict` to fail on warnings, or `--json-output path/to/validation_summary.json` for a machine-readable summary.

## Run evaluation

```bash
python scripts/run_evaluation.py `
  --config config/heavy.json `
  --ignore-local-config `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --strategies direct_json_ir_no_translate
```

Grouped metrics: `results/reports/evaluation_*/grouped_summary.json` when `manifest.json` is present.

## Maintenance

Edit `run.json` and `manifest.json` directly. After changes, re-run `validate_test_set.py`. Keep counts in `manifest.json` (`counts_by_*`) aligned with the `runs` list.
