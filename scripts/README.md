# Utility scripts

Run from the **project root**.

| Script | Purpose |
|--------|---------|
| `validate_test_set.py` | Static check of `inputs/json_final` (manifest, run.json shape, no generated artifacts). No LLM/IDP. |
| `run_evaluation.py` | Main evaluation: many JSON runs × strategies → `results/reports/evaluation_<timestamp>/` (`matrix.json`, `report.md`, `summary.csv`, `grouped_summary.json` when `manifest.json` is present). |
| `eval_support.py` | Shared helpers (imported by `run_evaluation.py`; not run directly). |
| `eval_grouped_metrics.py` | Tier/group metrics (imported by `run_evaluation.py` when evaluating `inputs/json_final`). |
| `diagnose_unsat.py` | Manual UNSAT debugging for a single run folder (KB + real case structure). |
| `run_model_sweep.py` | Run `run_evaluation.py` once per model; aggregate `model_sweep_summary.*` under `--output-root`. |

### Typical thesis command

```powershell
python scripts/run_evaluation.py --runs-dir inputs/json_final --runs all --strategies direct_json_ir_no_translate
# (--input-dir is an alias for --runs-dir)
```

Optional config profile (merged on top of `config/default.json` + `config/local.json`):

```powershell
python scripts/run_evaluation.py --config config/final.json --runs-dir inputs/json_final --runs run_001 --strategies direct_json_ir_no_translate

# Reproducible profile without local.json overrides:
python scripts/run_evaluation.py --config config/ablation_balanced.json --ignore-local-config --runs-dir inputs/json_final --runs run_001 --strategies direct_json_ir_no_translate
```

### Model sweep (OpenRouter or OpenAI)

Use a **small focused subset** before full thesis runs. Compare models only with the same strategy, config profile, and test set.

```powershell
$env:LLM_PROVIDER="openrouter"
$env:OPENROUTER_API_KEY="..."

python scripts/run_model_sweep.py `
  --provider openrouter `
  --models-file config/model_sweep_models.txt `
  --input-dir inputs/json_final_clean `
  --strategies direct_json_ir_no_translate le_json_ir_no_translate `
  --config config/ablation_balanced.json `
  --ignore-local-config `
  --clean `
  --no-fail-on-missing-score `
  --output-root results/reports/model_sweep_clean_law
```

OpenAI direct (single model via env):

```powershell
$env:LLM_PROVIDER="openai"
$env:OPENAI_API_KEY="..."
$env:LLM_MODEL="gpt-5.4-mini"
python scripts/run_evaluation.py --input-dir inputs/json_final_clean --runs run_001 --strategies direct_json_ir_no_translate
```

**Models list:** copy `config/model_sweep_models.example.txt` to `config/model_sweep_models.txt` (one model id per line, `#` comments allowed). Pass `--models-file config/model_sweep_models.txt`, or add extra ids with `--models openai/gpt-5.5`. JSON is also supported: `["openai/gpt-5.5", ...]` or `{"models": [...]}`.

Outputs: `results/reports/model_sweep_<name>/<model>_<timestamp>/` (normal eval artifacts) plus `model_sweep_summary.json`, `.csv`, `model_sweep_report.md` at the sweep root.

Optional budgets: `--max-llm-calls-per-model N` (passed to each eval), `--max-total-cost` (best-effort stop after summed estimates).

### Unit tests

```powershell
python -m pytest tests/
```
