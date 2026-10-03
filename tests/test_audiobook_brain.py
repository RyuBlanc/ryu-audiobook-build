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
        self.assertEqual(APP_VERSION, "0.3.6")

    def test_chatterbox_runtime_is_resume_safe_and_pinned(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "app" / "tts" / "chatterbox_runtime.py").read_text(encoding="utf-8")
        self.assertIn("CHATTERBOX_SOURCE_REVISION", source)
        self.assertIn('"--no-cache-dir", "--upgrade", "-r"', source)
        self.assertIn('"--no-cache-dir", "--no-deps", str(source_archive)', source)
        self.assertIn("def _verify_runtime", source)
        self.assertIn('"nano_supported": True', source)
        self.assertIn("if runtime_ready():", source)

    def test_versioned_pyinstaller_resource_is_enabled(self):
        from pathlib import Path
        build_source = (Path(__file__).resolve().parents[1] / "build.py").read_text(encoding="utf-8")
        self.assertIn("--version-file=", build_source)
        self.assertIn("VersionInfo(", build_source)

    def test_robust_merge_ignores_string_items(self):
        from app.ai.brain import AudiobookBrain
        brain = AudiobookBrain.__new__(AudiobookBrain)
        result = {"characters": [], "dialogue": [], "scenes": [], "pronunciation": [], "continuity_notes": []}
        brain._merge(result, {
            "characters": ["not-a-character", {"name": "Haruka", "confidence": "high"}],
            "dialogue": ["not-dialogue", {"quote": "Hello", "speaker": "Haruka", "confidence": 0.9}],
            "scenes": ["not-a-scene", {"summary": "Classroom", "confidence": 0.9}],
            "pronunciation": ["not-pronunciation"],
            "continuity_notes": ["rain"],
        }, set(), "Haruka said Hello in the classroom.")
        self.assertEqual([x["name"] for x in result["characters"]], ["Haruka"])
        self.assertEqual([x["quote"] for x in result["dialogue"]], ["Hello"])
        self.assertEqual(len(result["scenes"]), 1)
        self.assertEqual(result["continuity_notes"], ["rain"])

    def test_native_pronunciation_and_english_filtering(self):
        from app.tts.pronunciation_suggester import is_common_english_phrase, nativeish_pronunciation
        self.assertTrue(is_common_english_phrase("Gravity"))
        self.assertTrue(is_common_english_phrase("Let"))
        self.assertEqual(nativeish_pronunciation("Hinata", "Japanese"), "Hee-nah-tah")

    def test_empty_chapter_skips_ai(self):
        from pathlib import Path
        import tempfile
        from app.ai.brain import AudiobookBrain
        from app.chapters.detector import Chapter
        with tempfile.TemporaryDirectory() as temp:
            brain = AudiobookBrain.__new__(AudiobookBrain)
            brain.project_folder = Path(temp)
            brain.analysis_dir = Path(temp) / "analysis"
            brain.analysis_dir.mkdir()
            result = brain.analyze_chapter(Chapter(2, "Empty", ""))
            self.assertIn("no body text", result["warnings"][0].lower())


if __name__ == "__main__":
    unittest.main()
