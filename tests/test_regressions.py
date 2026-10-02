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
    def test_generation_page_exposes_custom_runtime_check(self):
        import app.ui.generation_page as generation_page

        self.assertTrue(callable(generation_page.runtime_ready))


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

    def test_generation_resume_reuses_completed_chunks_without_reopening_them(self):
        from app.tts.generator import generate_chapter

        class DummyProvider:
            def __init__(self):
                self.calls = 0

            def synthesize(self, text, output_path, voice=None):
                self.calls += 1
                _write_wav(output_path, 0.20)
                return output_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "audio"
            chapter = Chapter(
                1,
                "Chapter One",
                "This is the first sentence. This is the second sentence. "
                "This is the third sentence. This is the fourth sentence.",
            )
            provider = DummyProvider()

            first = generate_chapter(
                chapter,
                provider,
                "Narrator",
                root,
                narration_speed=1.0,
                pacing_profile="off",
            )
            first_calls = provider.calls
            self.assertGreater(first_calls, 0)
            self.assertEqual(first.chunks_completed, first.chunks_total)

            second = generate_chapter(
                chapter,
                provider,
                "Narrator",
                root,
                narration_speed=1.0,
                pacing_profile="off",
            )
            self.assertEqual(provider.calls, first_calls)
            self.assertEqual(second.chunks_completed, second.chunks_total)


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


    def test_online_tts_network_error_is_classifiable(self):
        from app.tts.providers.edge_tts import EdgeTTSProvider, OnlineTTSNetworkError

        self.assertTrue(issubclass(OnlineTTSNetworkError, RuntimeError))
        self.assertTrue(getattr(EdgeTTSProvider, "is_online_provider", False))

    def test_edge_tts_classifies_no_audio_as_transient_service_error(self):
        from app.tts.providers.edge_tts import EdgeTTSProvider

        self.assertTrue(EdgeTTSProvider._is_transient_service_error("NoAudioReceived: No audio was received. Please verify that your parameters are correct."))
        self.assertTrue(EdgeTTSProvider._is_transient_service_error("WebSocket connection was closed by the server"))
        self.assertTrue(EdgeTTSProvider._is_transient_service_error("getaddrinfo failed"))
        self.assertFalse(EdgeTTSProvider._is_transient_service_error("An invalid voice parameter was supplied"))

    def test_edge_tts_uses_extended_transient_retry_budget(self):
        from app.tts.providers.edge_tts import EdgeTTSProvider

        self.assertEqual(EdgeTTSProvider.transient_retry_attempts, 5)
        self.assertEqual(EdgeTTSProvider.request_timeout_seconds, 60)

    def test_online_tts_provider_stops_generation_after_service_failure(self):
        from app.tts.providers.edge_tts import EdgeTTSProvider, OnlineTTSNetworkError

        self.assertTrue(EdgeTTSProvider.stop_on_failure)
        self.assertEqual(EdgeTTSProvider.request_timeout_seconds, 60)
        self.assertTrue(issubclass(OnlineTTSNetworkError, RuntimeError))

    def test_manager_stops_after_online_provider_failure(self):
        from app.tts.manager import GenerationManager

        class StopProvider:
            stop_on_failure = True

            def synthesize(self, text, output_path, voice=None):
                raise RuntimeError("online voice service unavailable")

            def close(self):
                pass

        summaries = []
        manager = GenerationManager(
            StopProvider(),
            "voice",
            [
                Chapter(1, "One", "One"),
                Chapter(2, "Two", "Two"),
                Chapter(3, "Three", "Three"),
            ],
            Path(tempfile.mkdtemp()),
            on_finished=summaries.append,
        )
        manager.start()
        manager._thread.join(timeout=10)

        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].chapters_failed, [1])

    def test_project_save_round_trip_preserves_manual_chapter_edits(self):
        from app.core.project import Project

        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / "Book"
            project = Project(
                "Book",
                folder,
                None,
                [
                    Chapter(1, "Chapter One", "Edited body text."),
                    Chapter(2, "Chapter Two", "Second edited body."),
                ],
            )
            project.save()

            loaded = Project.load(folder)
            self.assertEqual(
                [(c.number, c.title, c.text) for c in loaded.chapters],
                [
                    (1, "Chapter One", "Edited body text."),
                    (2, "Chapter Two", "Second edited body."),
                ],
            )


if __name__ == "__main__":
    unittest.main()
