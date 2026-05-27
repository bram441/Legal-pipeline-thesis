# Pipeline configuration

Versioned behavior lives in **`default.json`**. Optional machine-local overrides go in **`local.json`** (gitignored — copy from `local.json.example`).

Secrets (`OPENAI_API_KEY`, model names) stay in **`.env`** only.

Most former `.env` pipeline knobs now live in **`default.json`** or **`local.json`**. Keep `.env` minimal; use `local.json` for machine-specific overrides (e.g. `legacy.use_le`, `debug.trace`, `json_ir.max_kb_llm_calls`).

Environment variables listed in `pipeline/config.py` still override config when set (optional escape hatch).

## `json_ir.scope_mode`

Controls how much law text is passed to KB compilation before symbol/rules generation (`pipeline/kb/law_scope.py`).

| Value | Behavior |
|-------|----------|
| **`cited`** (default) | Prefer citation-based chunk selection when the question cites articles/paragraphs; otherwise keyword retrieval or full law fallback |
| **`full`** | Always use the entire law text |
| **`retrieve`** | Keyword-based chunk retrieval from question + case text |

There is no `"auto"` mode — the previous implicit default was **`cited`**, which matches historical `JSON_IR_SCOPE_MODE` behavior when unset.

Override via config, `config/local.json`, or env: `JSON_IR_SCOPE_MODE`, `PIPELINE_LAW_SCOPE_MODE`, or `LAW_SCOPE_MODE`.

## Local overrides

Copy the example file:

```bash
cp config/local.json.example config/local.json
```

Edit `local.json` with partial overrides only; unspecified keys fall back to `default.json`.

### Config profiles (CLI overlay)

Merge order: **`default.json`** → **`local.json`** (if present) → **profile** (optional) → **environment variables**.

Pass a profile on evaluation or a single run (no need to edit `local.json`):

```powershell
python scripts/run_evaluation.py --config config/final.json --runs-dir inputs/json_final --runs run_001 --strategies direct_json_ir_no_translate
python main.py --mode json --run inputs/json_final/run_001 --config config/ablation_balanced.json --kb-strategy direct_json_ir_no_translate --no-translate
```

When `--config` is omitted, `run_evaluation.py` uses **default + local only** (and clears a stale `PIPELINE_CONFIG_PROFILE` from the shell). `main.py` without `--config` still respects `PIPELINE_CONFIG_PROFILE` if you export it.

**`--ignore-local-config`** skips `config/local.json` so only **default → profile → env** apply. Use for reproducible ablations (`run_config_ablation.py` passes this automatically).

| File | Purpose |
|------|---------|
| `config/cheap.json` | Debugging / smoke — low LLM budget |
| `config/eval.json` | Medium reproducible evaluation |
| `config/final.json` | Final thesis run — higher budget |
| `config/ablation_balanced.json` | Balanced ablation profile |

### Evaluation keys (`evaluation` section)

| Key | Default | Meaning |
|-----|---------|---------|
| `belief_scoring` | `false` | When true, open-world may score via belief threshold |
| `boolean_belief_threshold` | `0.5` | Threshold when belief scoring enabled |
| `run_pre_query_satisfiability_check` | `true` | SAT check before query |
| `pragmatic_factual_criteria_mode` | `false` | Allow factual criteria as case inputs (thesis comparison) |
| `model_expansion_max_models` | `3` | Cap for model-expansion diagnostics (not Boolean entailment) |

**`eval.json`** — same as eval profile above; suggested: `max_kb_llm_calls: 14`, `max_symbol_versions: 4`.

Example (raises KB compile LLM budget):

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
| `OPENAI_EXPLAINER_MODEL` | Optional model for NL paraphrase |
| `LLM_PROVIDER` | `openai` (default) or `openrouter` |
| `LLM_API_KEY` | Provider-neutral API key override |
| `LLM_MODEL` | Provider-neutral model override (wins over `OPENAI_MODEL`) |
| `LLM_BASE_URL` | Custom API base URL |
| `OPENROUTER_API_KEY` | OpenRouter secret |
| `OPENROUTER_MODEL` | OpenRouter model id (e.g. `openai/gpt-5.5`) |
| `OPENROUTER_BASE_URL` | Default `https://openrouter.ai/api/v1` |
| `OPENROUTER_HTTP_REFERER` | Optional OpenRouter header |
| `OPENROUTER_APP_TITLE` | Optional OpenRouter header |
| `PIPELINE_USE_LLM_EXPLANATIONS` | Enable LLM explanations (not in JSON config yet) |
| `PIPELINE_KB_COMPILER` | KB LLM provider (`openai` only) |
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

Everything else (JSON-IR repair limits, scope mode, extraction backend, trace via config, legacy LE flags, scoring) belongs in **`default.json`** / **`local.json`**.

## Run artifacts

Each JSON benchmark run writes **`effective_config.json`** (merged default + local + env overrides, plus **`llm_runtime`** with provider/model/host only — never API keys) next to other run outputs.
