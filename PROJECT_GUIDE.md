# Project guide

Quick map for developers and thesis reproducibility. Stack: **JSON-IR KB compile + schema-driven extraction + IDP-Z3**.

## 1. First run checklist

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # add API key + LLM_MODEL
python scripts/validate_test_set.py --input-dir inputs/json_final_clean
python main.py --mode json --run inputs/json_final_clean/run_001 `
  --config config/heavy.json --ignore-local-config `
  --kb-strategy direct_json_ir_no_translate --no-translate
```

## 2. KB strategies

| Strategy | Translation | LE intermediate |
|----------|:-----------:|:---------------:|
| `direct_json_ir_no_translate` | no | no |
| `direct_json_ir_translate` | yes | no |
| `le_json_ir_no_translate` | no | yes |
| `le_json_ir_translate` | yes | yes |

Canonical list: `pipeline/kb/compile_strategy.py` → `STRATEGY_CHOICES`.

## 3. End-to-end flow

`main.py` → `pipeline/app/pipeline.py::answer_legal_prompt(...)`

1. **Effective config** — `default.json` + optional `local.json` + `--config` + `.env`
2. **Law scoping** — `json_ir.scope_mode` (`cited` / `full` / `retrieve`)
3. **Optional translation** — NL → EN (`pipeline/translation/`)
4. **Optional Legal English** — `le_json_ir_*` only (`pipeline/le/`)
5. **JSON-IR KB compile** — symbols LLM → rules LLM → validation/repair (`json_ir_compile_loop.py`)
6. **Schema environment** — assertable symbols, factual inputs, query targets
7. **Case extraction** — JSON-IR → validated facts (`extraction/json_ir.py`)
8. **Query extraction** — target selection for legal-output predicates (`query_target_selection.py`)
9. **Pre-query SAT check** — intent routing + consistency (`semantic/`, `symbolic/`)
10. **Pre-solver validation** — entity types, domain seeding (`validation/`)
11. **Symbolic execution** — intent → IDP-Z3 (`symbolic/router.py`, `idp_z3/`)
12. **Render + score** — answer text, diagnostics, decisive Boolean scoring

## 4. Configuration

| Layer | File / flag |
|-------|-------------|
| Secrets | `.env` — `OPENROUTER_API_KEY` or `OPENAI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL` |
| Baseline | `config/default.json` |
| Thesis overlay | `config/heavy.json` (final LLM budgets) |
| Local dev | `config/local.json` (gitignored; copy from `local.json.example`) |
| Reproducible runs | `--config config/heavy.json --ignore-local-config` |

Budget profiles for ablation: `cheap.json`, `balanced.json`, `heavy.json`. Details: **`config/README.md`**.

## 5. Benchmark inputs

| Folder | Use |
|--------|-----|
| `inputs/json_final_clean/` | **Primary** — 37 tiered runs, `example_laws_clean/` paths |
| `inputs/json_final/` | Same run ids, raw `example_laws/` paths (optional) |
| `inputs/non_boolean_same_laws_testset/` | Non-boolean intent probe |
| `inputs/verus_lm_from_json_final_clean/` | Pre-converted VERUS-LM layout |

Manifest + tier labels: `inputs/json_final_clean/manifest.json`.

## 6. Evaluation scripts

| Goal | Command entrypoint |
|------|-------------------|
| Single run | `main.py --mode json --run ...` |
| Matrix eval | `scripts/run_evaluation.py` |
| Config compare | `scripts/run_config_ablation.py` |
| Model compare | `scripts/run_model_sweep.py` |
| Plain LLM baseline | `scripts/run_plain_llm_baseline.py` |
| Non-boolean probe | `scripts/run_non_boolean_probe.py` |

Full command reference: **`scripts/README.md`**.

Default benchmark directory in scripts: **`inputs/json_final_clean`**.

## 7. Prompts

| Area | Path |
|------|------|
| KB symbols + rules | `prompts/kb/json_ir/generation/` |
| KB repair | `prompts/kb/json_ir/repair/` |
| Case / query extraction | `prompts/extraction/json_ir/` |
| LE layer | `prompts/le/generation/law_to_le.txt` |
| NL paraphrase | `prompts/nl/` |

Registry: `pipeline/utils/prompt_paths.py`. Loader: `pipeline/utils/prompt_loader.py`.

## 8. Key artifacts per run

Written next to the run working directory:

- `effective_config.json` — merged config (no secrets)
- `results.json`, `score.json` — answer + evaluation
- `kb.fo`, `kb_schema.json` — compiled KB
- `schema_environment.json`, `symbolic_proof_gap.json` — diagnostics
- `llm_call_summary.json` — token/cost tracking when enabled

## 9. Deprecated / removed

See **`docs/DEPRECATED_COMPONENTS.md`** (`rule_plan`, `prompt_profile`, `inputs/json/`, legacy FO compile, old strategy names).

## 10. Tests

Thesis-critical smoke:

```powershell
python -m pytest tests/test_json_ir_prompts.py tests/test_negative_legal_output_rule_safety.py tests/test_query_target_selection.py -q
```

Overview: **`tests/README.md`**.
