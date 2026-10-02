import unittest

from app.ai.brain import _json, BrainUnavailableError
from app.ai.model_runtime import model_path, runtime_environment


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

    def test_natural_language_scores_are_normalized(self):
        from app.ai.brain import _numeric_score
        self.assertEqual(_numeric_score("Moderate"), 0.5)
        self.assertEqual(_numeric_score("High"), 0.75)
        self.assertEqual(_numeric_score("Very High"), 0.9)

    def test_model_path_has_local_models_root(self):
        self.assertIn("audiobook-ai", str(model_path()))

    def test_model_runtime_exports_shared_environment(self):
        env = runtime_environment()
        self.assertIn("HF_HOME", env)
        self.assertTrue(env["HF_HOME"])

    def test_release_version_is_current_bugfix_line(self):
        from app.version import APP_VERSION
        self.assertEqual(APP_VERSION, "0.3.1")

    def test_model_runtime_exposes_shared_environment(self):
        env = runtime_environment()
        self.assertIsInstance(env, dict)
        self.assertIn("HF_HOME", env)

    def test_chatterbox_pinned_source_is_installed_after_dependency_wheels(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "app" / "tts" / "chatterbox_runtime.py").read_text(encoding="utf-8")
        dependency_loop = source.index("for command in commands:")
        source_install = source.index('"--no-deps", str(source_archive)')
        verify = source.index("sig=inspect.signature(ChatterboxTurboTTS.from_pretrained)")
        self.assertLess(dependency_loop, source_install)
        self.assertLess(source_install, verify)
        self.assertIn("CHATTERBOX_SOURCE_REVISION", source)
        self.assertIn('"nano_supported": True', source)

    def test_versioned_pyinstaller_resource_is_enabled(self):
        from pathlib import Path
        build_source = (Path(__file__).resolve().parents[1] / "build.py").read_text(encoding="utf-8")
        self.assertIn("--version-file=", build_source)
        self.assertIn("VersionInfo(", build_source)


if __name__ == "__main__":
    unittest.main()