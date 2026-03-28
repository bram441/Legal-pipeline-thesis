#!/usr/bin/env python
"""
Diagnose why a run produces "theory is unsatisfiable".
Run from project root: python scripts/diagnose_unsat.py inputs/json/run_003

Composes KB + case structure and uses IDP Theory.explain() to show which rules conflict.
"""
import json
import sys
from pathlib import Path

# Add project root
_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_root))

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_unsat.py <run_dir>")
        print("Example: python scripts/diagnose_unsat.py inputs/json/run_003")
        sys.exit(1)

    run_dir = Path(sys.argv[1])
    run_json = run_dir / "run.json"
    if not run_json.exists():
        print(f"Not found: {run_json}")
        sys.exit(1)

    run = json.loads(run_json.read_text(encoding="utf-8"))
    case_text = (run.get("case") or {}).get("text", "")
    questions = run.get("questions") or []

    # Load KB
    kb_path = run_dir / "translated" / "le" / "kb.fo"
    if not kb_path.exists():
        kb_path = run_dir / "kb.fo"
    if not kb_path.exists():
        print(f"KB not found in {run_dir}")
        sys.exit(1)

    kb_text = kb_path.read_text(encoding="utf-8")

    # Get case: results.json, or parse from run_trace.txt (last "Case (normalized)" block)
    case = None
    results_path = run_dir / "results.json"
    if results_path.exists():
        results = json.loads(results_path.read_text(encoding="utf-8"))
        q0 = (results.get("questions") or [{}])[0]
        case = (q0.get("pipeline") or {}).get("case")
    if not case:
        trace_path = run_dir / "run_trace.txt"
        if trace_path.exists():
            txt = trace_path.read_text(encoding="utf-8")
            marker = "--- Case (normalized) ---"
            idx = txt.rfind(marker)  # last occurrence (e.g. Q3)
            if idx >= 0:
                rest = txt[idx + len(marker):].lstrip()
                depth, start = 0, -1
                for i, c in enumerate(rest):
                    if c == "{":
                        if depth == 0:
                            start = i
                        depth += 1
                    elif c == "}":
                        depth -= 1
                        if depth == 0 and start >= 0:
                            try:
                                case = json.loads(rest[start:i + 1])
                                break
                            except json.JSONDecodeError:
                                pass
    if not case or "facts" not in case:
        case = {"facts": [], "entities": {"Person": []}}

    from idp_z3.tasks import _compose_program

    fo_code = _compose_program(case, kb_text)
    print("=== CASE USED ===")
    print(json.dumps(case, indent=2))
    print("\n=== STRUCTURE BLOCK (from composed program) ===")
    if "structure S:V {" in fo_code:
        i0 = fo_code.find("structure S:V {")
        i1 = fo_code.find("}", i0) + 1
        # Match outer braces
        depth, j = 0, i0 + len("structure S:V ")
        for k in range(j, len(fo_code)):
            if fo_code[k] == "{": depth += 1
            elif fo_code[k] == "}":
                depth -= 1
                if depth == 0:
                    i1 = k + 1
                    break
        print(fo_code[i0:i1])
    # Check satisfiability and get explanation if UNSAT
    from idp_z3.idp_backend import run_idp
    result = run_idp(fo_code, max_models=1)
    print("SAT:", result["sat"])

    if not result["sat"]:
        print("\n=== FETCHING UNSAT EXPLANATION (Theory.explain) ===")
        try:
            from idp_engine import IDP, Theory
            kb = IDP.from_str(fo_code)
            T_block, S_block = kb.get_blocks("T, S")
            theory = Theory(T_block, S_block)
            theory.propagate()
            facts, formulas = theory.explain()
            print("Conflicting facts/assignments:")
            for f in facts:
                print(" ", f)
            print("Conflicting formulas:")
            for fm in formulas:
                code = getattr(fm, "code", str(fm))
                print(" ", code)
        except Exception as e:
            print("Could not get explanation:", e)

if __name__ == "__main__":
    main()
