# Utility scripts

Run from the **project root** unless noted.

| Script | Purpose |
|--------|---------|
| `run_evaluation.py` | Run **many** JSON runs × strategies; writes `results/reports/evaluation_<timestamp>/` with `matrix.json`, `report.md`, `summary.csv`, per-cell work under `work/`. Use `--runs all` or `run_001,run_003`, `--strategies all` or a subset, `--excel` for `summary.xlsx` (needs `pip install openpyxl`). Benchmarks: `inputs/json/run_001` … `run_009` (law text via `law.path` → `example_laws/`). Accuracy is empty when questions have no `expected` (smoke / exploratory runs). |
| `compare_kb_strategies.py` | Thin wrapper: one run, all four strategies; writes `kb_strategy_compare/` + `compare_summary.json`. Prefer `run_evaluation.py` for full sweeps. |
| `diagnose_unsat.py` | **Manual debugging:** compose KB + case from a run folder, print SAT and, if UNSAT, an explanation via `pipeline.kb.semantic_check.explain_unsat_fo` (same Theory.explain path as the KB semantic check). **Not invoked by the pipeline automatically.** |
| `tests/run_suite.py` | Regression over `tests/suites/baseline_v1`: each case uses `law.txt` (copy of `example_laws/*`) and **KB compilation** via `get_or_compile_kb`. Run with `--allow-compile-kb` (and optional `--kb-model`). Expectations use `smoke: true` (pass = no pipeline error + structured prediction). |

### UNSAT: pipeline vs diagnose_unsat

- **During KB compilation:** `pipeline/kb/semantic_check.py` runs `check_kb_semantic` on **KB + minimal dummy structure**. If UNSAT, it uses the same `explain_unsat_fo` logic (internal `_get_unsat_explanation`) to enrich repair prompts.
- **After a run:** use `diagnose_unsat.py` to debug **KB + real case structure** when answers say “theory is unsatisfiable” (reasoning-time UNSAT).
