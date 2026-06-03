# Non-boolean probe manual review

This is an exploratory run. Gold answers were not included in prompts and no automatic score was computed.

## nb_001 (legal_effect)

- Law source: `erfrecht_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `propagation` / `propagation`
- Output kind: `unknown`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_001`

**Question**

Welk erfrechtelijk recht verkrijgt Anna volgens artikel 4.17?

**Pipeline answer**

Symbolic reasoning error: explain target requires predicate and args

**Pipeline explanation**



**Gold answer for manual comparison**

Anna verkrijgt het vruchtgebruik van de gehele nalatenschap.

## nb_002 (legal_effect_list)

- Law source: `erfrecht_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `propagation` / `propagation`
- Output kind: `unknown`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_002`

**Question**

Welke rechten verkrijgt David volgens artikel 4.17, paragraaf 2?

**Pipeline answer**

Symbolic reasoning error: explain target requires predicate and args

**Pipeline explanation**



**Gold answer for manual comparison**

David verkrijgt de volle eigendom van Clara’s deel in het gemeenschappelijk vermogen en het vruchtgebruik van de overige goederen van Clara’s eigen vermogen.

## nb_003 (legal_effect)

- Law source: `erfrecht_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_003`

**Question**

Wat verkrijgt Felix volgens artikel 4.17?

**Pipeline answer**

Yes. Felix, Emma: The surviving spouse (first person) acquires full ownership of the entire estate of the deceased (second person).

**Pipeline explanation**



**Gold answer for manual comparison**

Felix verkrijgt de volle eigendom van de gehele nalatenschap.

## nb_004 (legal_effect_list)

- Law source: `erfrecht_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `propagation` / `propagation`
- Output kind: `unknown`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_004`

**Question**

Welke goederen vallen volgens artikel 4.23 onder het vruchtgebruik van Hana?

**Pipeline answer**

Symbolic reasoning error: explain target requires predicate and args

**Pipeline explanation**



**Gold answer for manual comparison**

Het vruchtgebruik heeft betrekking op het onroerend goed dat als voornaamste gezinswoning diende en op het daarin aanwezige huisraad.

## nb_005 (legal_effect)

- Law source: `erfrecht_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_005`

**Question**

Wie verkrijgt volgens artikel 4.20 het recht op de huur van de gezinswoning?

**Pipeline answer**

Yes. Jonas, Huurwoning: The person acquires the exclusive right to the lease of the property, to the exclusion of all other heirs, as the surviving spouse.

**Pipeline explanation**



**Gold answer for manual comparison**

De langstlevende echtgenoot Jonas verkrijgt als enige, met uitsluiting van alle andere erfgenamen, het recht op de huur.

## nb_006 (threshold_list)

- Law source: `microvennootschappen_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `relevance` / `relevance`
- Output kind: `unknown`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_006`

**Question**

Welke drie drempels gebruikt artikel 1:24 om te bepalen of een vennootschap een kleine vennootschap is?

**Pipeline answer**

Symbolic reasoning error: explain target requires predicate and args

**Pipeline explanation**



**Gold answer for manual comparison**

Jaargemiddelde werknemers: 50; jaarlijkse netto-omzet exclusief btw: 11.250.000 euro; balanstotaal: 6.000.000 euro.

## nb_007 (classification)

- Law source: `microvennootschappen_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `propagation` / `propagation`
- Output kind: `unknown`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_007`

**Question**

Welke vennootschapsclassificatie volgt voor BV Beta volgens artikel 1:25?

**Pipeline answer**

Symbolic reasoning error: explain target requires predicate and args

**Pipeline explanation**



**Gold answer for manual comparison**

BV Beta kwalificeert als microvennootschap.

## nb_008 (period)

- Law source: `microvennootschappen_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `propagation` / `propagation`
- Output kind: `unknown`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_008`

**Question**

Vanaf welk boekjaar moet volgens artikel 1:24, paragraaf 3 met deze overschrijding rekening worden gehouden?

**Pipeline answer**

Symbolic reasoning error: explain target requires predicate and args

**Pipeline explanation**



**Gold answer for manual comparison**

Er moet meteen rekening mee worden gehouden voor het eerste boekjaar, dus boekjaar 2026.

## nb_009 (numeric_amount)

- Law source: `microvennootschappen_clean.txt`
- Pipeline status: `no_results_json`
- Query type / intent: `None` / `None`
- Output kind: `None`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_009`

**Question**

Wat is volgens artikel 1:24, paragraaf 4 de aangepaste omzetdrempel voor dit boekjaar?

**Pipeline answer**



**Pipeline explanation**



**Gold answer for manual comparison**

16.875.000 euro, namelijk 11.250.000 × 18/12.

## nb_010 (period)

- Law source: `microvennootschappen_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_010`

**Question**

Vanaf welk boekjaar treden volgens artikel 1:24, paragraaf 2 de gevolgen in?

**Pipeline answer**

Yes. Nv_epsilon, Fy_2026: The company loses kleine vennootschap status starting from this financial year due to exceeding more than one criterion for two consecutive years.

**Pipeline explanation**



**Gold answer for manual comparison**

Vanaf boekjaar 2026, het boekjaar dat volgt op het boekjaar waarin de criteria voor de tweede keer werden overschreden.

## nb_011 (calculation_rule)

- Law source: `microvennootschappen_clean.txt`
- Pipeline status: `no_results_json`
- Query type / intent: `None` / `None`
- Output kind: `None`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_011`

**Question**

Hoe worden volgens artikel 1:24, paragraaf 6 de criteria netto-omzet, balanstotaal en werknemers berekend bij verbonden vennootschappen?

**Pipeline answer**



**Pipeline explanation**



**Gold answer for manual comparison**

Netto-omzet en balanstotaal worden op geconsolideerde basis berekend; het aantal werknemers wordt opgeteld over de betrokken verbonden vennootschappen.

## nb_012 (threshold_list)

- Law source: `microvennootschappen_clean.txt`
- Pipeline status: `no_results_json`
- Query type / intent: `None` / `None`
- Output kind: `None`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_012`

**Question**

Welke drie drempels vermeldt artikel 1:25 voor microvennootschappen?

**Pipeline answer**



**Pipeline explanation**



**Gold answer for manual comparison**

Jaargemiddelde werknemers: 10; jaarlijkse netto-omzet exclusief btw: 900.000 euro; balanstotaal: 450.000 euro.

## nb_013 (definition)

- Law source: `vreemdelingenwet_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_013`

**Question**

Onder welke wettelijke categorie valt Samir volgens artikel 1, paragraaf 1, punt 1?

**Pipeline answer**

Yes. Samir: The person is a foreigner: they cannot prove they hold Belgian nationality.

**Pipeline explanation**



**Gold answer for manual comparison**

Samir valt onder de categorie vreemdeling.

## nb_014 (definition_conditions)

- Law source: `vreemdelingenwet_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `explain` / `explain`
- Output kind: `explanation`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_014`

**Question**

Onder welke wettelijke categorie valt Mila volgens artikel 1, paragraaf 1, punt 3, en waarom?

**Pipeline answer**

Target atom is_third_country_national(mila) is entailed. Detailed proof explanation is limited in this environment.

**Pipeline explanation**

{'intent': 'explain', 'answer': 'Target atom is_third_country_national(mila) is entailed. Detailed proof explanation is limited in this environment.', 'support': None, 'parsed': True, 'warnings': [], 'raw': {'intent': 'explain', 'status': 'ok', 'output_kind': 'explanation', 'target': {'type': 'predicate', 'predicate': 'is_third_country_national', 'args': ['mila']}, 'label': 'entailed', 'explanation': 'Target atom is_third_country_national(mila) is entailed. Detailed proof explanation is limited in this environment.', 'support': [], 'raw': {'atom': 'is_third_country_national(x0)', 'constraint': '? x0 in Person: __sel0(x0) & is_third_country_national(x0)', 'possible': True, 'certain': True}, 'predicate': 'is_third_country_national', 'args': ['mila'], 'possible': True, 'certain': True, 'certainty_class': 'manual', 'sat': True, 'internal_intent': 'explain', 'antecedent_coverage': [{'rule_index': 1, 'target': 'is_third_country_national(mila)', 'conditions': [{'atom': 'is_eu_citizen(mila)', 'status': 'present'}, {'atom': 'covered_by_eu_free_movement_law(mila)', 'status': 'present'}]}]}}

**Gold answer for manual comparison**

Mila is een onderdaan van een derde land, omdat zij geen burger van de Unie is en niet onder het gemeenschapsrecht inzake vrij verkeer valt.

## nb_015 (classification)

- Law source: `vreemdelingenwet_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_015`

**Question**

Welke verblijfsstatus volgt volgens artikel 1, paragraaf 1, punt 4?

**Pipeline answer**

Cannot determine with certainty. risk_of_absconding(nora) is not logically forced either way (label: unknown).

**Pipeline explanation**



**Gold answer for manual comparison**

Nora bevindt zich in illegaal verblijf.

## nb_016 (condition_list)

- Law source: `vreemdelingenwet_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `explain` / `explain`
- Output kind: `explanation`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_016`

**Question**

Welke algemene vereisten stelt artikel 1, paragraaf 2 voor het vaststellen van risico op onderduiken?

**Pipeline answer**

Target atom risk_of_absconding(omar) is unknown. Detailed proof explanation is limited in this environment.

**Pipeline explanation**

{'intent': 'explain', 'answer': 'Target atom risk_of_absconding(omar) is unknown. Detailed proof explanation is limited in this environment.', 'support': None, 'parsed': True, 'warnings': [], 'raw': {'intent': 'explain', 'status': 'ok', 'output_kind': 'explanation', 'target': {'type': 'predicate', 'predicate': 'risk_of_absconding', 'args': ['omar']}, 'label': 'unknown', 'explanation': 'Target atom risk_of_absconding(omar) is unknown. Detailed proof explanation is limited in this environment.', 'support': [], 'raw': {'atom': 'risk_of_absconding(x0)', 'constraint': '? x0 in Person: __sel0(x0) & risk_of_absconding(x0)', 'possible': True, 'certain': False}, 'predicate': 'risk_of_absconding', 'args': ['omar'], 'possible': True, 'certain': False, 'certainty_class': 'manual', 'sat': True, 'internal_intent': 'explain', 'antecedent_coverage': [{'rule_index': 18, 'target': 'risk_of_absconding(omar)', 'conditions': [{'atom': 'risk_of_absconding_current_and_real(omar)', 'status': 'helper_defined'}]}]}}

**Gold answer for manual comparison**

Het risico moet actueel en reëel zijn, worden vastgesteld na een individueel onderzoek, gebaseerd zijn op één of meer objectieve criteria, en rekening houden met alle omstandigheden eigen aan het geval.

## nb_017 (classification)

- Law source: `vreemdelingenwet_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_017`

**Question**

Welke categorie uit artikel 1, paragraaf 1, punt 14 is op Pavel van toepassing?

**Pipeline answer**

Cannot determine with certainty. risk_of_absconding(pavel) is not logically forced either way (label: unknown).

**Pipeline explanation**



**Gold answer for manual comparison**

Pavel is een geïdentificeerde vreemdeling.

## nb_018 (objective_criterion)

- Law source: `vreemdelingenwet_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_018`

**Question**

Welk objectief criterium voor risico op onderduiken is volgens artikel 1, paragraaf 2 aanwezig?

**Pipeline answer**

Cannot determine with certainty. risk_of_absconding(rina) is not logically forced either way (label: unknown).

**Pipeline explanation**



**Gold answer for manual comparison**

Het criterium dat de betrokkene na illegale binnenkomst of tijdens illegaal verblijf geen verblijfsaanvraag heeft ingediend.

## nb_019 (classification)

- Law source: `vreemdelingenwet_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_019`

**Question**

Welke juridische vaststelling volgt volgens artikel 1, paragraaf 2?

**Pipeline answer**

Yes. Tomas: There is a current and real risk that the person will abscond, established after individual examination on the basis of one or more objective criteria.

**Pipeline explanation**



**Gold answer for manual comparison**

Er kan een risico op onderduiken worden vastgesteld.

## nb_020 (definition)

- Law source: `vreemdelingenwet_clean.txt`
- Pipeline status: `ok`
- Query type / intent: `predicate_boolean` / `deduction`
- Output kind: `epistemic_boolean`
- Work dir: `C:\Users\bramd\Documents\VUB\Master Thesis\Legal-pipeline\results\final\explain_questions\work\nb_020`

**Question**

Hoe definieert artikel 1, paragraaf 1, punt 4 de situatie van Yara?

**Pipeline answer**

Cannot determine with certainty. risk_of_absconding(yara) is not logically forced either way (label: unknown).

**Pipeline explanation**



**Gold answer for manual comparison**

Haar situatie is illegaal verblijf: aanwezigheid op het grondgebied van een vreemdeling die niet of niet langer voldoet aan de voorwaarden voor toegang tot of verblijf.
