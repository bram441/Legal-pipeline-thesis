# Tests

Run from the **project root**:

```powershell
python -m pytest tests/ -q
```

Quick smoke (scripts + config + core JSON-IR guards):

```powershell
python -m pytest tests/test_json_ir_prompts.py tests/test_json_ir_status_classification.py tests/test_json_ir_prerequisite_classification.py tests/test_negative_legal_output_rule_safety.py tests/test_query_target_selection.py tests/test_ignore_local_config.py tests/test_run_model_sweep.py tests/test_validate_test_set.py tests/test_eval_support.py -q
```

## Layout

| Area | Files | What they cover |
|------|-------|-----------------|
| **JSON-IR compile & validation** | `test_json_ir_*.py`, `test_kb_json_ir.py`, `test_kb_cache_json_ir.py` | Symbol/rules IR, compile loop, repair, cache, negated THEN, status/classification, prerequisites |
| **Extraction & query** | `test_extraction_json_ir.py`, `test_extractor_query_coerce.py`, `test_query_*.py` | Case/query IR normalization, target selection, role resolution, period binding |
| **Symbolic / intent** | `test_intent_*.py`, `test_get_range_intent.py`, `test_model_expansion_intent.py`, `test_predicate_solver.py` | Intent routing, scoring modes, IDP task shapes |
| **KB helpers & repair** | `test_repair_hints.py`, `test_*_repair*.py`, `test_legal_effect_*.py`, `test_threshold_*.py`, `test_composite_*.py` | Targeted repair cards, thresholds, legal effects, temporal support |
| **Case & FO validation** | `test_case_*.py`, `test_fo_*.py`, `test_factual_case_input.py`, `test_schema_environment.py` | Case facts, domain seeding, pre-solver validation |
| **Evaluation & scripts** | `test_eval_*.py`, `test_run_model_sweep.py`, `test_ignore_local_config.py`, `test_validate_test_set.py` | Scoring, failure categories, config merge, model sweep CLI |
| **Config & LLM** | `test_config.py`, `test_llm_*.py`, `test_prompt_paths.py` | Effective config, LLM client, prompt registry |
| **Law scope & compile strategy** | `test_law_scope_*.py`, `test_compile_strategy.py`, `test_kb_compile_backend.py` | Scope modes, KB strategy flags |
| **Misc pipeline** | `test_semantic_*.py`, `test_symbolic_proof_gap.py`, `test_import_isolation.py`, … | Semantic check, diagnostics, import boundaries |

## Thesis-critical tests

These guard behavior you rely on in final evaluation:

- `test_json_ir_prompts.py` — canonical prompts, no `rule_plan`
- `test_json_ir_status_classification.py` — directly observable status facts
- `test_json_ir_prerequisite_classification.py` — prerequisite closure repair
- `test_negative_legal_output_rule_safety.py` — unsafe inverse negative legal-output guard
- `test_query_target_selection.py` — query target prefers classification over effect
- `test_json_ir_negated_derived_then.py` — negated derived THEN rendering

## Internal / support modules

Not run directly; covered indirectly:

- `conftest.py` — skips `@pytest.mark.requires_idp` when `idp_engine` is missing

## Notes

- Many tests use **unittest** classes; pytest collects them fine.
- Tests marked `requires_idp` need IDP installed; they skip automatically otherwise.
- Some older tests target legacy FO compile paths or strict validation rules that may drift as JSON-IR hardening evolves. A failing count ≠ broken production path; check whether the failure is in code you still ship.

## Current health (last check)

- **~94 test modules**, **500+ tests** collected
- **1 collection error fixed:** `test_repair_hints.py` (removed import of deleted `_kb_repair_prompt_path`)
- **Duplicate removed:** `rule_plan` presence checks consolidated in `test_json_ir_prompts.py`

If the full suite shows failures, run with details on one file:

```powershell
python -m pytest tests/test_kb_json_ir.py -vv --tb=short
```
