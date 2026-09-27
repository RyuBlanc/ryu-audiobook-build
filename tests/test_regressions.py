import tempfile
import unittest
from pathlib import Path
import subprocess
import inspect
import sys
import wave

# Always import the application package from this checkout, not an identically
# named package that may be present in the CI Python environment.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.audio.assembler import assemble_m4b
from app.chapters.characters import analyze_book, _all_dialogue_spans
from app.chapters.detector import Chapter, detect_chapters
from app.tts.voice_profile import VoiceProfile, save_profiles, load_profiles
from app.tts.narration import prepare_for_narration
from app.tts.pronunciation_suggester import suggest_pronunciation, suggest_names_from_text


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

    def test_light_novel_em_dash_dialogue_is_detected(self):
        text = """Chapter 1
Issei Hyoudou\u2014That's my name.

Akeno Himejima
\u2014Hello there, Issei.

Rias Gremory
\u2014We should get going.
"""
        self.assertEqual([ord(ch) for ch in text if ch in "—–-"], [0x2014, 0x2014, 0x2014])
        import app.chapters.characters as characters_module
        lines = text.splitlines(keepends=True)
        dash_lines = [
            (repr(line), hex(ord(line.lstrip(" \\t")[0])))
            for line in lines
            if line.lstrip(" \\t") and ord(line.lstrip(" \\t")[0]) in (0x2014, 0x2013, 0x2D)
        ]
        self.assertEqual(len(dash_lines), 2, repr(dash_lines))
        parser_source = inspect.getsource(characters_module._all_dialogue_spans)
        self.assertIn(
            "dash-only line",
            parser_source,
            f"Unexpected character parser import: {characters_module.__file__}\n"
            f"sys.path={sys.path}\n"
            f"parser={parser_source}",
        )
        spans = _all_dialogue_spans(text)
        self.assertGreaterEqual(
            len(spans), 2,
            repr({
                "module": characters_module.__file__,
                "dash_lines": dash_lines,
                "spans": spans,
                "source_has_dash_parser": "dash-only line" in inspect.getsource(characters_module._all_dialogue_spans),
            }),
        )
        analysis = analyze_book([Chapter(1, "Chapter 1", text)])
        names = {c.name.casefold() for c in analysis.characters}
        self.assertIn("issei hyoudou", names)
        self.assertIn("akeno himejima", names)
        self.assertIn("rias gremory", names)
        self.assertGreaterEqual(analysis.dialogue_total, 2)

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

    def test_narration_preprocessing_preserves_source_and_repairs_wrapping(self):
        source = """This is a sentence that was split
across two extracted PDF lines.

“He looked at me,”
she said.
Page 12
"""
        result = prepare_for_narration(source)

        self.assertEqual(result.source_text, source)
        self.assertIn("sentence that was split across two extracted PDF lines.", result.narration_text)
        self.assertIn('"He looked at me,"', result.narration_text)
        self.assertIn("she said.", result.narration_text)
        self.assertNotIn("Page 12", result.narration_text)

    def test_pronunciation_suggester_has_known_name_readings(self):
        self.assertEqual(suggest_pronunciation("Hyoudou Issei"), "Hee-doh Is-say")
        self.assertEqual(suggest_pronunciation("Ise"), "Ee-say")
        self.assertEqual(suggest_pronunciation("Rias"), "Ree-ahs")

    def test_pronunciation_suggester_finds_capitalized_name_candidates(self):
        text = "Hyoudou Issei met Rias Gremory at Kuoh Academy."
        names = suggest_names_from_text(text)
        self.assertIn("Hyoudou Issei", names)
        self.assertIn("Rias Gremory", names)
    def test_pronunciation_dictionary_is_case_insensitive_and_phrase_aware(self):
        source = "Hyoudou Issei met Ise. HYoudou Issei smiled."
        result = prepare_for_narration(source, [
            {"written": "Hyoudou Issei", "spoken": "Hee-doh Is-say", "enabled": True},
            {"written": "Ise", "spoken": "Ee-say", "enabled": True},
        ])
        self.assertEqual(
            result.narration_text,
            "Hee-doh Is-say met Ee-say. Hee-doh Is-say smiled.",
        )

    def test_disabled_pronunciation_entry_is_ignored(self):
        source = "Rias Gremory."
        result = prepare_for_narration(source, [
            {"written": "Rias", "spoken": "Ree-ahs", "enabled": False},
        ])
        self.assertEqual(result.narration_text, source)
    def test_narration_preprocessing_does_not_grammar_correct(self):
        source = "I am a second year high school student."
        result = prepare_for_narration(source)
        self.assertEqual(result.narration_text, source)
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
            self.assertGreater(result.stat().st_size, 0)

            # Validate both streams instead of using a file-size threshold.
            # A valid AAC file containing silence can be only a few KB, so
            # size is not a reliable M4B validity check.
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            audio_probe = subprocess.run(
                [ffmpeg, "-v", "error", "-i", str(result), "-map", "0:a:0", "-f", "null", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(audio_probe.returncode, 0, audio_probe.stderr)

            cover_probe = subprocess.run(
                [ffmpeg, "-v", "error", "-i", str(result), "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(cover_probe.returncode, 0, cover_probe.stderr)


if __name__ == "__main__":
    unittest.main()
