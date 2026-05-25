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

**`eval.json`** — optional benchmark/eval profile (not loaded automatically). Copy values into `local.json` or set env vars when running `scripts/run_evaluation.py` or clean-compile audits. Suggested eval knobs: `max_kb_llm_calls: 14`, `max_symbol_versions: 4`.

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
| `OPENAI_API_KEY` | Required API secret |
| `OPENAI_MODEL` | Optional default model for extraction/KB/translation |
| `OPENAI_EXPLAINER_MODEL` | Optional model for NL paraphrase |
| `PIPELINE_USE_LLM_EXPLANATIONS` | Enable LLM explanations (not in JSON config yet) |
| `PIPELINE_KB_COMPILER` | KB LLM provider (`openai` only) |
| `PIPELINE_DEBUG` | Extra debug logging to console |

Everything else (JSON-IR repair limits, scope mode, extraction backend, trace via config, legacy LE flags, scoring) belongs in **`default.json`** / **`local.json`**.

## Run artifacts

Each JSON benchmark run writes **`effective_config.json`** (merged default + local + env overrides) next to other run outputs.
