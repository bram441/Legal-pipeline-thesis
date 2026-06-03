# Deprecated components

The thesis pipeline is **JSON-IR only**. The following are retained for compatibility or history but are not part of the default path.

## Removed or unsupported

| Item | Status |
|------|--------|
| **`rule_plan` KB stage** | Removed. Symbols + rules generation only. |
| **`prompt_profile` config** | Removed. Single canonical `symbols.txt` / `rules.txt`. |
| **`inputs/json/` dev benchmark** | Removed. Use `inputs/json_final_clean/`. |
| **`inputs/text/` manual runs** | Removed. Use JSON benchmark folders. |
| **Direct-FO KB compile (non JSON-IR)** | Deprecated. Use `direct_json_ir_*` or `le_json_ir_*` strategies. |
| **Legacy strategy names** (`le_two_phase`, `direct_single`, …) | Replaced by canonical JSON-IR strategy ids in `pipeline/kb/compile_strategy.py`. |

## Still available but optional

| Item | Notes |
|------|--------|
| **`le_json_ir_*` strategies** | Law → Legal English → JSON-IR. Off by default; enable via strategy flag or `le.use_le`. |
| **`direct_json_ir_translate`** | Translates law/case/question to English before compile. |
| **Belief-based open-world scoring** | Off by default (`evaluation.belief_scoring: false`). |
| **Streamlit UI (`ui/`)** | Stub only; not required for evaluation. |

## Current canonical paths

- **Benchmark:** `inputs/json_final_clean/` (37 runs, clean law texts)
- **Config baseline:** `config/default.json`
- **Thesis LLM budgets:** `config/cheap.json`, `config/balanced.json`, `config/heavy.json`
- **Selected final profile:** `config/heavy.json` with `--ignore-local-config`
