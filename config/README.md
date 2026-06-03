# Pipeline configuration

Versioned behavior lives in **`default.json`**. Optional machine-local overrides go in **`local.json`** (gitignored — copy from `local.json.example`).

Secrets (`OPENAI_API_KEY`, model names) stay in **`.env`** only.

Most pipeline knobs live in **`default.json`** or **`local.json`**. Keep `.env` minimal; use `local.json` for machine-specific overrides (e.g. `debug.trace`, `json_ir.max_kb_llm_calls`).

Environment variables listed in `pipeline/config.py` still override config when set (optional escape hatch).

## JSON-IR KB prompts

KB symbol and rule generation always use the canonical files under `prompts/kb/json_ir/generation/` (`symbols.txt`, `rules.txt`). There is no `prompt_profile` config key.

## `json_ir.scope_mode`

Controls how much law text is passed to KB compilation before symbol/rules generation (`pipeline/kb/law_scope.py`).

| Value | Behavior |
|-------|----------|
| **`cited`** (default) | Prefer citation-based chunk selection when the question cites articles/paragraphs; otherwise keyword retrieval or full law fallback |
| **`full`** | Always use the entire law text |
| **`retrieve`** | Keyword-based chunk retrieval from question + case text |

Override via config, `config/local.json`, or env: `JSON_IR_SCOPE_MODE`, `PIPELINE_LAW_SCOPE_MODE`, or `LAW_SCOPE_MODE`.

## Local overrides

Copy the example file:

```bash
cp config/local.json.example config/local.json
```

Edit `local.json` with partial overrides only; unspecified keys fall back to `default.json`.

### Config profiles (CLI overlay)

Merge order: **`default.json`** → **`local.json`** (if present) → **profile** (optional) → **environment variables**.

For reproducible thesis runs, pass a profile and skip local overrides:

```powershell
python scripts/run_evaluation.py `
  --config config/heavy.json `
  --ignore-local-config `
  --runs-dir inputs/json_final_clean `
  --runs all `
  --strategies direct_json_ir_no_translate

python main.py `
  --mode json `
  --run inputs/json_final_clean/run_001 `
  --config config/heavy.json `
  --ignore-local-config `
  --kb-strategy direct_json_ir_no_translate `
  --no-translate
```

When `--config` is omitted, `run_evaluation.py` uses **default + local only**. `main.py` without `--config` still respects `PIPELINE_CONFIG_PROFILE` if you export it.

**`--ignore-local-config`** skips `config/local.json` so only **default → profile → env** apply. `run_config_ablation.py` passes this automatically.

### Thesis LLM budget profiles

These files are **partial overlays** on top of `default.json`. They only tune JSON-IR compile budgets, extraction retries, and debug flags — not prompts or scoring semantics.

| File | Purpose |
|------|---------|
| `config/cheap.json` | Low LLM budget — smoke tests and quick debugging |
| `config/balanced.json` | Medium LLM budget — config ablation middle tier |
| `config/heavy.json` | Higher LLM budget — selected final thesis profile |

Compare all three without editing `local.json`:

```powershell
python scripts/run_config_ablation.py `
  --profiles config/cheap.json config/balanced.json config/heavy.json `
  --runs all `
  --runs-dir inputs/json_final_clean `
  --strategies direct_json_ir_no_translate `
  --output-root results/final/config_selection
```

### Other files in this folder

| File | Purpose |
|------|---------|
| `config/default.json` | Required repo baseline (always loaded first) |
| `config/local.json.example` | Template for optional gitignored `local.json` |
| `config/model_sweep_top3.txt` | Short model list for thesis model selection |
| `config/model_sweep_models.example.txt` | Example model list — copy and edit for custom sweeps |

### Evaluation keys (`evaluation` section)

| Key | Default | Meaning |
|-----|---------|---------|
| `belief_scoring` | `false` | When true, open-world may score via belief threshold |
| `boolean_belief_threshold` | `0.5` | Threshold when belief scoring enabled |
| `run_pre_query_satisfiability_check` | `true` | SAT check before query |
| `pragmatic_factual_criteria_mode` | `false` | Allow factual criteria as case inputs (thesis comparison) |
| `model_expansion_max_models` | `3` | Cap for model-expansion diagnostics (not Boolean entailment) |

Example overlay snippet (raises KB compile LLM budget):

```json
{
  "json_ir": {
    "max_kb_llm_calls": 12
  }
}
```

## `.env` (minimal)

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | API secret (OpenAI direct) |
| `OPENAI_MODEL` | Optional default model |
| `OPENAI_EXPLAINER_MODEL` | Optional model for NL paraphrase only |
| `LLM_PROVIDER` | `openai` (default) or `openrouter` |
| `LLM_API_KEY` | Provider-neutral API key override |
| `LLM_MODEL` | Provider-neutral model override (wins over `OPENAI_MODEL`) |
| `LLM_BASE_URL` | Custom API base URL |
| `OPENROUTER_API_KEY` | OpenRouter secret |
| `OPENROUTER_MODEL` | OpenRouter model id (e.g. `anthropic/claude-sonnet-4.6`) |
| `OPENROUTER_BASE_URL` | Default `https://openrouter.ai/api/v1` |
| `OPENROUTER_HTTP_REFERER` | Optional OpenRouter header |
| `OPENROUTER_APP_TITLE` | Optional OpenRouter header |
| `PIPELINE_USE_LLM_EXPLANATIONS` | Enable LLM NL paraphrase for explanations |
| `PIPELINE_DEBUG` | Extra debug logging to console |

### `llm` section (`default.json`)

| Key | Purpose |
|-----|---------|
| `provider` | `openai` or `openrouter` (overridable via `LLM_PROVIDER`) |
| `model` | Default model when env vars unset |
| `base_url` | API base URL |
| `use_seed` | Pass `seed` to chat completions (default off for OpenRouter) |
| `use_response_format` | Pass `response_format` (default off for OpenRouter) |
| `use_reasoning_effort` | Pass `reasoning_effort` when supported |
| `timeout_seconds` | OpenAI SDK client timeout |

Everything else (JSON-IR repair limits, scope mode, extraction backend, trace, legacy LE flags, scoring) belongs in **`default.json`** / **`local.json`**.

## Run artifacts

Each JSON benchmark run writes **`effective_config.json`** (merged default + local + profile + env overrides, plus **`llm_runtime`** with provider/model/host only — never API keys) next to other run outputs.
