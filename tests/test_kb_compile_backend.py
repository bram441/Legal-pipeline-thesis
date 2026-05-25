import os
import unittest

from pipeline.kb.compile_backend import get_kb_backend_from_env, kb_backend_env_override


class TestKBCompileBackend(unittest.TestCase):
    def test_default_backend(self):
        old = os.environ.pop("PIPELINE_KB_BACKEND", None)
        try:
            self.assertEqual(get_kb_backend_from_env(), "json_ir")
        finally:
            if old is not None:
                os.environ["PIPELINE_KB_BACKEND"] = old

    def test_env_override_context(self):
        original = os.environ.get("PIPELINE_KB_BACKEND")
        with kb_backend_env_override("json_ir"):
            self.assertEqual(get_kb_backend_from_env(), "json_ir")
        self.assertEqual(os.environ.get("PIPELINE_KB_BACKEND"), original)


if __name__ == "__main__":
    unittest.main()
