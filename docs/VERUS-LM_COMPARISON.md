# VERUS-LM vs Legal-Pipeline: In-Depth Comparison

This document compares the [VERUS-LM pipeline](https://gitlab.com/EAVISE/bca/verus-lm) (EAVISE/BCA) with this Legal-Pipeline project, and recommends improvements inspired by VERUS-LM.

---

## 1. Architecture Overview

### VERUS-LM
- **Purpose**: General logical reasoning benchmarks (PrOntoQA, ProofWriter, FOLIO, AR-LSAT, DivLR)
- **Flow**: Problem → Symbol extraction → Constraint extraction → Reasoning
- **KB Creation**: Two-phase (domain symbols first, then constraints)
- **Repair**: Separate prompts for syntax errors vs. unsatisfiability

### Legal-Pipeline
- **Purpose**: Legal reasoning (law articles → liability, sentencing)
- **Flow**: Law text → KB (FO) → Case extraction → Query extraction → IDP reasoning
- **KB Creation**: Configurable — direct single-shot, direct two-phase, LE→FO single-shot, or LE→two-phase (see README env table)
- **Repair**: Syntax vs UNSAT repair prompts plus structured UNSAT explanation when available

---

## 2. KB Creation & Repair

### VERUS-LM: Two-Phase Extraction

| Phase | Prompt | Output | Correction |
|-------|--------|--------|------------|
| 1 | `1_symbol_extraction.txt` | Types, predicates, functions | `3a_correct_symbols.txt` (up to 8 attempts) |
| 2 | `2_constraint_extraction.txt` | FOL constraints | `3c_correct_constraints.txt` (syntax) or `3b_correct_unsat.txt` (UNSAT) |

**Key insight**: Splitting domain and constraints reduces complexity per LLM call. Symbols are validated before constraints are even extracted.

### Legal-Pipeline: Single-Phase

- One shot: `kb_compilation.txt` or `law_to_le.txt` + `le_to_fo.txt`
- One repair: `kb_compilation_repair.txt` for any error

---

## 3. Semantic Check & UNSAT Feedback

### VERUS-LM: IDP Theory.propagate() + Theory.explain()

```python
# From verus_lm/utils/kb_creation_utils.py
idp = IDP.from_str(idp_file)
T_block, S_block = idp.get_blocks("T, S")
theory = Theory(T_block, S_block)
theory.propagate()
if not theory.satisfied:
    explanation = explain_unsat_theory(theory, nl=False)
    return {"sat": False, "explanation": explanation}

# From verus_lm/inferences/explain.py
def explain_unsat_theory(theory: Theory, nl=True):
    (facts, formulas) = theory.explain()
    formulas = [x.code for x in formulas]
    explanation = "It is not satisfiable due to the following assignments:\n"
    explanation += "\n".join(str(f) for f in facts)
    explanation += "\nin combination with the following formulas:\n"
    explanation += "\n".join(str(formula) for formula in formulas)
    return explanation
```

**Critical difference**: VERUS-LM gets **structured conflict information** from IDP:
- Which facts/assignments conflict
- Which formulas participate in the inconsistency

This is passed to `3b_correct_unsat.txt` so the LLM sees *exactly* which rules conflict.

### Legal-Pipeline: model_check() Only

```python
# pipeline/kb/semantic_check.py
result = run_idp(fo_code, max_models=1)
if not result.get("sat", True):
    raise KBSemanticError(
        "KB theory is unsatisfiable: no model exists. "
        "Common cause: article predicates defined in terms of each other..."
    )
```

We only know "unsat" — no explanation of which rules conflict. The repair prompt receives a generic message.

---

## 4. Syntax Error Handling

### VERUS-LM: Parsed Error Messages

```python
# From kb_creation_utils.py parse_error_message()
match = re.search(r"line (\d+)|None:(\d+)", error)
if match:
    line_number = int(match.group(1))
    lines = idp_file.split("\n")
    lines.insert(line_number - 1, "// The error occured in the line(s) below")
    idp_file = "\n".join(lines)
```

They inject `// The error occurred in the line(s) below` at the problematic line, helping the LLM focus.

### Legal-Pipeline
- Passes raw exception string to repair
- No line-number annotation in the previous output

---

## 5. Repair Prompts

### VERUS-LM: Separate Prompts for UNSAT vs Syntax

| Error Type | Prompt | Content |
|------------|--------|---------|
| Syntax | `3c_correct_constraints.txt` | FOL grammar, examples of typical syntax fixes |
| UNSAT | `3b_correct_unsat.txt` | "Think why cyclic behaviour arises", correction options (change types to predicates, rewrite constraints), **receives the actual conflicting rules** |

`3b_correct_unsat.txt` includes examples like:
```
>>> Unsatisfiable explanation:
The following rules led to an inconsistency:
bmi() ≥ 40 ⇒ overweight().
bmi() ≤ 40 ⇒ not(overweight()).
>>> Corrected Program:
bmi() > 40 ⇒ overweight().  // Rewritten "≥ 40" to "> 40"
bmi() ≤ 40 ⇒ ¬overweight().
```

### Legal-Pipeline
- Single `kb_compilation_repair.txt` for both
- Generic "unsatisfiable" guidance
- No structured UNSAT explanation passed in

---

## 6. Extraction & Feedback (Case/Query)

VERUS-LM focuses on KB creation; it does not have a case/query extraction layer like ours. Our extraction uses schema-aware feedback loops (separate for case and query), which is already a strength.

---

## 7. Recommended Improvements

### High impact

1. **Use IDP Theory.propagate() and Theory.explain() for UNSAT**
   - When semantic check fails with UNSAT, try to obtain the structured explanation
   - Pass conflicting facts + formulas to a dedicated UNSAT repair prompt
   - Requires checking if our `idp_engine` exposes `Theory`, `get_blocks`, `propagate`, `explain`

2. **Split repair: syntax vs. UNSAT**
   - Add `kb_compilation_repair_unsat.txt` when error is semantic/UNSAT
   - Keep `kb_compilation_repair.txt` for syntax/parse errors

### Medium impact

3. **Error line annotation**
   - Parse IDP error messages for line numbers
   - Insert `// Error at line(s) below` in the previous output before sending to repair

4. **Stronger 3b-style UNSAT examples**
   - Add examples to the UNSAT repair prompt showing cyclic definitions and overlapping conditions (e.g. `≥` vs `>`)

### Lower priority / future

5. **Two-phase KB creation** (domain then constraints)
   - **Implemented:** `PIPELINE_KB_TWO_PHASE=1` — vocabulary then theory, with IDP parse checks. With `PIPELINE_USE_LE=0`: prompts `prompts/kb/kb_*_only.txt`, fallback `kb_compilation.txt`. With `PIPELINE_USE_LE=1`: law → LE first, then `prompts/le/le_*_only.txt` on the LE text, fallback `le_to_fo.txt`. Four combinations allow A/B comparison of compilation strategies.

---

## 8. Summary Table

| Aspect | VERUS-LM | Legal-Pipeline | Recommendation |
|--------|----------|----------------|----------------|
| KB extraction | Two-phase (symbols, then constraints) | Single-phase | Consider two-phase later |
| UNSAT detection | Theory.propagate() + explain() | model_check() only | Use explain() when available |
| UNSAT repair | Dedicated prompt + conflicting rules | Generic message | Add UNSAT-specific prompt |
| Syntax repair | Dedicated prompt | Single repair prompt | Keep; add line annotation |
| Error focus | Injects "error at line" | Raw error only | Add line annotation |
