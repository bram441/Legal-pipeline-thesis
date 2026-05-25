import os
import unittest

from pipeline.eval import scoring


class TestScoringOpenBelief(unittest.TestCase):
    def tearDown(self):
        for k in (
            "SCORE_TREAT_OPEN_WITH_BELIEF",
            "SCORE_BOOLEAN_BELIEF_THRESHOLD",
            "PIPELINE_OPEN_WORLD_P_YES",
        ):
            os.environ.pop(k, None)

    def test_open_unknown_scored_when_flag_and_default_threshold(self):
        os.environ["SCORE_TREAT_OPEN_WITH_BELIEF"] = "1"
        os.environ["PIPELINE_OPEN_WORLD_P_YES"] = "0.8"
        expected = {"predicate": "x", "mode": "boolean", "value": True}
        # Open world: not certain, still possible
        symbolic = {"certain": False, "possible": True}
        r = scoring.score_question(expected, symbolic)
        self.assertIsNotNone(r.get("match"))
        self.assertTrue(r.get("match"))
        self.assertAlmostEqual(r.get("belief_match_threshold"), 0.5)

    def test_open_false_expected_uses_complement(self):
        os.environ["SCORE_TREAT_OPEN_WITH_BELIEF"] = "true"
        os.environ["SCORE_BOOLEAN_BELIEF_THRESHOLD"] = "0.5"
        os.environ["PIPELINE_OPEN_WORLD_P_YES"] = "0.2"
        expected = {"predicate": "x", "mode": "boolean", "value": False}
        symbolic = {"certain": False, "possible": True}
        r = scoring.score_question(expected, symbolic)
        self.assertIsNotNone(r.get("match"))
        self.assertTrue(r.get("match"))


if __name__ == "__main__":
    unittest.main()
