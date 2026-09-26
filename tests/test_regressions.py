import tempfile
import unittest
from pathlib import Path
import subprocess
import wave

from app.audio.assembler import assemble_m4b
from app.chapters.characters import analyze_book
from app.chapters.detector import Chapter, detect_chapters
from app.tts.voice_profile import VoiceProfile, save_profiles, load_profiles


def _write_wav(path: Path, seconds: float = 0.05) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 8000
    frames = max(1, int(rate * seconds))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * frames)


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

    def test_m4b_packaging_with_explicit_concat_durations(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter_dirs = []
            for number in (1, 2):
                chapter = root / f"{number:03d}_Chapter_{number}" / "chunks"
                _write_wav(chapter / "00001.wav", 2.0)
                _write_wav(chapter / "00002.wav", 2.0)
                chapter_dirs.append(chapter.parent)
            output = root / "book.m4b"
            result = assemble_m4b(
                chapter_dirs,
                output,
                "Regression Book",
                chapter_titles=["Chapter 1", "Chapter 2"],
            )
            self.assertTrue(result.exists())
            self.assertGreater(result.stat().st_size, 4096)

    def test_m4b_packaging_with_cover(self):
        # Generate a tiny valid JPEG through the same FFmpeg toolchain used by
        # the application instead of relying on a fragile hand-written fixture.
        import imageio_ffmpeg

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cover = root / "cover.jpg"
            ppm = root / "cover.ppm"
            ppm.write_text(
                "P3\n2 2\n255\n"
                "255 255 255   255 0 0\n"
                "0 255 0   0 0 255\n",
                encoding="ascii",
            )
            subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(),
                    "-y",
                    "-f",
                    "image2",
                    "-i",
                    str(ppm),
                    "-frames:v",
                    "1",
                    "-c:v",
                    "mjpeg",
                    "-q:v",
                    "3",
                    str(cover),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            chapter = root / "001_Chapter" / "chunks"
            _write_wav(chapter / "00001.wav", 2.0)
            output = root / "book-cover.m4b"
            result = assemble_m4b(
                [chapter.parent],
                output,
                "Cover Regression",
                chapter_titles=["Chapter 1"],
                cover=cover,
            )
            self.assertTrue(result.exists())
            self.assertGreater(result.stat().st_size, 4096)


if __name__ == "__main__":
    unittest.main()
