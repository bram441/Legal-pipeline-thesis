# Evaluation report

- Generated: 20260527T193211Z
- Runs directory: C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\inputs\json_final_clean

## Pipeline status summary

- Cells total: 37
- **Scored cells** (valid ``score.json`` with ``total``): 31
- **evaluation_no_score** (exit 0, no score): 0
- **evaluation_bad_score**: 0
- **law_compilation** failures: 6
- Other failures: 0
- Accuracy (decisive, **scored cells only**): 0.9474

Unscored cells are **not** successful pipeline completions; they are evaluation failures.

## Accuracy (decisive: correct / total; inconclusive counts as not correct)

Only **scored** cells show accuracy. Others show ``FAIL`` or status label.

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | 1.0000 (1/1, inc=0) |
| run_002 | 1.0000 (1/1, inc=0) |
| run_003 | 0.0000 (0/1, inc=1) |
| run_004 | completed_with_errors |
| run_005 | 1.0000 (1/1, inc=0) |
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
| run_108 | law_compilation |
| run_109 | law_compilation |
| run_110 | 1.0000 (1/1, inc=0) |
| run_111 | 1.0000 (1/1, inc=0) |
| run_112 | 0.0000 (0/1, inc=1) |
| run_113 | 0.0000 (0/1, inc=1) |
| run_114 | 1.0000 (1/1, inc=0) |
| run_115 | 0.0000 (0/1, inc=1) |
| run_116 | law_compilation |
| run_117 | 1.0000 (1/1, inc=0) |
| run_118 | law_compilation |
| run_119 | 0.0000 (0/1, inc=0) |
| run_120 | 1.0000 (1/1, inc=0) |
| run_201 | 1.0000 (1/1, inc=0) |
| run_202 | 0.0000 (0/1, inc=1) |
| run_203 | 0.0000 (0/1, inc=1) |
| run_204 | 0.0000 (0/1, inc=1) |
| run_205 | law_compilation |
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
| run_003 | completed |
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
| run_108 | law_compilation |
| run_109 | law_compilation |
| run_110 | completed |
| run_111 | completed |
| run_112 | completed |
| run_113 | completed |
| run_114 | completed |
| run_115 | completed |
| run_116 | law_compilation |
| run_117 | completed |
| run_118 | law_compilation |
| run_119 | completed |
| run_120 | completed |
| run_201 | completed |
| run_202 | completed |
| run_203 | completed |
| run_204 | completed |
| run_205 | law_compilation |
| run_206 | law_compilation |
| run_207 | completed |
| run_208 | completed |

## Query target diagnostics

Per-question query predicate and kind from `score.json` items. ``observable_query_target_warning_count`` / ``antecedent_diagnostic_warning_count`` split score warnings.

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | oqt=0,ant=0 (derived:surviving_spouse_inherits_usufruct_of_entire_estate) |
| run_002 | oqt=0,ant=0 (derived:is_foreigner) |
| run_003 | oqt=0,ant=0 (derived:is_micro_company) |
| run_004 | oqt=0,ant=0 |
| run_005 | oqt=0,ant=1 (derived:is_third_country_national) |
| run_006 | oqt=0,ant=0 (derived:loses_kleine_vennootschap_status_from) |
| run_007 | oqt=0,ant=0 (derived:acquires_usufruct_over) |
| run_008 | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_009 | oqt=0,ant=0 (derived:is_kleine_vennootschap) |
| run_101 | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) |
| run_102 | oqt=0,ant=0 |
| run_103 | oqt=0,ant=0 (derived:acquires_full_ownership_of_entire_estate) |
| run_104 | oqt=0,ant=0 (derived:acquires_usufruct_of) |
| run_105 | oqt=0,ant=0 (derived:preceding_provisions_apply) |
| run_106 | oqt=0,ant=0 (derived:acquires_right_to_lease) |
| run_107 | oqt=0,ant=0 (derived:is_foreigner) |
| run_108 | — |
| run_109 | — |
| run_110 | oqt=0,ant=0 (derived:is_third_country_national) |
| run_111 | oqt=0,ant=1 (derived:risk_of_absconding) |
| run_112 | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_113 | oqt=0,ant=0 (derived:is_kleine_vennootschap) |
| run_114 | oqt=0,ant=0 (derived:is_kleine_vennootschap) |
| run_115 | oqt=0,ant=2 (derived:is_micro_company) |
| run_116 | — |
| run_117 | oqt=0,ant=1 (derived:is_micro_company) |
| run_118 | — |
| run_119 | oqt=0,ant=1 (derived:is_small_company) |
| run_120 | oqt=0,ant=0 (derived:loses_kleine_vennootschap_status_from) |
| run_201 | oqt=0,ant=0 (derived:receives_usufruct_of_entire_estate) |
| run_202 | oqt=0,ant=0 (derived:receives_usufruct_of_entire_estate) |
| run_203 | oqt=0,ant=0 (derived:is_foreigner) |
| run_204 | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_205 | — |
| run_206 | — |
| run_207 | oqt=0,ant=2 (derived:acquires_right_to_lease) |
| run_208 | oqt=0,ant=0 (derived:is_kleine_vennootschap) |

## Timing

- Elapsed: 32.9m (1974.03 s)
- Cells recorded: 37
- Avg per cell: 53.3s (53.32 s)

See `timings.csv` for per (run, strategy) durations.

## Details (JSON)

See `matrix.json`.

## Grouped metrics (manifest tiers)

Aggregated over matrix cells. ``strict_accuracy`` = decisive_correct / total_questions; ``decisive_precision`` = decisive_correct / decisive_answers; ``coverage`` = scored_cells / total_cells.

### By strategy

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| direct_json_ir_no_translate | 37 | 31 | 18 | 1 | 10 | 16% | 0.49 | 0.62 | 0.95 | 0.84 |

### By evaluation_group

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| challenge | 10 | 8 | 6 | 0 | 2 | 20% | 0.60 | 0.75 | 1.00 | 0.80 |
| core | 23 | 19 | 10 | 0 | 7 | 17% | 0.43 | 0.59 | 1.00 | 0.83 |
| stress | 4 | 4 | 2 | 1 | 1 | 0% | 0.50 | 0.50 | 0.67 | 1.00 |

### By difficulty

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| basic | 20 | 16 | 9 | 0 | 7 | 20% | 0.45 | 0.56 | 1.00 | 0.80 |
| hard | 4 | 4 | 2 | 1 | 1 | 0% | 0.50 | 0.50 | 0.67 | 1.00 |
| intermediate | 13 | 11 | 7 | 0 | 2 | 15% | 0.54 | 0.78 | 1.00 | 0.85 |

### By law_domain

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| company | 14 | 10 | 6 | 1 | 3 | 29% | 0.43 | 0.60 | 0.86 | 0.71 |
| immigration | 11 | 9 | 5 | 0 | 4 | 18% | 0.45 | 0.56 | 1.00 | 0.82 |
| inheritance | 12 | 12 | 7 | 0 | 3 | 0% | 0.58 | 0.70 | 1.00 | 1.00 |

### By phenomenon

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| case_given_criteria | 3 | 3 | 1 | 0 | 2 | 0% | 0.33 | 0.33 | 1.00 | 1.00 |
| classification | 12 | 8 | 5 | 0 | 3 | 33% | 0.42 | 0.62 | 1.00 | 0.67 |
| definition | 14 | 12 | 8 | 0 | 4 | 14% | 0.57 | 0.67 | 1.00 | 0.86 |
| legal_effect | 15 | 15 | 9 | 1 | 3 | 0% | 0.60 | 0.69 | 0.90 | 1.00 |
| negative_exclusion | 11 | 9 | 4 | 0 | 5 | 18% | 0.36 | 0.44 | 1.00 | 0.82 |
| numeric_threshold | 13 | 10 | 6 | 1 | 3 | 23% | 0.46 | 0.60 | 0.86 | 0.77 |
| structural_exclusion | 1 | 0 | 0 | 0 | 0 | 100% | 0.00 | — | — | 0.00 |
| temporal | 3 | 3 | 2 | 1 | 0 | 0% | 0.67 | 0.67 | 0.67 | 1.00 |

