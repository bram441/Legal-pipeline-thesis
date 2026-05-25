import os
import unittest
from unittest.mock import MagicMock, patch

from pipeline.kb.law_scope import select_law_text_for_compilation


LAW = """
Article 1
General provision one.

Article 2
Special rule for cited article.

Article 3
Unrelated provision.
""".strip()


class TestLawScopeBeforeLE(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("JSON_IR_SCOPE_MODE", None)

    def test_cited_article_selected_from_question(self):
        os.environ["JSON_IR_SCOPE_MODE"] = "cited"
        scoped, meta = select_law_text_for_compilation(
            LAW,
            question_text="Does this apply under Article 2?",
            case_text="",
        )
        self.assertIn("Article 2", scoped)
        self.assertNotIn("Article 3", scoped)
        self.assertEqual(meta.get("mode"), "cited")

    @patch("pipeline.kb.compiler._compile_json_ir_two_step")
    @patch("pipeline.le.law_text_to_le")
    @patch("pipeline.le.use_le_enabled", return_value=True)
    def test_le_receives_scoped_natural_law_not_full(self, _use_le, mock_le, mock_compile):
        os.environ["JSON_IR_SCOPE_MODE"] = "cited"
        mock_le.return_value = "LE version of article 2"
        mock_compile.return_value = ("vocabulary V {\n}\n\ntheory T:V {\n}\n", {"types": []})

        mock_client = MagicMock()
        with patch("openai.OpenAI", return_value=mock_client):
            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "test-key",
                    "PIPELINE_KB_COMPILER": "openai",
                    "PIPELINE_KB_BACKEND": "json_ir",
                    "PIPELINE_USE_LE": "1",
                },
            ):
                from pipeline.kb.compiler import compile_law_to_kb_fo

                compile_law_to_kb_fo(
                    LAW,
                    question_text="Article 2 applies?",
                    case_text="",
                )

        self.assertTrue(mock_le.called, "law_text_to_le should be called when use_le is enabled")
        le_input = mock_le.call_args[0][0]
        self.assertIn("Article 2", le_input)
        self.assertNotIn("Article 3", le_input)


if __name__ == "__main__":
    unittest.main()
