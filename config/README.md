# Pipeline configuration

Versioned behaviour lives in:

```text
config/default.json
```

Optional machine-local overrides go in:

```text
config/local.json
```

`config/local.json` is gitignored and can be copied from `config/local.json.example`.

Secrets such as API keys remain in `.env` only.

Most pipeline options live in `default.json` or in an optional local override. Keep `.env` minimal and use `local.json` only for machine-specific development overrides such as tracing or temporary budget changes.

Environment variables listed in `pipeline/config.py` may still override configuration values when explicitly set.

## JSON-IR KB prompts

Knowledge-base symbol and rule generation always use the canonical files:

```text
prompts/kb/json_ir/generation/symbols.txt
prompts/kb/json_ir/generation/rules.txt
```

There is no `prompt_profile` configuration key.

## `json_ir.scope_mode`

`json_ir.scope_mode` controls how much supplied law text is passed to knowledge-base compilation before symbol and rule generation.

Implementation:

```text
pipeline/kb/law_scope.py
```

| Value | Behaviour |
|-------|-----------|
| `cited` | Prefer citation-based chunk selection when the question cites articles or paragraphs; otherwise use keyword retrieval or the full supplied law excerpt as fallback |
| `full` | Always use the entire supplied law excerpt |
| `retrieve` | Use keyword-based chunk retrieval from question and case text |

Possible environment-variable overrides:

```text
JSON_IR_SCOPE_MODE
PIPELINE_LAW_SCOPE_MODE
LAW_SCOPE_MODE
```

## Local overrides

Create a local override file only when needed:

```powershell
copy config\local.json.example config\local.json
```

Use partial overrides only; unspecified keys continue to fall back to `default.json`.

## Configuration merge order

Configuration is applied in this order:

```text
config/default.json
→ config/local.json, when present
→ --config profile, when supplied
→ environment variables
```

For reproducible thesis runs, pass the selected profile and disable local overrides:

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

Single-run equivalent:

```powershell
python main.py `
  --mode json `
  --run inputs/json_final_clean/run_001 `
  --config config/heavy.json `
  --ignore-local-config `
  --kb-strategy direct_json_ir_no_translate `
  --no-translate
```

When `--config` is omitted, `run_evaluation.py` uses the default configuration plus optional local overrides. `main.py` without `--config` may also respect `PIPELINE_CONFIG_PROFILE` when exported.

`--ignore-local-config` skips `config/local.json`, so only the repository baseline, selected profile and explicit environment overrides apply.

## Thesis LLM budget profiles

The three thesis budget profiles are partial overlays on top of `default.json`. They modify JSON-IR compilation budgets, extraction retry budgets and related debugging behaviour; they do not redefine prompts or scoring semantics.

| Technical file | Thesis description | Purpose |
|----------------|-------------------|---------|
| `config/cheap.json` | beperkte configuratie | Low LLM budget for quick evaluation and comparison |
| `config/balanced.json` | gebalanceerde configuratie | Middle budget-comparison profile |
| `config/heavy.json` | ruime configuratie | Higher LLM budget selected for the final thesis pipeline |

The committed thesis artefacts under:

```text
results/final/
```

preserve the runs reported in the thesis. New reproduction runs should use output folders under:

```text
results/reproduction/
```

so that the original artefacts remain unchanged.

### Fresh budget-profile comparison

```powershell
python scripts/run_config_ablation.py `
  --profiles config/cheap.json config/balanced.json config/heavy.json `
  --runs all `
  --runs-dir inputs/json_final_clean `
  --strategies direct_json_ir_no_translate `
  --output-root results/reproduction/config_selection_rerun
```

The committed profile-selection artefacts used in the thesis are stored in:

```text
results/final/config_selection_final/
```

## Model-comparison file

The file:

```text
config/model_sweep_top3.txt
```

contains all three models required for a complete fresh rerun of the selected-model comparison:

```text
anthropic/claude-sonnet-4.6
openai/gpt-5.5
google/gemini-3.1-pro-preview
```

In the reported thesis results, the Claude observation was reused from strategy selection because it had already been evaluated under the identical selected configuration and strategy. Including all three models in the current configuration file makes the repository easier to reproduce from scratch.

Custom model lists can be based on:

```text
config/model_sweep_models.example.txt
```

## Other files in this folder

| File | Purpose |
|------|---------|
| `config/default.json` | Required repository baseline, always loaded first |
| `config/local.json.example` | Template for optional gitignored local overrides |
| `config/cheap.json` | Restricted LLM budget profile |
| `config/balanced.json` | Balanced LLM budget profile |
| `config/heavy.json` | Selected final thesis budget profile |
| `config/model_sweep_top3.txt` | Complete three-model list for a fresh final model-comparison rerun |
| `config/model_sweep_models.example.txt` | Example custom model-list template |

## Evaluation keys

Relevant keys in the `evaluation` section include:

| Key | Default | Meaning |
|-----|---------|---------|
| `belief_scoring` | `false` | When enabled, open-world answers may be scored using a belief threshold |
| `boolean_belief_threshold` | `0.5` | Threshold used only when belief scoring is enabled |
| `run_pre_query_satisfiability_check` | `true` | Run a satisfiability check before evaluating the query |
| `pragmatic_factual_criteria_mode` | `false` | Allow factual criteria as case inputs in the relevant comparison mode |
| `model_expansion_max_models` | `3` | Cap for model-expansion diagnostics; not Boolean entailment scoring |

Example partial overlay increasing the KB compilation LLM budget:

```json
{
  "json_ir": {
    "max_kb_llm_calls": 12
  }
}
```

## `.env`

Common variables:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | API secret for OpenAI-direct execution |
| `OPENAI_MODEL` | Optional default OpenAI model |
| `OPENAI_EXPLAINER_MODEL` | Optional model used for natural-language paraphrase only |
| `LLM_PROVIDER` | `openai` or `openrouter` |
| `LLM_API_KEY` | Provider-neutral API-key override |
| `LLM_MODEL` | Provider-neutral model override |
| `LLM_BASE_URL` | Custom API base URL |
| `OPENROUTER_API_KEY` | OpenRouter API secret |
| `OPENROUTER_MODEL` | OpenRouter model id, for example `anthropic/claude-sonnet-4.6` |
| `OPENROUTER_BASE_URL` | Usually `https://openrouter.ai/api/v1` |
| `OPENROUTER_HTTP_REFERER` | Optional OpenRouter header |
| `OPENROUTER_APP_TITLE` | Optional OpenRouter header |
| `PIPELINE_USE_LLM_EXPLANATIONS` | Enable optional natural-language explanation rendering |
| `PIPELINE_DEBUG` | Enable additional console debugging |

## `llm` section in `default.json`

| Key | Purpose |
|-----|---------|
| `provider` | `openai` or `openrouter`, overridable through environment variables |
| `model` | Default model when no environment override is supplied |
| `base_url` | API base URL |
| `use_seed` | Pass a seed to compatible chat-completion calls |
| `use_response_format` | Pass structured-response settings when supported |
| `use_reasoning_effort` | Pass a reasoning-effort setting when supported |
| `timeout_seconds` | Client timeout |

Everything else, including JSON-IR repair limits, scope mode, extraction backend, trace behaviour, Logical English flags and scoring options, belongs in `default.json` or an explicit local/profile override.

## Run artefacts

Each JSON benchmark run writes:

```text
effective_config.json
```

This file contains the merged configuration and an `llm_runtime` block with provider, model and host information only. API keys are never written to the artefact.
