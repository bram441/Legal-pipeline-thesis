import unittest

from pipeline.rendering.nl_answer import render_boolean_nl


class TestRenderDescriptions(unittest.TestCase):
    def test_uses_schema_description(self):
        kb_schema = {
            "predicates": [
                {
                    "name": "legal_result",
                    "args": ["Actor"],
                    "returns": "Bool",
                    "kind": "derived",
                    "description": "The actor acquires the legal benefit described by the rule.",
                }
            ],
        }
        out = render_boolean_nl("legal_result", ["alice"], True, True, kb_schema=kb_schema)
        self.assertIn("acquires the legal benefit", out)
        self.assertIn("Alice", out)
        self.assertNotIn("legal_result(", out)


if __name__ == "__main__":
    unittest.main()
