# Project guide (sanity map)

Quick map of the current architecture. **JSON-IR is the primary path**; legacy direct-FO compilation remains available but is deprecated / lower priority.

## 1) Unified backend modes

Use `--pipeline-backend` (preferred):

| Mode | KB | Extraction |
|------|-----|------------|
| `json_ir` (default) | JSON-IR structured compile | JSON-IR case/query IR |
| `legacy` | Legacy FO compile | Legacy direct JSON extraction |

`--kb-backend` still exists for backward compatibility.

## 2) Canonical KB strategies (JSON-IR)

| Strategy | Translation | LE intermediate |
|----------|-------------|-----------------|
| `direct_json_ir_translate` | yes | no |
| `direct_json_ir_no_translate` | no | no |
| `le_json_ir_translate` | yes | yes |
| `le_json_ir_no_translate` | no | yes |

Legacy aliases (`direct_single`, `le_two_phase`, …) still resolve but are deprecated.

## 3) End-to-end flow

`main.py` → `pipeline/app/pipeline.py::answer_legal_prompt(...)`

1. Load **effective config** (`config/default.json` + optional `config/local.json` + env overrides) → `effective_config.json`
2. KB compile/load (`pipeline/kb/cache.py`, structured repair loop)
3. **Schema environment** (`pipeline/kb/schema_environment.py`) — typed contract for extraction + FO seeding
4. Case extraction with strict assertability + optional **case_given_* factual inputs** (`pipeline/kb/case_given_bridge.py`)
5. Query extraction with **legal-output target selection** (`pipeline/extraction/query_target_selection.py`)
6. Pre-solver validation + **entity type mapping** (`pipeline/validation/`)
7. Symbolic routing (`pipeline/symbolic/router.py`) → IDP-Z3 (`idp_z3/`)
8. Rendering + optional NL paraphrase
9. Optional **symbolic proof-gap** diagnostic (`pipeline/diagnostics/symbolic_proof_gap.py`)

## 4) Configuration

- **Secrets / machine-local:** `.env` — `OPENAI_API_KEY`, optional `OPENAI_MODEL`, debug-only overrides
- **Versioned behavior:** `config/default.json` — JSON-IR repair limits, extraction backend, scoring, trace flags
- **Local overrides:** `config/local.json` (gitignored; see `config/local.json.example`)
- **Env overrides:** legacy `JSON_IR_*`, `PIPELINE_*`, `SCORE_*` still work via `pipeline/config.py`
- **Run artifact:** `effective_config.json` written per `main.py` JSON run

## 5) Case / query contract

- **Schema environment** lists assertable symbols, factual case inputs, legal-output query targets, temporal support symbols.
- **Case facts:** observable symbols by default; controlled helper assertions via `case_given_<pred>` + bridge rules when case text explicitly supports threshold/criterion satisfaction (with `evidence_text`; no invented numerics).
- **Query:** must target legal-output predicates when the question asks for a legal effect; never assert the query predicate as a case fact.

## 6) Scoring

- Default: **decisive** scoring — `unknown` / open-world / inconclusive is **not** correct.
- Optional belief scoring: `evaluation.belief_scoring` in config or eval `--belief-scoring` (env `SCORE_TREAT_OPEN_WITH_BELIEF`).

## 7) Testing

- Pure unit tests import `pipeline.kb.schema_environment`, `case_fact_validation`, etc. **without** `idp_engine`.
- IDP integration tests use `@pytest.mark.requires_idp` and skip when `idp_engine` is missing.

## 8) Generated artifacts

Curated inputs live under `inputs/json/run_*/run.json`. Generated outputs (results, KB cache, diagnostics) are gitignored and removable via:

```bash
python scripts/clean_generated_artifacts.py --dry-run
python scripts/clean_generated_artifacts.py
```

## 9) Prompts

Canonical tree:

- `prompts/kb/json_ir/` — symbols + rules generation/repair
- `prompts/kb/legacy/` — deprecated direct-FO KB prompts
- `prompts/extraction/json_ir/` — case/query extraction
- `prompts/extraction/legacy/` — deprecated extraction prompts
- `prompts/le/generation/` — LE intermediate

Legacy paths resolve through `pipeline/utils/prompt_paths.py` aliases (no duplicate files on disk).
