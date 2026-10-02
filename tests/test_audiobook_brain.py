import unittest

from app.ai.brain import _json, BrainUnavailableError
from app.ai.model_runtime import model_path


class AudiobookBrainTests(unittest.TestCase):
    def test_json_parser_accepts_plain_json(self):
        value = _json('{"characters": [], "dialogue": []}')
        self.assertEqual(value["characters"], [])

    def test_json_parser_accepts_json_fence(self):
        value = _json('```json\n{"scenes": []}\n```')
        self.assertEqual(value["scenes"], [])

    def test_json_parser_rejects_non_object(self):
        with self.assertRaises(BrainUnavailableError):
            _json('[1, 2, 3]')

    def test_model_path_has_local_models_root(self):
        self.assertIn("audiobook-ai", str(model_path()))


if __name__ == "__main__":
    unittest.main()