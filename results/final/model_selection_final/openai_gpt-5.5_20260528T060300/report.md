# Evaluation report

- Generated: 20260528T060429Z
- Runs directory: C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\inputs\json_final_clean

## Pipeline status summary

- Cells total: 37
- **Scored cells** (valid ``score.json`` with ``total``): 25
- **evaluation_no_score** (exit 0, no score): 0
- **evaluation_bad_score**: 0
- **law_compilation** failures: 2
- Other failures: 10
- Accuracy (decisive, **scored cells only**): 1.0000

Unscored cells are **not** successful pipeline completions; they are evaluation failures.

## Accuracy (decisive: correct / total; inconclusive counts as not correct)

Only **scored** cells show accuracy. Others show ``FAIL`` or status label.

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | 1.0000 (1/1, inc=0) |
| run_002 | kb_idp_parse |
| run_003 | law_compilation |
| run_004 | 0.0000 (0/1, inc=1) |
| run_005 | kb_idp_parse |
| run_006 | kb_idp_parse |
| run_007 | 1.0000 (1/1, inc=0) |
| run_008 | kb_idp_parse |
| run_009 | 1.0000 (1/1, inc=0) |
| run_101 | 1.0000 (1/1, inc=0) |
| run_102 | completed_with_errors |
| run_103 | 0.0000 (0/1, inc=1) |
| run_104 | completed_with_errors |
| run_105 | 0.0000 (0/1, inc=1) |
| run_106 | 1.0000 (1/1, inc=0) |
| run_107 | kb_idp_parse |
| run_108 | 1.0000 (1/1, inc=0) |
| run_109 | kb_idp_parse |
| run_110 | 1.0000 (1/1, inc=0) |
| run_111 | kb_idp_parse |
| run_112 | kb_idp_parse |
| run_113 | 0.0000 (0/1, inc=1) |
| run_114 | 1.0000 (1/1, inc=0) |
| run_115 | 0.0000 (0/1, inc=1) |
| run_116 | law_compilation |
| run_117 | 0.0000 (0/1, inc=1) |
| run_118 | 0.0000 (0/1, inc=1) |
| run_119 | 1.0000 (1/1, inc=0) |
| run_120 | 0.0000 (0/1, inc=1) |
| run_201 | 1.0000 (1/1, inc=0) |
| run_202 | 0.0000 (0/1, inc=1) |
| run_203 | kb_idp_parse |
| run_204 | kb_idp_parse |
| run_205 | 0.0000 (0/1, inc=1) |
| run_206 | 1.0000 (1/1, inc=0) |
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
| run_002 | kb_idp_parse |
| run_003 | law_compilation |
| run_004 | completed |
| run_005 | kb_idp_parse |
| run_006 | kb_idp_parse |
| run_007 | completed |
| run_008 | kb_idp_parse |
| run_009 | completed |
| run_101 | completed |
| run_102 | completed_with_errors |
| run_103 | completed |
| run_104 | completed_with_errors |
| run_105 | completed |
| run_106 | completed |
| run_107 | kb_idp_parse |
| run_108 | completed |
| run_109 | kb_idp_parse |
| run_110 | completed |
| run_111 | kb_idp_parse |
| run_112 | kb_idp_parse |
| run_113 | completed |
| run_114 | completed |
| run_115 | completed |
| run_116 | law_compilation |
| run_117 | completed |
| run_118 | completed |
| run_119 | completed |
| run_120 | completed |
| run_201 | completed |
| run_202 | completed |
| run_203 | kb_idp_parse |
| run_204 | kb_idp_parse |
| run_205 | completed |
| run_206 | completed |
| run_207 | completed |
| run_208 | completed |

## Query target diagnostics

Per-question query predicate and kind from `score.json` items. ``observable_query_target_warning_count`` / ``antecedent_diagnostic_warning_count`` split score warnings.

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | oqt=0,ant=0 (derived:obtains_usufruct_of_entire_estate) |
| run_002 | — |
| run_003 | — |
| run_004 | oqt=0,ant=0 |
| run_005 | — |
| run_006 | — |
| run_007 | oqt=0,ant=0 (derived:has_usufruct_right_over) |
| run_008 | — |
| run_009 | oqt=0,ant=0 (derived:is_small_company) |
| run_101 | oqt=0,ant=1 (derived:obtains_usufruct_of_entire_estate) |
| run_102 | oqt=0,ant=0 |
| run_103 | oqt=0,ant=2 (derived:obtains_full_ownership_of_entire_estate) |
| run_104 | oqt=0,ant=0 |
| run_105 | oqt=0,ant=0 (derived:preceding_provisions_not_applicable) |
| run_106 | oqt=0,ant=0 (derived:obtains_exclusive_lease_right) |
| run_107 | — |
| run_108 | oqt=0,ant=0 (derived:is_foreigner) |
| run_109 | — |
| run_110 | oqt=0,ant=0 (derived:is_third_country_national) |
| run_111 | — |
| run_112 | — |
| run_113 | oqt=0,ant=0 (derived:is_small_company) |
| run_114 | oqt=0,ant=0 (derived:is_small_company) |
| run_115 | oqt=0,ant=2 (derived:is_micro_company) |
| run_116 | — |
| run_117 | oqt=0,ant=2 (derived:is_micro_company) |
| run_118 | oqt=0,ant=2 (derived:is_micro_company) |
| run_119 | oqt=0,ant=0 (derived:estimate_must_be_taken_into_account_immediately) |
| run_120 | oqt=0,ant=0 (derived:loses_small_company_status_from) |
| run_201 | oqt=0,ant=0 (derived:obtains_usufruct_of_entire_estate) |
| run_202 | oqt=0,ant=0 (derived:obtains_usufruct_of_entire_estate) |
| run_203 | — |
| run_204 | — |
| run_205 | oqt=0,ant=2 (derived:is_micro_company) |
| run_206 | oqt=0,ant=1 (derived:is_micro_company) |
| run_207 | oqt=0,ant=2 (derived:has_right_to_lease) |
| run_208 | oqt=0,ant=0 (derived:is_small_company) |

## Timing

- Elapsed: 1.47h (5309.22 s)
- Cells recorded: 37
- Avg per cell: 2.4m (143.46 s)

See `timings.csv` for per (run, strategy) durations.

## Details (JSON)

See `matrix.json`.

## Grouped metrics (manifest tiers)

Aggregated over matrix cells. ``strict_accuracy`` = decisive_correct / total_questions; ``decisive_precision`` = decisive_correct / decisive_answers; ``coverage`` = scored_cells / total_cells.

### By strategy

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| direct_json_ir_no_translate | 37 | 25 | 12 | 0 | 11 | 5% | 0.32 | 0.52 | 1.00 | 0.68 |

### By evaluation_group

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| challenge | 10 | 7 | 3 | 0 | 4 | 10% | 0.30 | 0.43 | 1.00 | 0.70 |
| core | 23 | 16 | 8 | 0 | 6 | 4% | 0.35 | 0.57 | 1.00 | 0.70 |
| stress | 4 | 2 | 1 | 0 | 1 | 0% | 0.25 | 0.50 | 1.00 | 0.50 |

### By difficulty

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| basic | 20 | 13 | 8 | 0 | 5 | 5% | 0.40 | 0.62 | 1.00 | 0.65 |
| hard | 4 | 2 | 1 | 0 | 1 | 0% | 0.25 | 0.50 | 1.00 | 0.50 |
| intermediate | 13 | 10 | 3 | 0 | 5 | 8% | 0.23 | 0.38 | 1.00 | 0.77 |

### By law_domain

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| company | 14 | 11 | 5 | 0 | 6 | 14% | 0.36 | 0.45 | 1.00 | 0.79 |
| immigration | 11 | 2 | 2 | 0 | 0 | 0% | 0.18 | 1.00 | 1.00 | 0.18 |
| inheritance | 12 | 12 | 5 | 0 | 5 | 0% | 0.42 | 0.50 | 1.00 | 1.00 |

### By phenomenon

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| case_given_criteria | 3 | 0 | 0 | 0 | 0 | 0% | 0.00 | — | — | 0.00 |
| classification | 12 | 10 | 4 | 0 | 6 | 17% | 0.33 | 0.40 | 1.00 | 0.83 |
| definition | 14 | 5 | 4 | 0 | 0 | 0% | 0.29 | 1.00 | 1.00 | 0.36 |
| legal_effect | 15 | 14 | 6 | 0 | 6 | 0% | 0.40 | 0.50 | 1.00 | 0.93 |
| negative_exclusion | 11 | 8 | 5 | 0 | 3 | 0% | 0.45 | 0.62 | 1.00 | 0.73 |
| numeric_threshold | 13 | 10 | 5 | 0 | 5 | 15% | 0.38 | 0.50 | 1.00 | 0.77 |
| structural_exclusion | 1 | 1 | 0 | 0 | 1 | 0% | 0.00 | 0.00 | — | 1.00 |
| temporal | 3 | 2 | 1 | 0 | 1 | 0% | 0.33 | 0.50 | 1.00 | 0.67 |

