import os
import unittest

from pipeline.eval.scoring import belief_scoring_enabled, score_question


class TestBooleanDecisiveScoring(unittest.TestCase):
    def tearDown(self):
        for k in ("SCORE_TREAT_OPEN_WITH_BELIEF", "SCORE_BOOLEAN_BELIEF_THRESHOLD", "PIPELINE_OPEN_WORLD_P_YES"):
            os.environ.pop(k, None)

    def test_entailed_matches_expected_true(self):
        r = score_question({"mode": "boolean", "value": True}, {"certain": True, "possible": True})
        self.assertTrue(r["match"])
        self.assertTrue(r["decisive"])
        self.assertFalse(r["inconclusive"])
        self.assertIs(r["got"], True)

    def test_contradicted_matches_expected_false(self):
        r = score_question({"mode": "boolean", "value": False}, {"certain": False, "possible": False})
        self.assertTrue(r["match"])
        self.assertTrue(r["decisive"])
        self.assertIs(r["got"], False)

    def test_open_unknown_is_not_correct_for_expected_true(self):
        r = score_question({"mode": "boolean", "value": True}, {"certain": False, "possible": True})
        self.assertFalse(r["match"])
        self.assertTrue(r["inconclusive"])
        self.assertFalse(r["decisive"])
        self.assertIsNone(r["got"])
        self.assertEqual(r["epistemic_label"], "unknown")
        self.assertIn("warning", r)

    def test_open_unknown_is_not_correct_for_expected_false(self):
        r = score_question({"mode": "boolean", "value": False}, {"certain": False, "possible": True})
        self.assertFalse(r["match"])
        self.assertTrue(r["inconclusive"])
        self.assertIn("warning", r)

    def test_belief_scoring_off_by_default_even_with_threshold_in_expected(self):
        os.environ.pop("SCORE_TREAT_OPEN_WITH_BELIEF", None)
        r = score_question(
            {"mode": "boolean", "value": True, "belief_match_threshold": 0.45},
            {"certain": False, "possible": True},
        )
        self.assertFalse(belief_scoring_enabled())
        self.assertFalse(r["match"])
        self.assertTrue(r["inconclusive"])

    def test_belief_scoring_on_only_when_env_explicit(self):
        os.environ["SCORE_TREAT_OPEN_WITH_BELIEF"] = "1"
        os.environ["SCORE_BOOLEAN_BELIEF_THRESHOLD"] = "0.5"
        os.environ["PIPELINE_OPEN_WORLD_P_YES"] = "0.5"
        self.assertTrue(belief_scoring_enabled())
        r = score_question({"mode": "boolean", "value": True}, {"certain": False, "possible": True})
        self.assertTrue(r["match"])
        self.assertTrue(r.get("belief_scored"))
        self.assertEqual(r["scoring_mode"], "belief")

    def test_belief_threshold_065_fails_at_prior_05(self):
        os.environ["SCORE_TREAT_OPEN_WITH_BELIEF"] = "1"
        r = score_question(
            {"mode": "boolean", "value": True, "belief_match_threshold": 0.65},
            {"certain": False, "possible": True},
        )
        self.assertFalse(r["match"])


class TestRun001ScoringRegression(unittest.TestCase):
    """run_001-style unknown must not count as correct without belief scoring."""

    def tearDown(self):
        os.environ.pop("SCORE_TREAT_OPEN_WITH_BELIEF", None)

    def test_unknown_possible_not_counted_correct(self):
        symbolic = {"possible": True, "certain": False, "label": "unknown"}
        r = score_question({"mode": "boolean", "value": True}, symbolic)
        self.assertFalse(r["match"])
        self.assertTrue(r["inconclusive"])

    def test_entailed_future_target(self):
        """When pipeline eventually returns certain=true, decisive scoring should pass."""
        r = score_question(
            {"mode": "boolean", "value": True},
            {"possible": True, "certain": True},
        )
        self.assertTrue(r["match"])
        self.assertTrue(r["decisive"])


if __name__ == "__main__":
    unittest.main()
