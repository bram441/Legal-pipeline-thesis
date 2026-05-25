"""Tests for scripts/eval_support.py (failure classification for benchmarks)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def _load_eval_support():
    path = _ROOT / "scripts" / "eval_support.py"
    spec = importlib.util.spec_from_file_location("eval_support_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class TestClassifyFailure(unittest.TestCase):
    def test_completed_with_results(self):
        es = _load_eval_support()
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            (w / "results.json").write_text(
                json.dumps({"questions": [{"pipeline": {"sat": True}}]}),
                encoding="utf-8",
            )
            self.assertEqual(es.classify_failure(w, 0, ok=True), "completed")

    def test_completed_with_errors(self):
        es = _load_eval_support()
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            (w / "results.json").write_text(
                json.dumps(
                    {
                        "questions": [
                            {"pipeline": {"error_stage": "symbolic"}},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(es.classify_failure(w, 0, ok=True), "completed_with_errors")

    def test_kb_lint_from_trace(self):
        es = _load_eval_support()
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            (w / "run_trace.txt").write_text(
                "--- Validation failed (ERROR) ---\nKB lint: Theory contains `let`\n",
                encoding="utf-8",
            )
            self.assertEqual(es.classify_failure(w, 1, ok=False), "kb_lint")

    def test_reasoning_symbol_mismatch(self):
        es = _load_eval_support()
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            (w / "run_trace.txt").write_text(
                "--- Symbolic reasoning failed (ERROR) ---\nSymbol not in vocabulary: karel\n",
                encoding="utf-8",
            )
            self.assertEqual(es.classify_failure(w, 0, ok=False), "reasoning_symbol_mismatch")

    def test_process_error_no_logs(self):
        es = _load_eval_support()
        with tempfile.TemporaryDirectory() as td:
            w = Path(td)
            self.assertEqual(es.classify_failure(Path(td), 2, ok=False), "process_error")


if __name__ == "__main__":
    unittest.main()
