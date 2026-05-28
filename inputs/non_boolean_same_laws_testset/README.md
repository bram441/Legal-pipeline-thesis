# Non-boolean capability test set using the existing clean law texts

This set contains 20 additional non-true/false questions built from the same cleaned law files used in the main evaluation:

- `erfrecht_clean.txt`
- `microvennootschappen_clean.txt`
- `vreemdelingenwet_clean.txt`

The goal is not to replace the main true/false/unknown benchmark. It is a small capability probe for richer answer types such as classifications, legal effects, thresholds, periods, calculation rules, and condition lists.

## Files

- `plain_inputs/nb_*.json`: input files containing only law text, case text, and question. These may be shown to a model.
- `gold/nb_*.gold.json`: expected answers. Do not include these in prompts.
- `plain_inputs.jsonl`: all plain inputs in JSONL format.
- `gold_answers.jsonl`: all gold answers in JSONL format.

## Important

These questions are not multiple choice and are not true/false/unknown. The scoring therefore cannot use the same exact boolean scoring as the main benchmark. Suggested scoring options:

1. manual scoring;
2. exact/partial match for numeric thresholds and short classifications;
3. LLM-assisted judging with a strict rubric, if clearly reported.

This set should be described as an exploratory capability probe, not as the main quantitative evaluation.
