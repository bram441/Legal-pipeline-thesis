# Evaluation report

- Generated: 20260528T040300Z
- Runs directory: C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\inputs\json_final_clean

## Pipeline status summary

- Cells total: 37
- **Scored cells** (valid ``score.json`` with ``total``): 24
- **evaluation_no_score** (exit 0, no score): 0
- **evaluation_bad_score**: 0
- **law_compilation** failures: 12
- Other failures: 1
- Accuracy (decisive, **scored cells only**): 0.9167

Unscored cells are **not** successful pipeline completions; they are evaluation failures.

## Accuracy (decisive: correct / total; inconclusive counts as not correct)

Only **scored** cells show accuracy. Others show ``FAIL`` or status label.

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | 0.0000 (0/1, inc=1) |
| run_002 | law_compilation |
| run_003 | 0.0000 (0/1, inc=1) |
| run_004 | completed_with_errors |
| run_005 | law_compilation |
| run_006 | kb_idp_parse |
| run_007 | 1.0000 (1/1, inc=0) |
| run_008 | law_compilation |
| run_009 | 1.0000 (1/1, inc=0) |
| run_101 | 1.0000 (1/1, inc=0) |
| run_102 | 0.0000 (0/1, inc=1) |
| run_103 | 1.0000 (1/1, inc=0) |
| run_104 | 1.0000 (1/1, inc=0) |
| run_105 | 0.0000 (0/1, inc=1) |
| run_106 | 1.0000 (1/1, inc=0) |
| run_107 | 1.0000 (1/1, inc=0) |
| run_108 | law_compilation |
| run_109 | law_compilation |
| run_110 | law_compilation |
| run_111 | 0.0000 (0/1, inc=1) |
| run_112 | law_compilation |
| run_113 | 0.0000 (0/1, inc=1) |
| run_114 | 1.0000 (1/1, inc=0) |
| run_115 | 0.0000 (0/1, inc=1) |
| run_116 | 0.0000 (0/1, inc=1) |
| run_117 | law_compilation |
| run_118 | law_compilation |
| run_119 | 0.0000 (0/1, inc=0) |
| run_120 | law_compilation |
| run_201 | 1.0000 (1/1, inc=0) |
| run_202 | 0.0000 (0/1, inc=1) |
| run_203 | law_compilation |
| run_204 | 0.0000 (0/1, inc=1) |
| run_205 | 0.0000 (0/1, inc=1) |
| run_206 | law_compilation |
| run_207 | 1.0000 (1/1, inc=0) |
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
| run_002 | law_compilation |
| run_003 | completed |
| run_004 | completed_with_errors |
| run_005 | law_compilation |
| run_006 | kb_idp_parse |
| run_007 | completed |
| run_008 | law_compilation |
| run_009 | completed |
| run_101 | completed |
| run_102 | completed |
| run_103 | completed |
| run_104 | completed |
| run_105 | completed |
| run_106 | completed |
| run_107 | completed |
| run_108 | law_compilation |
| run_109 | law_compilation |
| run_110 | law_compilation |
| run_111 | completed |
| run_112 | law_compilation |
| run_113 | completed |
| run_114 | completed |
| run_115 | completed |
| run_116 | completed |
| run_117 | law_compilation |
| run_118 | law_compilation |
| run_119 | completed |
| run_120 | law_compilation |
| run_201 | completed |
| run_202 | completed |
| run_203 | law_compilation |
| run_204 | completed |
| run_205 | completed |
| run_206 | law_compilation |
| run_207 | completed |
| run_208 | completed |

## Query target diagnostics

Per-question query predicate and kind from `score.json` items. ``observable_query_target_warning_count`` / ``antecedent_diagnostic_warning_count`` split score warnings.

| Run | direct_json_ir_no_translate |
|---|---|
| run_001 | oqt=0,ant=2 (derived:receives_usufruct_of) |
| run_002 | — |
| run_003 | oqt=0,ant=2 (derived:is_micro_company) |
| run_004 | oqt=0,ant=0 |
| run_005 | — |
| run_006 | — |
| run_007 | oqt=0,ant=0 (derived:acquires_usufruct) |
| run_008 | — |
| run_009 | oqt=0,ant=0 (derived:is_small_company) |
| run_101 | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) |
| run_102 | oqt=0,ant=0 |
| run_103 | oqt=0,ant=1 (derived:acquires_full_ownership_of) |
| run_104 | oqt=0,ant=0 (derived:obtains_usufruct) |
| run_105 | oqt=0,ant=0 (derived:preceding_provisions_do_not_apply) |
| run_106 | oqt=0,ant=0 (derived:acquires_right_to_rent) |
| run_107 | oqt=0,ant=0 (derived:is_foreigner) |
| run_108 | — |
| run_109 | — |
| run_110 | — |
| run_111 | oqt=0,ant=2 (derived:has_risk_of_absconding) |
| run_112 | — |
| run_113 | oqt=0,ant=0 (derived:is_small_company) |
| run_114 | oqt=0,ant=0 (derived:is_small_company) |
| run_115 | oqt=0,ant=2 (derived:is_micro_company) |
| run_116 | oqt=0,ant=2 (derived:is_micro_company) |
| run_117 | — |
| run_118 | — |
| run_119 | oqt=0,ant=0 (derived:is_small_company) |
| run_120 | — |
| run_201 | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) |
| run_202 | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) |
| run_203 | — |
| run_204 | oqt=0,ant=0 (derived:is_illegal_stay) |
| run_205 | oqt=0,ant=2 (derived:is_micro_company) |
| run_206 | — |
| run_207 | oqt=0,ant=0 (derived:acquires_right_to_rent) |
| run_208 | oqt=0,ant=0 (derived:is_small_company) |

## Timing

- Elapsed: 2.02h (7288.69 s)
- Cells recorded: 37
- Avg per cell: 3.3m (196.95 s)

See `timings.csv` for per (run, strategy) durations.

## Details (JSON)

See `matrix.json`.

## Grouped metrics (manifest tiers)

Aggregated over matrix cells. ``strict_accuracy`` = decisive_correct / total_questions; ``decisive_precision`` = decisive_correct / decisive_answers; ``coverage`` = scored_cells / total_cells.

### By strategy

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| direct_json_ir_no_translate | 37 | 24 | 11 | 1 | 11 | 32% | 0.30 | 0.48 | 0.92 | 0.65 |

### By evaluation_group

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| challenge | 10 | 7 | 4 | 0 | 3 | 30% | 0.40 | 0.57 | 1.00 | 0.70 |
| core | 23 | 16 | 7 | 0 | 8 | 30% | 0.30 | 0.47 | 1.00 | 0.70 |
| stress | 4 | 1 | 0 | 1 | 0 | 50% | 0.00 | 0.00 | 0.00 | 0.25 |

### By difficulty

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| basic | 20 | 13 | 6 | 0 | 7 | 35% | 0.30 | 0.46 | 1.00 | 0.65 |
| hard | 4 | 1 | 0 | 1 | 0 | 50% | 0.00 | 0.00 | 0.00 | 0.25 |
| intermediate | 13 | 10 | 5 | 0 | 4 | 23% | 0.38 | 0.56 | 1.00 | 0.77 |

### By law_domain

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| company | 14 | 9 | 3 | 1 | 5 | 29% | 0.21 | 0.33 | 0.75 | 0.64 |
| immigration | 11 | 3 | 1 | 0 | 2 | 73% | 0.09 | 0.33 | 1.00 | 0.27 |
| inheritance | 12 | 12 | 7 | 0 | 4 | 0% | 0.58 | 0.64 | 1.00 | 1.00 |

### By phenomenon

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| case_given_criteria | 3 | 1 | 0 | 0 | 1 | 67% | 0.00 | 0.00 | — | 0.33 |
| classification | 12 | 9 | 4 | 0 | 5 | 25% | 0.33 | 0.44 | 1.00 | 0.75 |
| definition | 14 | 6 | 3 | 0 | 3 | 57% | 0.21 | 0.50 | 1.00 | 0.43 |
| legal_effect | 15 | 13 | 7 | 1 | 4 | 7% | 0.47 | 0.58 | 0.88 | 0.87 |
| negative_exclusion | 11 | 6 | 3 | 0 | 3 | 45% | 0.27 | 0.50 | 1.00 | 0.55 |
| numeric_threshold | 13 | 9 | 3 | 1 | 5 | 23% | 0.23 | 0.33 | 0.75 | 0.69 |
| structural_exclusion | 1 | 0 | 0 | 0 | 0 | 100% | 0.00 | — | — | 0.00 |
| temporal | 3 | 1 | 0 | 1 | 0 | 33% | 0.00 | 0.00 | 0.00 | 0.33 |

