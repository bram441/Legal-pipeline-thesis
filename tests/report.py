# tests/report.py
import json
from pathlib import Path
from datetime import datetime

def write_report(out_dir, suite_name, payload):
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    fname = "report_" + suite_name + "_" + timestamp + ".json"
    path = out_path / fname
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)