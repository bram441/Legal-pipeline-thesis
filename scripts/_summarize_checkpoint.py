#!/usr/bin/env python
import json
from pathlib import Path
from collections import Counter

OUT = Path("results/reports/evaluation_checkpoint_direct_json_ir_after_repairs")
m = json.loads((OUT / "matrix.json").read_text(encoding="utf-8"))
runs, strats, cells = m["runs"], m["strategies"], m["cells"]
errs, routes, llm = Counter(), Counter(), 0
for run in runs:
    for s in strats:
        c = cells[run][s]
        p = c.get("path")
        if not p:
            continue
        rs_path = Path(p) / "json_ir_compile" / "repair_summary.json"
        if rs_path.is_file():
            rs = json.loads(rs_path.read_text(encoding="utf-8"))
            if not c.get("ok"):
                errs[rs.get("final_normalized_error_code", "?")] += 1
                used = rs.get("repair_layers_used") or []
                if used:
                    routes[used[-1]] += 1
            llm += rs.get("total_kb_llm_calls") or 0
print("TOP_ERRORS", dict(errs.most_common(8)))
print("ROUTES", dict(routes.most_common(6)))
print("LLM_SUM", llm)
