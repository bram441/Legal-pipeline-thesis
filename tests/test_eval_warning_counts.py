import unittest

from scripts.eval_support import summarize_query_targets


class TestEvalWarningCounts(unittest.TestCase):
    def test_splits_warning_counts(self):
        score = {
            "items": [
                {
                    "id": "q1",
                    "query_predicate": "p",
                    "query_predicate_kind": "derived",
                    "warnings": [
                        "Expected legal Boolean answer was evaluated using observable predicate 'obs'.",
                        "Antecedent diagnostics: missing observable case facts for cond_a.",
                    ],
                }
            ],
        }
        s = summarize_query_targets(score)
        self.assertEqual(s["observable_query_target_warning_count"], 1)
        self.assertEqual(s["antecedent_diagnostic_warning_count"], 1)


if __name__ == "__main__":
    unittest.main()
