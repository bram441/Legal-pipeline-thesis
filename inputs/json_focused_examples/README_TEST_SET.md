# Focused-law diagnostic subset

This folder contains a small diagnostic subset with manually selected legal extracts. Each run has its own `article.txt`, and `run.json` points to that local extract.

This is an oracle article-selection / focused-context diagnostic set. It should not replace the main cleaned-law evaluation. It is useful to estimate how much performance improves when the relevant legal provisions are already selected and irrelevant statutory context is removed.

Selected runs:
- Inheritance: run_001, run_004, run_007
- Immigration: run_002, run_005, run_008
- Company law: run_003, run_009, run_119

Notes:
- `run_003` explicitly adds legal personality to the case text.
- `run_119` is corrected to exceed Article 1:24 thresholds instead of micro-company thresholds.
- Expected answers are otherwise preserved from the corresponding curated runs.
