# Evaluation report

- Generated: 20260527T200505Z
- Runs directory: C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\inputs\json_final_clean

## Pipeline status summary

- Cells total: 37
- **Scored cells** (valid ``score.json`` with ``total``): 31
- **evaluation_no_score** (exit 0, no score): 0
- **evaluation_bad_score**: 0
- **law_compilation** failures: 6
- Other failures: 0
- Accuracy (decisive, **scored cells only**): 1.0000

Unscored cells are **not** successful pipeline completions; they are evaluation failures.

## Accuracy (decisive: correct / total; inconclusive counts as not correct)

Only **scored** cells show accuracy. Others show ``FAIL`` or status label.

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | 1.0000 (1/1, inc=0) |
| run_002 | 0.0000 (0/1, inc=1) |
| run_003 | law_compilation |
| run_004 | completed_with_errors |
| run_005 | 0.0000 (0/1, inc=1) |
| run_006 | 1.0000 (1/1, inc=0) |
| run_007 | 1.0000 (1/1, inc=0) |
| run_008 | 0.0000 (0/1, inc=1) |
| run_009 | 1.0000 (1/1, inc=0) |
| run_101 | 1.0000 (1/1, inc=0) |
| run_102 | completed_with_errors |
| run_103 | 1.0000 (1/1, inc=0) |
| run_104 | 1.0000 (1/1, inc=0) |
| run_105 | 0.0000 (0/1, inc=1) |
| run_106 | 1.0000 (1/1, inc=0) |
| run_107 | 1.0000 (1/1, inc=0) |
| run_108 | 1.0000 (1/1, inc=0) |
| run_109 | 1.0000 (1/1, inc=0) |
| run_110 | law_compilation |
| run_111 | 0.0000 (0/1, inc=1) |
| run_112 | 0.0000 (0/1, inc=1) |
| run_113 | 0.0000 (0/1, inc=1) |
| run_114 | 1.0000 (1/1, inc=0) |
| run_115 | 0.0000 (0/1, inc=1) |
| run_116 | law_compilation |
| run_117 | law_compilation |
| run_118 | 1.0000 (1/1, inc=0) |
| run_119 | law_compilation |
| run_120 | 1.0000 (1/1, inc=0) |
| run_201 | 1.0000 (1/1, inc=0) |
| run_202 | 0.0000 (0/1, inc=1) |
| run_203 | 1.0000 (1/1, inc=0) |
| run_204 | completed_with_errors |
| run_205 | 0.0000 (0/1, inc=1) |
| run_206 | law_compilation |
| run_207 | 0.0000 (0/1, inc=1) |
| run_208 | 1.0000 (1/1, inc=0) |

## Strategy configuration

JSON_IR backend always compiles via ``symbols_then_rules`` (symbols then rules).

| Strategy | Canonical | LE | Config trans | Effective trans | Source | JSON IR | Depr |
|---|:---|:---:|:---:|:---:|:---|:---|:---:|
| direct_json_ir_no_translate | direct_json_ir_no_translate | no | no | no | strategy | symbols_then_rules | no |

## Failure / status category

Heuristic label from `run_trace.txt` / `kb_compile.log` (see `eval_support.classify_failure`).

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | completed |
| run_002 | completed |
| run_003 | law_compilation |
| run_004 | completed_with_errors |
| run_005 | completed |
| run_006 | completed |
| run_007 | completed |
| run_008 | completed |
| run_009 | completed |
| run_101 | completed |
| run_102 | completed_with_errors |
| run_103 | completed |
| run_104 | completed |
| run_105 | completed |
| run_106 | completed |
| run_107 | completed |
| run_108 | completed |
| run_109 | completed |
| run_110 | law_compilation |
| run_111 | completed |
| run_112 | completed |
| run_113 | completed |
| run_114 | completed |
| run_115 | completed |
| run_116 | law_compilation |
| run_117 | law_compilation |
| run_118 | completed |
| run_119 | law_compilation |
| run_120 | completed |
| run_201 | completed |
| run_202 | completed |
| run_203 | completed |
| run_204 | completed_with_errors |
| run_205 | completed |
| run_206 | law_compilation |
| run_207 | completed |
| run_208 | completed |

## Query target diagnostics

Per-question query predicate and kind from `score.json` items. ``observable_query_target_warning_count`` / ``antecedent_diagnostic_warning_count`` split score warnings.

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | oqt=0,ant=0 (derived:surviving_spouse_acquires_usufruct_of_entire_estate) |
| run_002 | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_003 | — |
| run_004 | oqt=0,ant=0 |
| run_005 | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_006 | oqt=0,ant=0 (derived:loses_kleine_vennootschap_status_from) |
| run_007 | oqt=0,ant=0 (derived:acquires_usufruct_of_family_residence) |
| run_008 | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_009 | oqt=0,ant=0 (derived:is_kleine_vennootschap) |
| run_101 | oqt=0,ant=0 (derived:receives_usufruct_of_entire_estate) |
| run_102 | oqt=0,ant=0 |
| run_103 | oqt=0,ant=0 (derived:acquires_full_ownership_of_entire_estate) |
| run_104 | oqt=0,ant=0 (derived:acquires_usufruct_over) |
| run_105 | oqt=0,ant=0 (derived:exception_applies) |
| run_106 | oqt=0,ant=0 (derived:acquires_right_to_lease) |
| run_107 | oqt=0,ant=0 (derived:is_foreigner) |
| run_108 | oqt=0,ant=0 (derived:is_foreigner) |
| run_109 | oqt=0,ant=1 (derived:is_third_country_national) |
| run_110 | — |
| run_111 | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_112 | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_113 | oqt=0,ant=0 (derived:is_kleine_vennootschap) |
| run_114 | oqt=0,ant=0 (derived:is_kleine_vennootschap) |
| run_115 | oqt=0,ant=2 (derived:is_micro_company) |
| run_116 | — |
| run_117 | — |
| run_118 | oqt=0,ant=1 (derived:is_micro_company) |
| run_119 | — |
| run_120 | oqt=0,ant=0 (derived:loses_small_company_status_from) |
| run_201 | oqt=0,ant=0 (derived:receives_usufruct_of_entire_estate) |
| run_202 | oqt=0,ant=2 (derived:receives_usufruct_of_entire_estate) |
| run_203 | oqt=0,ant=0 (derived:is_foreigner) |
| run_204 | oqt=0,ant=0 |
| run_205 | oqt=0,ant=0 (derived:is_micro_company) |
| run_206 | — |
| run_207 | oqt=0,ant=2 (derived:acquires_right_to_lease) |
| run_208 | oqt=0,ant=0 (derived:is_kleine_vennootschap) |

## Timing

- Elapsed: 32.8m (1970.33 s)
- Cells recorded: 37
- Avg per cell: 53.2s (53.22 s)

See `timings.csv` for per (run, strategy) durations.

## Details (JSON)

See `matrix.json`.

## Grouped metrics (manifest tiers)

Aggregated over matrix cells. ``strict_accuracy`` = decisive_correct / total_questions; ``decisive_precision`` = decisive_correct / decisive_answers; ``coverage`` = scored_cells / total_cells.

### By strategy

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| direct_json_ir_no_translate | 37 | 31 | 17 | 0 | 11 | 16% | 0.46 | 0.61 | 1.00 | 0.84 |

### By evaluation_group

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| challenge | 10 | 8 | 5 | 0 | 3 | 20% | 0.50 | 0.62 | 1.00 | 0.80 |
| core | 23 | 20 | 10 | 0 | 7 | 13% | 0.43 | 0.59 | 1.00 | 0.87 |
| stress | 4 | 3 | 2 | 0 | 1 | 25% | 0.50 | 0.67 | 1.00 | 0.75 |

### By difficulty

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| basic | 20 | 17 | 9 | 0 | 7 | 15% | 0.45 | 0.56 | 1.00 | 0.85 |
| hard | 4 | 3 | 2 | 0 | 1 | 25% | 0.50 | 0.67 | 1.00 | 0.75 |
| intermediate | 13 | 11 | 6 | 0 | 3 | 15% | 0.46 | 0.67 | 1.00 | 0.85 |

### By law_domain

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| company | 14 | 9 | 6 | 0 | 3 | 36% | 0.43 | 0.67 | 1.00 | 0.64 |
| immigration | 11 | 10 | 4 | 0 | 5 | 9% | 0.36 | 0.44 | 1.00 | 0.91 |
| inheritance | 12 | 12 | 7 | 0 | 3 | 0% | 0.58 | 0.70 | 1.00 | 1.00 |

### By phenomenon

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| case_given_criteria | 3 | 3 | 0 | 0 | 3 | 0% | 0.00 | 0.00 | — | 1.00 |
| classification | 12 | 8 | 5 | 0 | 3 | 33% | 0.42 | 0.62 | 1.00 | 0.67 |
| definition | 14 | 13 | 7 | 0 | 5 | 7% | 0.50 | 0.58 | 1.00 | 0.93 |
| legal_effect | 15 | 14 | 9 | 0 | 3 | 7% | 0.60 | 0.75 | 1.00 | 0.93 |
| negative_exclusion | 11 | 9 | 5 | 0 | 3 | 18% | 0.45 | 0.62 | 1.00 | 0.82 |
| numeric_threshold | 13 | 8 | 5 | 0 | 3 | 38% | 0.38 | 0.62 | 1.00 | 0.62 |
| structural_exclusion | 1 | 1 | 1 | 0 | 0 | 0% | 1.00 | 1.00 | 1.00 | 1.00 |
| temporal | 3 | 2 | 2 | 0 | 0 | 33% | 0.67 | 1.00 | 1.00 | 0.67 |

