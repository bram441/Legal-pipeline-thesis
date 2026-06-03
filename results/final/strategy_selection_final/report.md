# Evaluation report

- Generated: 20260527T212415Z
- Runs directory: C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\inputs\json_final_clean

## Pipeline status summary

- Cells total: 148
- **Scored cells** (valid ``score.json`` with ``total``): 119
- **evaluation_no_score** (exit 0, no score): 0
- **evaluation_bad_score**: 0
- **law_compilation** failures: 10
- Other failures: 19
- Accuracy (decisive, **scored cells only**): 0.9844

Unscored cells are **not** successful pipeline completions; they are evaluation failures.

## Accuracy (decisive: correct / total; inconclusive counts as not correct)

Only **scored** cells show accuracy. Others show ``FAIL`` or status label.

| Run | direct_json_ir_translate | direct_json_ir_no_translate | le_json_ir_translate | le_json_ir_no_translate |
|---|---|---|---|---|
| run_001 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | law_compilation | 1.0000 (1/1, inc=0) |
| run_002 | 1.0000 (1/1, inc=0) | 0.0000 (0/1, inc=1) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_003 | 0.0000 (0/1, inc=1) | law_compilation | kb_idp_parse | kb_idp_parse |
| run_004 | completed_with_errors | completed_with_errors | completed_with_errors | completed_with_errors |
| run_005 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 0.0000 (0/1, inc=1) |
| run_006 | process_error | 1.0000 (1/1, inc=0) | law_compilation | kb_idp_parse |
| run_007 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_008 | 1.0000 (1/1, inc=0) | completed_with_errors | 0.0000 (0/1, inc=1) | law_compilation |
| run_009 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | kb_idp_parse |
| run_101 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_102 | completed_with_errors | completed_with_errors | completed_with_errors | completed_with_errors |
| run_103 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | law_compilation | law_compilation |
| run_104 | process_error | 1.0000 (1/1, inc=0) | process_error | 1.0000 (1/1, inc=0) |
| run_105 | 0.0000 (0/1, inc=1) | law_compilation | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) |
| run_106 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_107 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_108 | process_error | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) |
| run_109 | 0.0000 (0/1, inc=1) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | completed_with_errors |
| run_110 | 0.0000 (0/1, inc=1) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_111 | 1.0000 (1/1, inc=0) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) |
| run_112 | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) |
| run_113 | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | kb_idp_parse |
| run_114 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_115 | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | kb_idp_parse |
| run_116 | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | kb_idp_parse |
| run_117 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | kb_idp_parse |
| run_118 | law_compilation | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 0.0000 (0/1, inc=1) |
| run_119 | 1.0000 (1/1, inc=0) | 0.0000 (0/1, inc=1) | kb_idp_parse | kb_idp_parse |
| run_120 | process_error | 1.0000 (1/1, inc=0) | kb_idp_parse | kb_idp_parse |
| run_201 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_202 | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) |
| run_203 | process_error | 0.0000 (0/1, inc=1) | law_compilation | 0.0000 (0/1, inc=1) |
| run_204 | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=0) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) |
| run_205 | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) | 0.0000 (0/1, inc=1) |
| run_206 | 0.0000 (0/1, inc=1) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) |
| run_207 | 0.0000 (0/1, inc=1) | 1.0000 (1/1, inc=0) | law_compilation | 1.0000 (1/1, inc=0) |
| run_208 | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | 1.0000 (1/1, inc=0) | kb_idp_parse |

## Strategy configuration

JSON_IR backend always compiles via ``symbols_then_rules`` (symbols then rules).

| Strategy | Canonical | LE | Config trans | Effective trans | Source | JSON IR | Depr |
|---|:---|:---:|:---:|:---:|:---|:---|:---:|
| direct_json_ir_translate | direct_json_ir_translate | no | yes | yes | strategy | symbols_then_rules | no |
| direct_json_ir_no_translate | direct_json_ir_no_translate | no | no | no | strategy | symbols_then_rules | no |
| le_json_ir_translate | le_json_ir_translate | yes | yes | yes | strategy | symbols_then_rules | no |
| le_json_ir_no_translate | le_json_ir_no_translate | yes | no | no | strategy | symbols_then_rules | no |

## Failure / status category

Heuristic label from `run_trace.txt` / `kb_compile.log` (see `eval_support.classify_failure`).

| Run | direct_json_ir_translate | direct_json_ir_no_translate | le_json_ir_translate | le_json_ir_no_translate |
|---|---|---|---|---|
| run_001 | completed | completed | law_compilation | completed |
| run_002 | completed | completed | completed | completed |
| run_003 | completed | law_compilation | kb_idp_parse | kb_idp_parse |
| run_004 | completed_with_errors | completed_with_errors | completed_with_errors | completed_with_errors |
| run_005 | completed | completed | completed | completed |
| run_006 | process_error | completed | law_compilation | kb_idp_parse |
| run_007 | completed | completed | completed | completed |
| run_008 | completed | completed_with_errors | completed | law_compilation |
| run_009 | completed | completed | completed | kb_idp_parse |
| run_101 | completed | completed | completed | completed |
| run_102 | completed_with_errors | completed_with_errors | completed_with_errors | completed_with_errors |
| run_103 | completed | completed | law_compilation | law_compilation |
| run_104 | process_error | completed | process_error | completed |
| run_105 | completed | law_compilation | completed | completed |
| run_106 | completed | completed | completed | completed |
| run_107 | completed | completed | completed | completed |
| run_108 | process_error | completed | completed | completed |
| run_109 | completed | completed | completed | completed_with_errors |
| run_110 | completed | completed | completed | completed |
| run_111 | completed | completed | completed | completed |
| run_112 | completed | completed | completed | completed |
| run_113 | completed | completed | completed | kb_idp_parse |
| run_114 | completed | completed | completed | completed |
| run_115 | completed | completed | completed | kb_idp_parse |
| run_116 | completed | completed | completed | kb_idp_parse |
| run_117 | completed | completed | completed | kb_idp_parse |
| run_118 | law_compilation | completed | completed | completed |
| run_119 | completed | completed | kb_idp_parse | kb_idp_parse |
| run_120 | process_error | completed | kb_idp_parse | kb_idp_parse |
| run_201 | completed | completed | completed | completed |
| run_202 | completed | completed | completed | completed |
| run_203 | process_error | completed | law_compilation | completed |
| run_204 | completed | completed | completed | completed |
| run_205 | completed | completed | completed | completed |
| run_206 | completed | completed | completed | completed |
| run_207 | completed | completed | law_compilation | completed |
| run_208 | completed | completed | completed | kb_idp_parse |

## Query target diagnostics

Per-question query predicate and kind from `score.json` items. ``observable_query_target_warning_count`` / ``antecedent_diagnostic_warning_count`` split score warnings.

| Run | direct_json_ir_translate | direct_json_ir_no_translate | le_json_ir_translate | le_json_ir_no_translate |
|---|---|---|---|---|
| run_001 | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) | — | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) |
| run_002 | oqt=0,ant=0 (derived:is_alien) | oqt=0,ant=2 (derived:risk_of_absconding) | oqt=0,ant=0 (derived:is_alien) | oqt=0,ant=0 (derived:is_foreigner) |
| run_003 | oqt=0,ant=2 (derived:is_micro_company) | — | — | — |
| run_004 | oqt=0,ant=0 | oqt=0,ant=0 | oqt=0,ant=0 | oqt=0,ant=0 |
| run_005 | oqt=0,ant=0 (derived:is_in_illegal_stay) | oqt=0,ant=1 (derived:is_third_country_national) | oqt=0,ant=0 (derived:has_illegal_stay) | oqt=0,ant=0 (derived:is_in_illegal_residence) |
| run_006 | — | oqt=0,ant=0 (derived:loses_kleine_vennootschap_status_from) | — | — |
| run_007 | oqt=0,ant=0 (derived:acquires_usufruct_of) | oqt=0,ant=0 (derived:acquires_usufruct_of_main_residence) | oqt=0,ant=0 (derived:acquires_usufruct_of_principal_residence) | oqt=0,ant=0 (derived:acquires_usufruct_of_residence) |
| run_008 | oqt=0,ant=1 (derived:risk_of_absconding) | oqt=0,ant=0 | oqt=0,ant=2 (derived:risk_of_absconding) | — |
| run_009 | oqt=0,ant=0 (derived:is_small_company) | oqt=0,ant=0 (derived:is_kleine_vennootschap) | oqt=0,ant=0 (derived:is_small_company) | — |
| run_101 | oqt=0,ant=0 (derived:acquires_usufruct_of_estate) | oqt=0,ant=0 (derived:receives_usufruct_of_entire_estate) | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) |
| run_102 | oqt=0,ant=0 | oqt=0,ant=0 | oqt=0,ant=0 | oqt=0,ant=0 |
| run_103 | oqt=0,ant=0 (derived:acquires_full_ownership_of_entire_estate) | oqt=0,ant=0 (derived:acquires_full_ownership_of_entire_estate) | — | — |
| run_104 | — | oqt=0,ant=0 (derived:acquires_usufruct_of) | — | oqt=0,ant=0 (derived:acquires_usufruct_of_immovable_property) |
| run_105 | oqt=0,ant=0 (derived:exception_applies_surviving_partner_is_descendant) | — | oqt=0,ant=0 (derived:exclusion_from_foregoing_provisions_applies) | oqt=0,ant=0 (derived:exception_applies_surviving_cohabitant_is_descendant) |
| run_106 | oqt=0,ant=0 (derived:acquires_right_to_lease) | oqt=0,ant=0 (derived:acquires_right_to_lease) | oqt=0,ant=0 (derived:acquires_right_to_lease) | oqt=0,ant=0 (derived:acquires_right_to_lease) |
| run_107 | oqt=0,ant=0 (derived:is_alien) | oqt=0,ant=0 (derived:is_foreigner) | oqt=0,ant=0 (derived:is_alien) | oqt=0,ant=0 (derived:is_foreigner) |
| run_108 | — | oqt=0,ant=0 (derived:is_foreigner) | oqt=0,ant=0 (derived:is_alien) | oqt=0,ant=0 (derived:is_foreigner) |
| run_109 | oqt=0,ant=0 (derived:is_in_illegal_stay) | oqt=0,ant=1 (derived:is_third_country_national) | oqt=0,ant=0 (derived:has_illegal_residence) | oqt=0,ant=0 |
| run_110 | oqt=0,ant=0 (derived:is_third_country_national) | oqt=0,ant=0 (derived:is_third_country_national) | oqt=0,ant=0 (derived:is_third_country_national) | oqt=0,ant=0 (derived:is_third_country_national) |
| run_111 | oqt=0,ant=1 (derived:risk_of_absconding) | oqt=0,ant=2 (derived:risk_of_absconding) | oqt=0,ant=2 (derived:risk_of_absconding) | oqt=0,ant=2 (derived:risk_of_absconding_exists) |
| run_112 | oqt=0,ant=2 (derived:risk_of_absconding) | oqt=0,ant=2 (derived:risk_of_absconding) | oqt=0,ant=2 (derived:risk_of_absconding) | oqt=0,ant=2 (derived:risk_of_absconding) |
| run_113 | oqt=0,ant=0 (derived:is_small_company) | oqt=0,ant=0 (derived:is_kleine_vennootschap) | oqt=0,ant=0 (derived:is_small_company) | — |
| run_114 | oqt=0,ant=0 (derived:is_small_company) | oqt=0,ant=0 (derived:is_kleine_vennootschap) | oqt=0,ant=0 (derived:is_small_company) | oqt=0,ant=0 (derived:is_small_company) |
| run_115 | oqt=0,ant=2 (derived:is_micro_company) | oqt=0,ant=2 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) | — |
| run_116 | oqt=0,ant=2 (derived:is_micro_company) | oqt=0,ant=2 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) | — |
| run_117 | oqt=0,ant=0 (derived:is_micro_company) | oqt=0,ant=1 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) | — |
| run_118 | — | oqt=0,ant=1 (derived:is_micro_company) | oqt=0,ant=1 (derived:is_micro_company) | oqt=0,ant=2 (derived:is_micro_company) |
| run_119 | oqt=0,ant=0 (derived:more_than_one_criterion_exceeded) | oqt=0,ant=2 (derived:is_small_company) | — | — |
| run_120 | — | oqt=0,ant=0 (derived:loses_kleine_vennootschap_status_from) | — | — |
| run_201 | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) | oqt=0,ant=0 (derived:receives_usufruct_of_entire_estate) | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) |
| run_202 | oqt=0,ant=0 (derived:acquires_usufruct_of_entire_estate) | oqt=0,ant=2 (derived:acquires_usufruct_of_entire_estate) | oqt=0,ant=2 (derived:acquires_usufruct_of_entire_estate) | oqt=0,ant=2 (derived:acquires_usufruct_of_entire_estate) |
| run_203 | — | oqt=0,ant=0 (derived:is_foreigner) | — | oqt=0,ant=0 (derived:is_foreigner) |
| run_204 | oqt=0,ant=0 (derived:is_in_illegal_stay) | oqt=0,ant=1 (derived:is_third_country_national) | oqt=0,ant=0 (derived:has_illegal_stay) | oqt=0,ant=0 (derived:is_in_illegal_residence) |
| run_205 | oqt=0,ant=0 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) |
| run_206 | oqt=0,ant=2 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) | oqt=0,ant=0 (derived:is_micro_company) |
| run_207 | oqt=0,ant=2 (derived:acquires_right_to_lease) | oqt=0,ant=0 (derived:acquires_right_to_lease) | — | oqt=0,ant=0 (derived:is_sole_beneficiary_of_lease_right) |
| run_208 | oqt=0,ant=0 (derived:is_small_company) | oqt=0,ant=0 (derived:is_kleine_vennootschap) | oqt=0,ant=0 (derived:is_small_company) | — |

## Timing

- Elapsed: 3.54h (12737.15 s)
- Cells recorded: 148
- Avg per cell: 1.4m (85.99 s)

See `timings.csv` for per (run, strategy) durations.

## Details (JSON)

See `matrix.json`.

## Grouped metrics (manifest tiers)

Aggregated over matrix cells. ``strict_accuracy`` = decisive_correct / total_questions; ``decisive_precision`` = decisive_correct / decisive_answers; ``coverage`` = scored_cells / total_cells.

### By strategy

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| direct_json_ir_translate | 37 | 31 | 16 | 0 | 13 | 3% | 0.43 | 0.55 | 1.00 | 0.84 |
| direct_json_ir_no_translate | 37 | 35 | 20 | 1 | 11 | 5% | 0.54 | 0.62 | 0.95 | 0.95 |
| le_json_ir_translate | 37 | 28 | 15 | 0 | 11 | 14% | 0.41 | 0.58 | 1.00 | 0.76 |
| le_json_ir_no_translate | 37 | 25 | 12 | 0 | 10 | 5% | 0.32 | 0.55 | 1.00 | 0.68 |

### By evaluation_group

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| challenge | 40 | 32 | 20 | 0 | 11 | 12% | 0.50 | 0.65 | 1.00 | 0.80 |
| core | 92 | 79 | 40 | 1 | 29 | 4% | 0.43 | 0.57 | 0.98 | 0.86 |
| stress | 16 | 8 | 3 | 0 | 5 | 6% | 0.19 | 0.38 | 1.00 | 0.50 |

### By difficulty

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| basic | 80 | 69 | 38 | 1 | 29 | 5% | 0.47 | 0.56 | 0.97 | 0.86 |
| hard | 16 | 8 | 3 | 0 | 5 | 6% | 0.19 | 0.38 | 1.00 | 0.50 |
| intermediate | 52 | 42 | 22 | 0 | 11 | 10% | 0.42 | 0.67 | 1.00 | 0.81 |

### By law_domain

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| company | 56 | 38 | 21 | 0 | 17 | 5% | 0.38 | 0.55 | 1.00 | 0.68 |
| immigration | 44 | 40 | 17 | 1 | 20 | 5% | 0.39 | 0.45 | 0.94 | 0.91 |
| inheritance | 48 | 41 | 25 | 0 | 8 | 10% | 0.52 | 0.76 | 1.00 | 0.85 |

### By phenomenon

| Group | cells | scored | dec.ok | dec.wrong | inconcl. | compile% | strict_acc | scored_acc | dec.prec | coverage |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| case_given_criteria | 12 | 11 | 2 | 0 | 8 | 8% | 0.17 | 0.20 | 1.00 | 0.92 |
| classification | 48 | 36 | 20 | 0 | 16 | 8% | 0.42 | 0.56 | 1.00 | 0.75 |
| definition | 56 | 49 | 26 | 1 | 20 | 5% | 0.46 | 0.55 | 0.96 | 0.88 |
| legal_effect | 60 | 45 | 28 | 0 | 9 | 10% | 0.47 | 0.76 | 1.00 | 0.75 |
| negative_exclusion | 44 | 37 | 16 | 1 | 20 | 5% | 0.36 | 0.43 | 0.94 | 0.84 |
| numeric_threshold | 52 | 35 | 19 | 0 | 16 | 4% | 0.37 | 0.54 | 1.00 | 0.67 |
| structural_exclusion | 4 | 3 | 2 | 0 | 1 | 25% | 0.50 | 0.67 | 1.00 | 0.75 |
| temporal | 12 | 4 | 3 | 0 | 1 | 8% | 0.25 | 0.75 | 1.00 | 0.33 |

