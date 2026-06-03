# Project guide

Quick map for developers and thesis reproducibility. Stack: **JSON-IR KB compilation + schema-driven extraction + IDP-Z3**.

## 1. First run checklist

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env          # add API key + LLM_MODEL

python scripts/validate_test_set.py --input-dir inputs/json_final_clean

python main.py `
  --mode json `
  --run inputs/json_final_clean/run_001 `
  --config config/heavy.json `
  --ignore-local-config `
  --kb-strategy direct_json_ir_no_translate `
  --no-translate
```

## 2. KB strategies

| Strategy | Translation | Logical English intermediate |
|----------|:-----------:|:----------------------------:|
| `direct_json_ir_no_translate` | no | no |
| `direct_json_ir_translate` | yes | no |
| `le_json_ir_no_translate` | no | yes |
| `le_json_ir_translate` | yes | yes |

`LE` refers to the optional **Logical English** preprocessing layer before JSON-IR generation.

Canonical strategy list:

```text
pipeline/kb/compile_strategy.py → STRATEGY_CHOICES
```

## 3. End-to-end flow

Entrypoint:

```text
main.py → pipeline/app/pipeline.py::answer_legal_prompt(...)
```

Processing steps:

1. **Effective configuration** — `default.json` + optional `local.json` + `--config` + `.env`.
2. **Law scoping** — `json_ir.scope_mode` selects cited, retrieved or full supplied law text.
3. **Optional translation** — Dutch to English via `pipeline/translation/`.
4. **Optional Logical English** — only for `le_json_ir_*` strategies via `pipeline/le/`.
5. **JSON-IR KB compilation** — symbol generation, rule generation, validation and repair.
6. **Deterministic FO(.) rendering** — valid JSON-IR is rendered into an executable knowledge base.
7. **Schema environment** — allowed symbols, factual inputs and query targets are exposed.
8. **Case extraction** — case text becomes validated formal facts.
9. **Query extraction** — the question is mapped to a valid legal-output target or supported intent.
10. **Pre-query satisfiability check** — KB and case are checked before answer generation.
11. **Pre-solver validation** — entity types, signatures and domain seeding are checked.
12. **Symbolic execution** — the selected intent is executed in IDP-Z3.
13. **Rendering and scoring** — answers, diagnostics and decisive Boolean scores are written.

## 4. Configuration

| Layer | File or flag |
|-------|--------------|
| Secrets | `.env` — `OPENROUTER_API_KEY` or `OPENAI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL` |
| Baseline | `config/default.json` |
| Selected thesis profile | `config/heavy.json` |
| Local development | `config/local.json`, gitignored and copied from `local.json.example` |
| Reproducible runs | `--config config/heavy.json --ignore-local-config` |

Budget profiles for comparison:

| Technical file | Thesis description |
|----------------|-------------------|
| `config/cheap.json` | beperkte configuratie |
| `config/balanced.json` | gebalanceerde configuratie |
| `config/heavy.json` | ruime configuratie; selected final thesis profile |

Details are documented in **`config/README.md`**.

## 5. Benchmark inputs

| Folder | Use |
|--------|-----|
| `inputs/json_final_clean/` | **Primary benchmark** — 37 runs using `example_laws_clean/` paths |
| `inputs/json_final/` | Equivalent raw-law-path variant, retained for optional comparison |
| `inputs/non_boolean_same_laws_testset/` | Non-Boolean capability probe |
| `inputs/verus_lm_from_json_final_clean/` | Converted input layout for the VERUS-LM comparison |

Primary benchmark manifest:

```text
inputs/json_final_clean/manifest.json
```

The primary benchmark contains Boolean gold labels (`TRUE` / `FALSE`). The symbolic pipeline may additionally output `UNKNOWN` when neither the queried conclusion nor its explicit negation is entailed.

## 6. Evaluation scripts

| Goal | Entrypoint |
|------|------------|
| Single run | `main.py --mode json --run ...` |
| Matrix evaluation | `scripts/run_evaluation.py` |
| Budget-profile comparison | `scripts/run_config_ablation.py` |
| Model comparison | `scripts/run_model_sweep.py` |
| Plain LLM baseline | `scripts/run_plain_llm_baseline.py` |
| Non-Boolean probe | `scripts/run_non_boolean_probe.py` |
| VERUS-LM conversion | `scripts/convert_json_final_to_verus_lm.py` |
| VERUS-LM evaluation | `scripts/run_verus_lm_evaluation.py` |
| Test-set validation | `scripts/validate_test_set.py` |

Full command reference:

```text
scripts/README.md
```

Default primary benchmark directory:

```text
inputs/json_final_clean/
```

## 7. Prompts

| Area | Path |
|------|------|
| KB symbol and rule generation | `prompts/kb/json_ir/generation/` |
| KB repair | `prompts/kb/json_ir/repair/` |
| Case and query extraction | `prompts/extraction/json_ir/` |
| Logical English layer | `prompts/le/generation/law_to_le.txt` |
| Translation | `prompts/translation/translate_to_english.txt` |
| Optional natural-language rendering | `prompts/nl/` |

Registry:

```text
pipeline/utils/prompt_paths.py
```

Loader:

```text
pipeline/utils/prompt_loader.py
```

## 8. Key artefacts per run

Written under the run working directory or evaluation cell folder:

- `effective_config.json` — merged configuration without API keys.
- `results.json` — normalized output.
- `score.json` — evaluation outcome when scoring is available.
- `kb.fo` — rendered FO(.) knowledge base.
- `kb_schema.json` / `schema_environment.json` — symbol and extraction constraints.
- `symbolic_proof_gap.json` — missing-support diagnostics when generated.
- `llm_call_summary.json` — call and token tracking when enabled.

## 9. Reported result artefacts and fresh reruns

The committed folders under:

```text
results/final/
```

contain the artefacts used for the reported thesis evaluation. Fresh reruns can use a separate output root, while the committed thesis artefacts remain available under `results/final/`, for example:

```text
results/reproduction/
```

The reported thesis model comparison uses three models:

- `anthropic/claude-sonnet-4.6`
- `openai/gpt-5.5`
- `google/gemini-3.1-pro-preview`

In the reported artefacts, Claude Sonnet 4.6 was reused from the strategy-selection run because it had already been evaluated under the identical selected configuration and strategy. The file:

```text
config/model_sweep_top3.txt
```

now contains all three models so that a new user can execute a complete fresh model-comparison rerun.

## 10. Tests

Thesis-critical smoke tests:

```powershell
python -m pytest tests/test_json_ir_prompts.py tests/test_negative_legal_output_rule_safety.py tests/test_query_target_selection.py -q
```

Test overview:

```text
tests/README.md
```
