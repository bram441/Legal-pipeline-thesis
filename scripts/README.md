# Utility scripts

Run from the **project root**.

| Script | Purpose |
|--------|---------|
| `validate_test_set.py` | Static check of `inputs/json_final` (manifest, run.json shape, no generated artifacts). No LLM/IDP. |
| `run_evaluation.py` | Main evaluation: many JSON runs × strategies → `results/reports/evaluation_<timestamp>/` (`matrix.json`, `report.md`, `summary.csv`, `grouped_summary.json` when `manifest.json` is present). |
| `eval_support.py` | Shared helpers (imported by `run_evaluation.py`; not run directly). |
| `eval_grouped_metrics.py` | Tier/group metrics (imported by `run_evaluation.py` when evaluating `inputs/json_final`). |
| `diagnose_unsat.py` | Manual UNSAT debugging for a single run folder (KB + real case structure). |

### Typical thesis command

```powershell
python scripts/run_evaluation.py --runs-dir inputs/json_final --runs all --strategies direct_json_ir_no_translate
```

### Unit tests

```powershell
python -m pytest tests/
```
