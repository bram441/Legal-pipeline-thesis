# VERUS-LM evaluation report

Provider: `openrouter`  
Model: `anthropic/claude-sonnet-4.6`  
VERUS version mode: `llm`

## Summary

- total runs/questions: 37 / 37
- scored: 31
- correct decisive: 20
- wrong decisive: 5
- inconclusive/unknown: 6
- law compilation / KB generation failures: 0
- parsing failures: 0
- symbolic execution failures: 6
- strict accuracy: 0.5405
- coverage: 0.8378
- decisive precision: 0.8000
- decisive wrong rate: 0.1351

## Fairness notes

- The adapter preserves the same law text, case text, question text, expected answer, and metadata from the JSON run files.
- Failures during KB generation or symbolic execution are not converted into `False`; they are reported as failure categories.
- The report records provider/model so differences with the JSON_IR-pipeline can be made explicit.
