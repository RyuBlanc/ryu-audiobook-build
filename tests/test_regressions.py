import tempfile
import unittest
from pathlib import Path

from app.chapters.characters import analyze_book
from app.chapters.detector import Chapter, detect_chapters
from app.tts.voice_profile import VoiceProfile, save_profiles, load_profiles


class RegressionTests(unittest.TestCase):
    def test_light_novel_dialogue_discovers_characters(self):
        text = """Life.0
Issei Hyoudou—that’s my name, but my friends and family just call me Issei.
“My name is Rias Gremory,” said the crimson-haired girl.
“Oh dear. Greetings, I’m Akeno Himejima. Pleased to make your acquaintance,” she said.
“S-same here. Issei Hyoudou. Nice to meet you!” I replied.
“Rias, sit with us,” Akeno said.
"""
        analysis = analyze_book([Chapter(1, "Life.0", text)])
        names = {c.name.casefold() for c in analysis.characters}
        self.assertIn("issei hyoudou", names)
        self.assertIn("rias gremory", names)
        self.assertIn("akeno himejima", names)
        self.assertGreaterEqual(analysis.dialogue_total, 4)
        self.assertLess(analysis.unassigned_dialogue, analysis.dialogue_total)

    def test_detector_never_returns_empty_chapter(self):
        text = """Life.0
Story text here.

Life.1

Life.2
More story text here.
"""
        chapters = detect_chapters(text)
        self.assertTrue(chapters)
        self.assertTrue(all(c.text.strip() for c in chapters))
        self.assertEqual([c.number for c in chapters], list(range(1, len(chapters) + 1)))

    def test_custom_profile_round_trip(self):
        import app.tts.voice_profile as vp

        with tempfile.TemporaryDirectory() as temp:
            original = vp.voices_root
            root = Path(temp) / "Voices"
            vp.voices_root = lambda: root
            try:
                sample = root / "custom" / "reference.wav"
                sample.parent.mkdir(parents=True)
                sample.write_bytes(b"0" * 2048)
                profile = VoiceProfile(
                    name="Test Custom",
                    provider="chatterbox",
                    voice_id="reference",
                    sample_path=str(sample),
                    model_id="chatterbox-multilingual",
                    backend="automatic",
                    language="en",
                    authorized=True,
                )
                save_profiles([profile])
                loaded = [p for p in load_profiles() if p.name == "Test Custom"]
                self.assertEqual(len(loaded), 1)
                self.assertEqual(loaded[0].provider, "chatterbox")
                self.assertEqual(Path(loaded[0].sample_path), sample)
            finally:
                vp.voices_root = original


if __name__ == "__main__":
    unittest.main()
