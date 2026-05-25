# Project guide (sanity map)

Quick map of the architecture. The stack is **JSON-IR only** (KB compile + extraction).

## 1) KB strategies

| Strategy | Translation | LE intermediate |
|----------|-------------|-----------------|
| `direct_json_ir_translate` | yes | no |
| `direct_json_ir_no_translate` | no | no |
| `le_json_ir_translate` | yes | yes |
| `le_json_ir_no_translate` | no | yes |

## 2) End-to-end flow

`main.py` → `pipeline/app/pipeline.py::answer_legal_prompt(...)`

1. **Effective config** — `config/default.json` + `config/local.json` + env → `effective_config.json`
2. **Law scoping** — citation/keyword chunk selection (`pipeline/kb/law_scope.py`, `json_ir.scope_mode`)
3. **Optional translation** — NL → EN for law/case/question (`pipeline/translation/`)
4. **Optional Legal English** — for `le_json_ir_*` strategies only (`pipeline/le/`)
5. **JSON-IR KB compile** — symbols LLM → rules LLM → validation/repair loop (`json_ir_compile_loop.py`)
6. **Schema environment** — assertable symbols, factual inputs, query targets (`schema_environment.py`)
7. **Case extraction** — JSON-IR IR → validated facts (`extraction/json_ir.py`, `case_fact_validation.py`)
8. **Query extraction** — legal-output target selection (`query_target_selection.py`, `query_period_binding.py`)
9. **Pre-query satisfiability** — intent routing + SAT (`semantic/intent_routing.py`, `symbolic/consistency_check.py`)
10. **Pre-solver validation** — entity types, domain seeding (`validation/`)
11. **Symbolic execution** — intent → IDP-Z3 (`symbolic/router.py`, `idp_z3/`)
12. **Scoring & diagnostics** — decisive Boolean match, proof gap, LLM call tracking

## 3) Configuration

- **Secrets:** `.env` — `OPENAI_API_KEY`, optional `OPENAI_MODEL`
- **Behavior:** `config/default.json` + optional `config/local.json`
- **LE:** `le.use_le` or `PIPELINE_USE_LE=1` for `le_json_ir_*` strategies

## 4) Evaluation

```text
python scripts/run_evaluation.py --runs-dir inputs/json_final --runs run_001 --strategies direct_json_ir_no_translate
```

## 5) Prompts

- `prompts/kb/json_ir/` — symbols + rules generation/repair
- `prompts/extraction/json_ir/` — case/query extraction
- `prompts/le/generation/law_to_le.txt` — LE layer for `le_json_ir_*`
