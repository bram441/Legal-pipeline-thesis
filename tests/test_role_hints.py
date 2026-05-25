import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.kb.json_ir import render_json_ir_to_fo_and_schema
from pipeline.kb.role_hints import role_hints_conflict, unary_subject_role_hints


class TestRoleHints(unittest.TestCase):
    def test_surviving_spouse_description_does_not_add_dead_hint(self):
        hints = unary_subject_role_hints(
            "is_surviving_spouse",
            "Indicates whether a person is the surviving spouse of the deceased.",
        )
        self.assertEqual(hints, frozenset({"lifecycle_alive"}))
        self.assertFalse(role_hints_conflict(hints))

    def test_deceased_unary_is_dead_only(self):
        hints = unary_subject_role_hints("is_deceased", "Indicates whether a person is deceased.")
        self.assertEqual(hints, frozenset({"lifecycle_dead"}))

    def test_run_004_artifact_no_spouse_role_conflation(self):
        ir_path = (
            _ROOT
            / "results/reports/evaluation_20260516T084645Z/work/run_004__le_two_phase__json_ir/json_ir_compile/attempt_02/combined_ir.json"
        )
        if not ir_path.is_file():
            self.skipTest("eval artifact not present")
        ir = json.loads(ir_path.read_text(encoding="utf-8"))
        try:
            render_json_ir_to_fo_and_schema(ir)
            err = None
        except Exception as e:
            err = str(e)
        if err:
            self.assertNotIn("incompatible unary subject roles", err)


if __name__ == "__main__":
    unittest.main()
