# Curated JSON_IR legal test set

This pack contains only `inputs/json/run_XXX/run.json` files. The pipeline should generate all other artifacts itself. Copy or merge the `inputs/json` folder into the project root.

All runs are configured for `kb_compile_backend: json_ir` and `pipeline_backend_mode: json_ir`.

The first pass is intentionally mostly Boolean legal-conclusion testing, because it is the cleanest way to test JSON_IR KB generation plus case/query grounding before adding range, explanation, or set-valued tests.

## Runs and expected-value rationale

### run_101
- Law: `example_laws/erfrecht.text`
- Expected: `true`
- Question: Heeft Anna als langstlevende echtgenoot recht op het vruchtgebruik van de gehele nalatenschap volgens artikel 4.17, paragraaf 1?
- Reason: Art. 4.17 par. 1: if the deceased leaves descendants, the surviving spouse obtains usufruct of the whole estate.

### run_102
- Law: `example_laws/erfrecht.text`
- Expected: `true`
- Question: Verkrijgt Dirk volgens artikel 4.17, paragraaf 2 het vruchtgebruik van de overige goederen van Carla's eigen vermogen?
- Reason: Art. 4.17 par. 2: with ascendants or close collateral relatives, the surviving spouse gets usufruct of the remaining goods of the deceased's own property.

### run_103
- Law: `example_laws/erfrecht.text`
- Expected: `true`
- Question: Verkrijgt Filip volgens artikel 4.17, paragraaf 3 de volle eigendom van de gehele nalatenschap?
- Reason: Art. 4.17 par. 3: if the deceased leaves other heirs or no heirs, the surviving spouse obtains full ownership of the whole estate.

### run_104
- Law: `example_laws/erfrecht.text`
- Expected: `true`
- Question: Heeft Hannah volgens artikel 4.23, paragraaf 1 het vruchtgebruik van de gezinswoning en het daarin aanwezige huisraad?
- Reason: Art. 4.23 par. 1: the surviving legal cohabitant receives usufruct of the family home and household goods, regardless of the other heirs.

### run_105
- Law: `example_laws/erfrecht.text`
- Expected: `false`
- Question: Is artikel 4.23, paragraaf 4 een reden om Karin het vruchtgebruik van de gezinswoning te weigeren?
- Reason: Art. 4.23 par. 4 excludes the right only when the surviving legal cohabitant is a descendant of the predeceased cohabitant. The case states Karin is not a descendant of Joris, so that exclusion does not apply.

### run_106
- Law: `example_laws/erfrecht.text`
- Expected: `true`
- Question: Verkrijgt Lotte volgens artikel 4.20 als enige het recht op de huur van de gezinswoning?
- Reason: Art. 4.20: the surviving spouse exclusively obtains the rental right of the real estate that served as the family home.

### run_107
- Law: `example_laws/vreemdelingenwet.txt`
- Expected: `true`
- Question: Valt Ahmed onder de definitie van een vreemdeling in artikel 1, paragraaf 1, punt 1?
- Reason: A foreigner is anyone who does not provide proof of Belgian nationality.

### run_108
- Law: `example_laws/vreemdelingenwet.txt`
- Expected: `false`
- Question: Valt Sofie onder de definitie van een vreemdeling in artikel 1, paragraaf 1, punt 1?
- Reason: If the person proves Belgian nationality, the statutory definition of foreigner is not met.

### run_109
- Law: `example_laws/vreemdelingenwet.txt`
- Expected: `true`
- Question: Is er sprake van illegaal verblijf in de zin van artikel 1, paragraaf 1, punt 4?
- Reason: Illegal stay is the presence on the territory of a foreigner who does not or no longer meets the conditions for entry or stay.

### run_110
- Law: `example_laws/vreemdelingenwet.txt`
- Expected: `true`
- Question: Is Carlos een onderdaan van een derde land volgens artikel 1, paragraaf 1, punt 3?
- Reason: A third-country national is someone who is not a Union citizen and not covered by free movement law.

### run_111
- Law: `example_laws/vreemdelingenwet.txt`
- Expected: `true`
- Question: Kan dit een objectief criterium zijn voor risico op onderduiken volgens artikel 1, paragraaf 2, punt 2?
- Reason: Risk of absconding can be established using one or more objective criteria; use of false documents in a residence/removal procedure is listed as criterion 2.

### run_112
- Law: `example_laws/vreemdelingenwet.txt`
- Expected: `false`
- Question: Is er volgens artikel 1, paragraaf 1, punt 11 en paragraaf 2 een risico op onderduiken vastgesteld?
- Reason: The statutory risk requires a relevant procedure and an actual, real risk based on at least one listed objective criterion. The case states neither is present.

### run_113
- Law: `example_laws/microvennootschappen.txt`
- Expected: `true`
- Question: Is BV Orion een kleine vennootschap volgens artikel 1:24, paragraaf 1?
- Reason: The company has legal personality and exceeds none of the three small-company thresholds: 50 employees, 11,250,000 turnover, 6,000,000 balance sheet total.

### run_114
- Law: `example_laws/microvennootschappen.txt`
- Expected: `false`
- Question: Is NV Atlas nog een kleine vennootschap volgens artikel 1:24, paragraaf 1?
- Reason: Under Art. 1:24 par. 1, a small company may exceed no more than one of the three thresholds. Atlas exceeds two: employees > 50 and turnover > 11,250,000, so direct par. 1 classification is false.

### run_115
- Law: `example_laws/microvennootschappen.txt`
- Expected: `true`
- Question: Is NV Delta een microvennootschap volgens artikel 1:25, paragraaf 1?
- Reason: A micro-company must be small, have legal personality, not be parent/subsidiary, and exceed no more than one micro threshold. Delta exceeds none.

### run_116
- Law: `example_laws/microvennootschappen.txt`
- Expected: `true`
- Question: Is BV Nova een microvennootschap volgens artikel 1:25, paragraaf 1?
- Reason: Nova exceeds only one micro threshold, employees > 10. Article 1:25 allows not more than one exceeded criterion.

### run_117
- Law: `example_laws/microvennootschappen.txt`
- Expected: `false`
- Question: Is BV Sigma een microvennootschap volgens artikel 1:25, paragraaf 1?
- Reason: Sigma exceeds two micro thresholds: employees > 10 and turnover > 900,000. A micro-company may exceed no more than one.

### run_118
- Law: `example_laws/microvennootschappen.txt`
- Expected: `false`
- Question: Is BV ParentCo een microvennootschap volgens artikel 1:25, paragraaf 1?
- Reason: Even with low thresholds, Article 1:25 excludes parent companies and subsidiaries from micro-company status.

### run_119
- Law: `example_laws/microvennootschappen.txt`
- Expected: `true`
- Question: Moet BV Start volgens artikel 1:24, paragraaf 3 meteen rekening houden met het overschrijden van meer dan één criterium in het eerste boekjaar?
- Reason: For starting companies, if the good-faith estimate shows that more than one criterion will be exceeded in the first financial year, this must be taken into account immediately.

### run_120
- Law: `example_laws/microvennootschappen.txt`
- Expected: `true`
- Question: Gaan de gevolgen volgens artikel 1:24, paragraaf 2 in vanaf het boekjaar dat volgt op boekjaar 2025?
- Reason: When more than one criterion is exceeded for two consecutive financial years, the effects start in the financial year following the year in which the criteria were exceeded for the second time.

