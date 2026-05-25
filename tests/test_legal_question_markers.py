import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.semantic.legal_question import (
    question_asks_legal_conclusion,
    question_asks_legal_definition,
)


class TestLegalQuestionMarkers(unittest.TestCase):
    def test_within_the_meaning_of(self):
        q = "Is there illegal residence for Samir within the meaning of Article 1, paragraph 1, point 4?"
        self.assertTrue(question_asks_legal_definition(q))
        self.assertTrue(question_asks_legal_conclusion(q))

    def test_consequence_timing(self):
        q = "Do the consequences according to article 1:24, paragraph 2 apply from the financial year following 2025?"
        self.assertTrue(question_asks_legal_conclusion(q))

    def test_in_de_zin_van(self):
        q = "Is er sprake van illegaal verblijf in de zin van artikel 1?"
        self.assertTrue(question_asks_legal_definition(q))


if __name__ == "__main__":
    unittest.main()
