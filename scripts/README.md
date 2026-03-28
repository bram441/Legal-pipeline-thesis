# Utility scripts

Run from the **project root** unless noted.

| Script | Purpose |
|--------|---------|
| `compare_kb_strategies.py` | Run the same JSON benchmark four times (`direct_single`, `direct_two_phase`, `le_single`, `le_two_phase`); writes `kb_strategy_compare/` + `compare_summary.json`. See main README. |
| `diagnose_unsat.py` | **Manual debugging:** compose KB + case from a run folder, print SAT and, if UNSAT, an explanation via `pipeline.kb.semantic_check.explain_unsat_fo` (same Theory.explain path as the KB semantic check). **Not invoked by the pipeline automatically.** |

### UNSAT: pipeline vs diagnose_unsat

- **During KB compilation:** `pipeline/kb/semantic_check.py` runs `check_kb_semantic` on **KB + minimal dummy structure**. If UNSAT, it uses the same `explain_unsat_fo` logic (internal `_get_unsat_explanation`) to enrich repair prompts.
- **After a run:** use `diagnose_unsat.py` to debug **KB + real case structure** when answers say “theory is unsatisfiable” (reasoning-time UNSAT).
