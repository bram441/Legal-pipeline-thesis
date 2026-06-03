# Model sweep report

Generated: 2026-05-28T07:32:58.423477+00:00

**Warnings**

- Model sweeps on a subset are exploratory only.
- Confirm the final model with a full best-strategy run on the thesis test set.
- ``possible`` / model-expansion answers are not Boolean entailment.
- Compare models only with the same strategy, config profile, and test set.
- Non-OpenAI models may be worse at strict JSON; validation/repair still applies.
- Cost limits are best-effort when enforced only after each model completes.

## Ranking (strict accuracy, then decisive precision, coverage, cost)

| Rank | Model | Provider | Exit | Strict acc | Coverage | Decisive prec | Cost USD | Tokens |
|---:|---|---|:---:|---:|---:|---:|---:|---:|
| 1 | openai/gpt-5.5 | openrouter | 1 | 0.3243 | 0.6757 | 1.0000 | — | 1677493 |
| 2 | google/gemini-3.1-pro-preview | openrouter | 1 | 0.2973 | 0.6486 | 0.9167 | — | 2300007 |

## Per-model output directories

- `openai/gpt-5.5` → `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\model_selection_final\openai_gpt-5.5_20260528T060300`
- `google/gemini-3.1-pro-preview` → `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\model_selection_final\google_gemini-3.1-pro-preview_20260528T060300`
