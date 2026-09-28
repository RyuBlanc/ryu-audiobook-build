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
from app.tts.pacing import append_silence, pause_after_ms, split_for_pacing
from app.tts.preview import build_voice_preview
from app.tts.pronunciation_suggester import suggest_pronunciation, suggest_names_from_text, COMMON_ENGLISH_WORDS


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

    def test_natural_pacing_splits_story_into_sentence_units(self):
        text = "The door opened. Issei looked inside. Rias smiled."
        chunks = split_for_pacing(text, max_chars=200, max_sentences=2)
        self.assertEqual(chunks, ["The door opened. Issei looked inside.", "Rias smiled."])
        self.assertGreater(pause_after_ms("Rias smiled.", "natural"), 0)
        self.assertGreater(pause_after_ms("Rias smiled!", "natural"), pause_after_ms("Rias smiled.", "natural"))
        self.assertEqual(pause_after_ms("Rias smiled.", "off"), 0)

    def test_natural_pacing_appends_silence_without_changing_existing_audio(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "chunk.wav"
            _write_wav(path, 1.0)
            with wave.open(str(path), "rb") as before:
                original_frames = before.getnframes()
                rate = before.getframerate()
            append_silence(path, 250)
            with wave.open(str(path), "rb") as after:
                self.assertEqual(after.getframerate(), rate)
                self.assertGreater(after.getnframes(), original_frames)
                self.assertEqual(after.getnframes(), original_frames + round(rate * 0.25))

    def test_pronunciation_suggester_has_known_name_readings(self):
        self.assertEqual(suggest_pronunciation("Hyoudou Issei"), "Hee-doh Is-say")
        self.assertEqual(suggest_pronunciation("Ise"), "Ee-say")
        self.assertEqual(suggest_pronunciation("Rias"), "Ree-ahs")

    def test_pronunciation_suggester_ignores_common_english_words(self):
        text = """But she looked at Her friend.
Hyoudou Issei spoke to Rias Gremory.
"""
        candidates = {value.casefold() for value in suggest_names_from_text(text)}
        self.assertNotIn("but", candidates)
        self.assertNotIn("she", candidates)
        self.assertNotIn("her", candidates)
        self.assertIn("what", COMMON_ENGLISH_WORDS)
        self.assertIn("hyoudou issei", candidates)

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
    def test_cast_provider_routes_em_dash_dialogue_to_assigned_character(self):
        from app.tts.cast_provider import CastAwareProvider

        class DummyNarrator:
            def synthesize(self, text, output_path, voice=None):
                return output_path

        provider = CastAwareProvider(
            DummyNarrator(),
            "Narrator",
            profiles={},
            assignments={"Akeno Himejima": "Akeno Voice"},
        )
        text = """Akeno Himejima
—Hello there, Issei.

The hallway was quiet.

Rias Gremory
—We should get going.
"""
        parts = provider.split_for_cast(text, "Narrator")
        assigned = [(value, voice) for value, voice in parts if voice == "Akeno Voice"]
        self.assertTrue(assigned)
        self.assertEqual(assigned[0][0], "Hello there, Issei.")

        provider.close()

    def test_voice_preview_uses_pronunciation_and_creates_audio(self):
        class DummyProvider:
            def synthesize(self, text, output_path, voice=None):
                _write_wav(output_path, 0.20)
                self.last_text = text
                self.last_voice = voice

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "preview.wav"
            provider = DummyProvider()
            result = build_voice_preview(
                "Hyoudou Issei looked at the door.",
                provider,
                "Narrator",
                output,
                pronunciation_dictionary=[
                    {"written": "Hyoudou Issei", "spoken": "Hee-doh Is-say", "enabled": True}
                ],
                narration_speed=1.0,
                pacing_profile="natural",
                max_chars=500,
            )
            self.assertTrue(result.output_path.exists())
            self.assertGreater(result.segments, 0)
            self.assertIn("Hee-doh Is-say", provider.last_text)
            self.assertEqual(provider.last_voice, "Narrator")

    def test_voice_profile_library_preserves_custom_voice_and_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            import app.tts.voice_profile as vp

            original_root = vp.voices_root
            root = Path(temp) / "Voices"
            vp.voices_root = lambda: root
            try:
                custom = VoiceProfile(
                    name="Offline Neural • Amy",
                    provider="chatterbox",
                    voice_id="reference",
                    sample_path=str(root / "custom" / "reference.wav"),
                    model_id="chatterbox-multilingual",
                    backend="automatic",
                    language="en",
                    authorized=True,
                )
                builtin = VoiceProfile(
                    name="Offline Neural • Amy",
                    provider="piper",
                    voice_id="en_US-amy-medium",
                    backend="automatic",
                    language="en-US",
                    authorized=True,
                )
                save_profiles([custom, builtin])
                loaded = load_profiles()
                custom_loaded = [p for p in loaded if p.provider == "chatterbox"]
                builtin_loaded = [p for p in loaded if p.provider == "piper"]
                self.assertEqual(len(custom_loaded), 1)
                self.assertEqual(len(builtin_loaded), 1)
                self.assertNotEqual(
                    custom_loaded[0].name.casefold(),
                    builtin_loaded[0].name.casefold(),
                )
                self.assertTrue(
                    custom_loaded[0].name.casefold().startswith("offline neural • amy")
                )
                self.assertEqual(custom_loaded[0].sample_path, str(root / "custom" / "reference.wav"))
            finally:
                vp.voices_root = original_root

    def test_generation_resume_state_detects_completed_and_partial_chapters(self):
        from app.tts.resume import inspect_generation_state

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            completed_dir = root / "001_Chapter_1"
            completed_dir.mkdir(parents=True)
            (completed_dir / "generation.json").write_text(
                '{"chunks_total": 2, "completed": [0, 1]}',
                encoding="utf-8",
            )

            partial_dir = root / "002_Chapter_2"
            (partial_dir / "chunks").mkdir(parents=True)
            (partial_dir / "generation.json").write_text(
                '{"chunks_total": 3, "completed": [0]}',
                encoding="utf-8",
            )

            chapters = [
                Chapter(1, "Chapter 1", "one"),
                Chapter(2, "Chapter 2", "two"),
                Chapter(3, "Chapter 3", "three"),
            ]
            state = inspect_generation_state(root, chapters)
            self.assertEqual(state.completed_chapters, (1,))
            self.assertEqual(state.partial_chapters, (2,))
            self.assertTrue(state.resume_available)

    def test_library_status_marks_failed_latest_generation_as_needs_attention_even_with_old_output(self):
        from app.ui.library import project_status
        from app.core.project import Project

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "Book"
            folder.mkdir()
            output = folder / "book.m4b"
            output.write_bytes(b"old-valid-output")
            project = Project("Retry Book", folder, None, [Chapter(1, "Chapter 1", "Story")])
            (folder / "state.json").write_text(
                '{"status": "failed", "output_path": "' + str(output).replace('\\', '/') + '", "failed_chapters": [2]}',
                encoding="utf-8",
            )
            self.assertEqual(project_status(project)[0], "Needs Attention")

    def test_library_project_status_prefers_finished_m4b(self):
        from app.ui.library import project_status, project_matches
        from app.core.project import Project

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "Book"
            folder.mkdir()
            chapters = [Chapter(1, "Chapter 1", "Story text.")]
            project = Project("Test Book", folder, folder / "source.txt", chapters)
            state = {
                "status": "completed",
                "output_path": str(folder / "book.m4b"),
                "completed_chapters": [1],
                "failed_chapters": [],
            }
            (folder / "state.json").write_text(
                __import__("json").dumps(state),
                encoding="utf-8",
            )
            output = folder / "book.m4b"
            output.write_bytes(b"m4b")
            self.assertEqual(project_status(project)[0], "Completed")
            self.assertTrue(project_matches(project, "test", "Completed"))
            self.assertFalse(project_matches(project, "other", "Completed"))

    def test_library_project_status_detects_needs_attention(self):
        from app.ui.library import project_status
        from app.core.project import Project

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "Book"
            folder.mkdir()
            project = Project("Broken Book", folder, None, [Chapter(1, "Chapter 1", "Story")])
            (folder / "state.json").write_text(
                '{"status": "failed", "failed_chapters": [1]}',
                encoding="utf-8",
            )
            self.assertEqual(project_status(project)[0], "Needs Attention")

    def test_generation_readiness_blocks_missing_required_items(self):
        from app.tts.readiness import build_generation_readiness

        chapters = [Chapter(1, "Chapter 1", "Story text.")]
        result = build_generation_readiness(
            chapters,
            voice_name=None,
            voice_provider=None,
            output_path="book.m4b",
        )
        self.assertFalse(result.ready)
        self.assertEqual(len(result.blocking_failures), 1)
        self.assertIn("Narrator voice", result.blocking_failures[0].label)

    def test_generation_readiness_allows_optional_items_to_be_missing(self):
        from app.tts.readiness import build_generation_readiness

        chapters = [Chapter(1, "Chapter 1", "Story text.")]
        result = build_generation_readiness(
            chapters,
            voice_name="Narrator",
            voice_provider="piper",
            output_path="book.m4b",
            assignments={},
            cover_selected=False,
        )
        self.assertTrue(result.ready)
        self.assertEqual(result.attention_count, 0)

    def test_voice_cast_filter_and_confidence_helpers(self):
        from app.ui.voice_cast_page import cast_row_matches, confidence_band

        row = {
            "name": "Akeno Himejima",
            "role": "Character",
            "aliases": ["Akeno"],
            "voice": "Akeno Voice",
            "confidence": 0.91,
        }
        self.assertEqual(confidence_band(0.91), "High confidence")
        self.assertEqual(confidence_band(0.70), "Medium confidence")
        self.assertEqual(confidence_band(0.40), "Needs review")
        self.assertTrue(cast_row_matches(row, "Assigned", "akeno"))
        self.assertFalse(cast_row_matches(row, "Needs Voice", "akeno"))
        self.assertTrue(cast_row_matches(row, "All", "himejima"))
        self.assertFalse(cast_row_matches(row, "All", "rias"))

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
