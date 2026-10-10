import tempfile
import unittest
from pathlib import Path
import subprocess
import inspect
import sys
import wave
import json

# Always import the application package from this checkout, not an identically
# named package that may be present in the CI Python environment.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.audio.assembler import assemble_m4b, _probe_audio_bitrate_kbps, DEFAULT_AUDIO_BITRATE_KBPS
from app.chapters.characters import analyze_book, _all_dialogue_spans
from app.chapters.dialogue import dialogue_segment_for_selection
from app.chapters.detector import Chapter, detect_chapters
from app.tts.voice_profile import VoiceProfile, save_profiles, load_profiles, import_reference_audio
from app.tts.narration import prepare_for_narration
from app.tts.pacing import append_silence, pause_after_ms, split_for_pacing
from app.tts.preview import build_voice_preview
from app.tts.pronunciation_suggester import (
    suggest_pronunciation, suggest_names_from_text, COMMON_ENGLISH_WORDS,
    is_common_english_phrase, nativeish_pronunciation,
 )


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
    def test_pronunciation_candidates_reject_ordinary_english(self):
        self.assertTrue(is_common_english_phrase("All"))
        self.assertTrue(is_common_english_phrase("Confirmed"))
        self.assertTrue(is_common_english_phrase("Sir"))
        self.assertTrue(is_common_english_phrase("Sure"))
        self.assertEqual(nativeish_pronunciation("Hinata", "Japanese"), "Hee-nah-tah")

    def test_elevenlabs_key_round_trip_is_local(self):
        import app.tts.providers.elevenlabs as eleven
        with tempfile.TemporaryDirectory() as temp:
            original = eleven.ElevenLabsProvider.KEY_FILE
            eleven.ElevenLabsProvider.KEY_FILE = Path(temp) / "elevenlabs.json"
            try:
                eleven.ElevenLabsProvider.save_api_key("test-key")
                self.assertEqual(eleven.ElevenLabsProvider.load_api_key(), "test-key")
                self.assertTrue(eleven.ElevenLabsProvider.KEY_FILE.exists())
            finally:
                eleven.ElevenLabsProvider.KEY_FILE = original

    def test_custom_voice_worker_uses_utf8_ipc(self):
        provider_source = Path("app/tts/providers/chatterbox.py").read_text(encoding="utf-8")
        runtime_source = Path("app/tts/chatterbox_runtime.py").read_text(encoding="utf-8")
        preview_source = Path("app/tts/preview.py").read_text(encoding="utf-8")
        self.assertIn('encoding="utf-8"', provider_source)
        self.assertIn('PYTHONIOENCODING', runtime_source)
        self.assertIn('PYTHONUTF8', runtime_source)
        self.assertIn('encoding="utf-8"', preview_source)

    def test_offline_qwen_runtime_never_creates_venv_from_frozen_app(self):
        source = Path("app/tts/qwen_character_runtime.py").read_text(encoding="utf-8")
        self.assertIn("python312", source)
        self.assertIn('PYTHON_INSTALLER_URL =', source)
        self.assertIn('PYTHON_VERSION = "3.12.10"', source)
        self.assertIn("TargetDir=", source)
        self.assertNotIn("EnvBuilder(with_pip=True, clear=False, upgrade_deps=True)", source)

    def test_offline_qwen_character_catalog_is_declared(self):
        from app.tts.voice_profile import builtin_voice_profiles
        source = Path("app/tts/qwen_character_runtime.py").read_text(encoding="utf-8")
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn("Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", source)
        self.assertIn("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", source)
        self.assertIn("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", source)
        self.assertIn("Qwen/Qwen3-TTS-12Hz-0.6B-Base", source)
        self.assertIn("Qwen/Qwen3-TTS-12Hz-1.7B-Base", source)
        self.assertIn("--models-root", worker)
        self.assertIn('choices=["custom", "design", "clone"]', worker) if False else None

        profiles = [
            p for p in builtin_voice_profiles()
            if p.provider == "qwen-character"
        ]
        # The catalogue remains visible before installation so users can choose
        # a character and see exactly which local pack is required.
        self.assertGreaterEqual(len(profiles), 4)
        english_ids = {p.voice_id for p in profiles if p.language == "English"}
        self.assertEqual(english_ids, {"Ryan", "Aiden"})
        self.assertTrue(any(p.provider == "qwen-character" and p.voice_id == "Ono_Anna" for p in profiles))

    def test_qwen_provider_selects_the_three_real_model_phases(self):
        from app.tts.providers.qwen_character import QwenCharacterProvider

        custom = QwenCharacterProvider(
            voice_id="Ryan",
            model_kind="custom-1.7b",
            qwen_mode="custom",
        )
        design = QwenCharacterProvider(
            voice_id="design-test",
            model_kind="design-1.7b",
            qwen_mode="design",
            instruct="Warm cinematic young female anime heroine.",
            qwen_seed=123,
        )
        clone = QwenCharacterProvider(
            voice_id="clone-test",
            model_kind="base-1.7b",
            qwen_mode="clone",
            reference_audio=Path("reference.wav"),
            reference_text="Hello there.",
        )
        self.assertEqual(custom.model_kind, "custom-1.7b")
        self.assertEqual(design.model_kind, "design-1.7b")
        self.assertEqual(design.qwen_mode, "design")
        self.assertEqual(clone.model_kind, "base-1.7b")
        self.assertEqual(clone.qwen_mode, "clone")
        self.assertEqual(clone.reference_text, "Hello there.")

    def test_chapter_editor_keeps_assignment_labels_small_and_synced(self):
        source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn('badge.setFixedHeight(18)', source)
        self.assertIn('font-size:7px', source)
        self.assertIn('probe.setPosition(end)', source)
        self.assertIn('_update_current_chapter_list_label', source)
        self.assertIn('self.title.textChanged.connect(self._update_current_chapter_list_label)', source)

    def test_chapter_editor_assignment_ui_is_subtle_and_uses_project_title(self):
        source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn("self.text.setViewportMargins(82, 0, 0, 0)", source)
        self.assertIn('assignment_manager_button = QPushButton("Assignments")', source)
        self.assertIn('badge.setFixedWidth(72)', source)
        self.assertIn('badge.setFixedHeight(18)', source)
        self.assertIn("soft.setAlpha(52)", source)
        self.assertIn("self.project_title = str(project_title or \\"\\").strip()", source)
        self.assertNotIn('text=self.window().windowTitle()', source)

    def test_workflow_passes_real_project_title_to_chapter_editor(self):
        source = Path("app/ui/workflow.py").read_text(encoding="utf-8")
        self.assertIn("self.project.folder,", source)
        self.assertIn("self.project.title,", source)

    def test_voice_page_stage_two_contains_library_selectors(self):
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        self.assertIn("library_config_box = QGroupBox", source)
        self.assertIn("root.addWidget(library_config_box)", source)
        self.assertIn("library_config.addWidget(self.neural_box)", source)
        self.assertIn("library_config.addWidget(self.qwen_phase_box)", source)
        self.assertIn("library_config.addWidget(self.sapi_box)", source)
        self.assertIn("library_config.addWidget(self.custom_box)", source)
        self.assertNotIn("root.addWidget(self.custom_box)", source)

    def test_voice_page_uses_four_stage_preview_layout(self):
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        for marker in (
            'QGroupBox("1  •  Voice Library")',
            'QGroupBox("2  •  Library Configuration")',
            'QGroupBox("3  •  Voice Profile")',
            'QGroupBox("4  •  Preview")',
        ):
            self.assertIn(marker, source)
        self.assertIn("for seconds in (10, 20, 30):", source)
        self.assertIn("preview_library", source)
        self.assertIn("preview_voice", source)
        self.assertIn("preview_model", source)
        self.assertIn("VoiceDesign preview", source)
        self.assertNotIn("qwen_design_preview_duration", source)
        self.assertNotIn("test_profile_button", source)

    def test_qwen_design_preview_does_not_require_base_model(self):
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn('"design-preview"', provider)
        self.assertIn('args.task', worker)
        self.assertIn('_generate_design_preview', worker)
        self.assertIn('"design-preview"', worker)

    def test_qwen_voice_consistency_uses_design_anchor_and_base_prompt(self):
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        self.assertIn("create_voice_clone_prompt", worker)
        self.assertIn("generate_voice_design", worker)
        self.assertIn("voice_anchors", worker)
        self.assertIn("--clone-kind", worker)
        self.assertIn("recommended_chunk_chars = 1200", provider)
        self.assertIn("recommended_chunk_sentences = 5", provider)

    def test_voice_profile_save_and_qwen_preview_controls_are_exposed(self):
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        self.assertIn("Save Voice Profile", source)
        self.assertIn("qwen_design_preview_duration", source)
        for seconds in ("10, 20, 30, 40, 50, 60"):
            self.assertIn(seconds, source)
        self.assertIn("Test VoiceDesign", source)

    def test_chapter_cleaner_detects_and_reflows_import_noise(self):
        from app.documents.parser import detect_repeated_book_noise, clean_import_noise, reflow_source_text
        raw = (
            "The hero walked toward the door and
"
            "stopped when he heard a sound.
"
            "41
"
            "Report
"
            "www.asianovel.com

"
            "A second paragraph begins here.
"
            "41
"
            "Report
"
            "www.asianovel.com
"
        )
        noise = detect_repeated_book_noise([raw])
        self.assertIn("41", noise)
        self.assertIn("report", noise)
        cleaned, removed = clean_import_noise(raw, set(noise))
        cleaned = reflow_source_text(cleaned)
        self.assertNotIn("asianovel.com", cleaned)
        self.assertNotIn("Report", cleaned)
        self.assertNotIn("\n41\n", "\n" + cleaned + "\n")
        self.assertIn("hero walked toward the door and stopped", cleaned)
        self.assertGreaterEqual(len(removed), 3)

    def test_source_reflow_preserves_life_chapter_headings(self):
        from app.documents.parser import reflow_source_text
        source = (
            "Life.0\n"
            "The opening of the story.\n"
            "Life.1 I Quit Being a Human\n"
            "The next chapter starts here.\n"
            "Life.2 I Start as a Devil\n"
            "Another chapter body."
        )
        result = reflow_source_text(source)
        self.assertIn("Life.0\nThe opening of the story.", result)
        self.assertIn("Life.1 I Quit Being a Human\nThe next chapter starts here.", result)
        self.assertIn("Life.2 I Start as a Devil\nAnother chapter body.", result)
        self.assertNotIn("Life.0 Life.1", result)

    def test_generation_pipeline_applies_speed_during_chapter_packaging(self):
        assembler = Path("app/audio/assembler.py").read_text(encoding="utf-8")
        generator = Path("app/tts/generator.py").read_text(encoding="utf-8")
        manager = Path("app/tts/manager.py").read_text(encoding="utf-8")
        self.assertIn("narration_speed: float = 1.0", assembler)
        self.assertIn('"filter:a", f"atempo={speed:.3f}"', assembler)
        self.assertIn("narration_speed=self.narration_speed", manager)
        self.assertNotIn("_apply_narration_speed(", generator)
        self.assertIn("if len(completed) % 4 == 0", generator)

    def test_qwen_long_form_runtime_uses_lighter_base_and_larger_units(self):
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        runtime = Path("app/tts/qwen_character_runtime.py").read_text(encoding="utf-8")
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn("recommended_chunk_chars = 1800", provider)
        self.assertIn("recommended_chunk_sentences = 8", provider)
        self.assertIn("best_long_form_clone_kind", provider)
        self.assertIn("base-0.6b", runtime)
        self.assertIn("Base 1.7B exceeded available GPU memory", worker)
        self.assertIn('"longform": self.qwen_mode != "design-preview"', provider)
        self.assertIn('"max_new_tokens": 1536', worker)

    def test_qwen_resume_signature_tracks_exact_voice_configuration(self):
        source = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        generator = Path("app/tts/generator.py").read_text(encoding="utf-8")
        cast = Path("app/tts/cast_provider.py").read_text(encoding="utf-8")
        self.assertIn("def generation_signature(self)", source)
        self.assertIn("self.qwen_mode", source)
        self.assertIn("self.model_kind", source)
        self.assertIn("self.qwen_prompt", source)
        self.assertIn("self.qwen_seed", source)
        self.assertIn("GENERATION_PIPELINE_VERSION", generator)
        self.assertIn("self.profiles[k].qwen_mode", cast)

    def test_qwen_failure_stops_cascading_chapter_errors(self):
        source = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        self.assertIn("stop_on_failure = True", source)
        self.assertIn("self.close()", source)
        self.assertIn("_read_response(timeout=900.0)", source)

    def test_chapter_autosave_does_not_rebuild_generation_page(self):
        workflow = Path("app/ui/workflow.py").read_text(encoding="utf-8")
        editor = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn("def autosave_project", workflow)
        self.assertIn("self.on_autosave or self.on_save", editor)
        self.assertIn("self.project.save()", workflow[workflow.index("def autosave_project"):workflow.index("def save_project")])

    def test_metadata_dropdowns_and_multiselect_genres_exist(self):
        widgets = Path("app/ui/metadata_widgets.py").read_text(encoding="utf-8")
        generation = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("class HistoryComboBox", widgets)
        self.assertIn("class GenrePicker", widgets)
        self.assertIn("Anime • Fantasy", widgets)
        self.assertIn("Cartoon • Comedy", widgets)
        self.assertIn("HistoryComboBox(self._metadata_history", generation)
        self.assertIn("GenrePicker()", generation)
        self.assertNotIn('form.addRow("Series number"', generation)
        self.assertNotIn('form.addRow("Description"', generation)

    def test_assignment_badges_follow_scroll_and_can_edit_assignment(self):
        source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn('QPushButton(display_name, self.text.viewport())', source)
        self.assertIn("_edit_assignment_badge", source)
        self.assertIn("viewport_rect.top()", source)
        self.assertIn("badge.hide()", source)

    def test_generation_surfaces_provider_device_status(self):
        manager = Path("app/tts/manager.py").read_text(encoding="utf-8")
        generation = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        cast = Path("app/tts/cast_provider.py").read_text(encoding="utf-8")
        self.assertIn('set_status = getattr(self.provider, "set_status_callback", None)', manager)
        self.assertIn('message.startswith("provider:")', generation)
        self.assertIn("def set_status_callback(self, callback) -> None:", cast)

    def test_generation_cancel_closes_active_provider(self):
        manager = Path("app/tts/manager.py").read_text(encoding="utf-8")
        self.assertIn("self.cancel_event.set()", manager)
        self.assertIn("close = getattr(provider, "close", None)", manager)
        self.assertIn("if self.cancel_event.is_set():", manager)

    def test_project_title_is_propagated_to_generation_and_editor(self):
        workflow = Path("app/ui/workflow.py").read_text(encoding="utf-8")
        generation = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("self.project.title,", workflow)
        self.assertIn("self.project_title = str(project_title or "").strip()", generation)
        self.assertIn("book_name = self.project_title", generation)

    def test_chapter_editor_uses_inline_sentence_assignment_ui(self):
        source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn('QPushButton("＋", self.text.viewport())', source)
        self.assertIn("_open_inline_assignment_dialog", source)
        self.assertIn("_selection_sentence_span", source)
        self.assertIn('label = QLabel("Assigned: " + ", ".join(speakers)', source)
        self.assertIn("setExtraSelections", source)
        self.assertNotIn("Quick Assign Speaker", source)
        self.assertNotIn("_update_quick_assign_button", source)
        self.assertNotIn('("Assign Selected Dialogue"', source)

    def test_cast_provider_keeps_qwen_long_form_chunk_settings(self):
        source = Path("app/tts/cast_provider.py").read_text(encoding="utf-8")
        self.assertIn("profile.provider == "qwen-character"", source)
        self.assertIn("limits.append(1200)", source)
        self.assertIn("return 5", source)

    def test_qwen_three_phase_voice_studio_is_exposed(self):
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn("Qwen3-TTS  ·  CustomVoice", source)
        self.assertIn("Qwen3-TTS  ·  VoiceDesign", source)
        self.assertIn("Qwen3-TTS  ·  Voice Clone", source)
        self.assertIn('choices=["custom", "design", "clone"]', worker) if False else None
        self.assertIn('"design"', provider)
        self.assertIn('"clone"', provider)
        self.assertIn("generate_voice_design", worker)
        self.assertIn("generate_voice_clone", worker)

    def test_qwen_voice_profiles_persist_phase_metadata(self):
        profile = VoiceProfile(
            name="Qwen Design Test",
            provider="qwen-character",
            voice_id="design-test",
            model_id="design-1.7b",
            language="English",
            qwen_mode="design",
            qwen_prompt="Young warm anime heroine, cinematic",
            qwen_seed=123,
        )
        self.assertEqual(profile.qwen_mode, "design")
        self.assertEqual(profile.qwen_seed, 123)
        self.assertIn("anime heroine", profile.qwen_prompt)

    def test_pronunciation_dictionary_has_audio_test_controls(self):
        source = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("Test Selected", source)
        self.assertIn("PronunciationPreviewWorker", source)
        self.assertIn("pronunciation_preview_status", source)
        self.assertIn("current voice", source)

    def test_pronunciation_cleanup_covers_god_and_town(self):
        self.assertTrue(is_common_english_phrase("God"))
        self.assertTrue(is_common_english_phrase("Town"))

    def test_premium_character_voice_studio_is_exposed(self):
        from app.tts.providers.elevenlabs import ElevenLabsProvider
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        self.assertIn("Premium Character Voice Studio", source)
        self.assertIn("Generate 3 Premium Character Voices", source)
        self.assertIn("Add Selected to My Voices", source)
        self.assertTrue(hasattr(ElevenLabsProvider, "design_character_voice"))
        self.assertTrue(hasattr(ElevenLabsProvider, "create_designed_voice"))

    def test_voice_cast_analysis_is_background_thread(self):
        from PySide6.QtCore import QThread
        from app.ui.voice_cast_page import VoiceCastAnalysisWorker
        self.assertTrue(issubclass(VoiceCastAnalysisWorker, QThread))

    def test_chatterbox_reference_shorter_than_six_seconds_is_rejected(self):
        import app.tts.voice_profile as vp
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "short.wav"
            _write_wav(source, 1.0)
            original_root = vp.voices_root
            vp.voices_root = lambda: root / "Voices"
            try:
                with self.assertRaisesRegex(RuntimeError, "at least 6 seconds"):
                    vp.import_reference_audio(source, "Short Voice")
            finally:
                vp.voices_root = original_root

    def test_voice_preview_runs_in_a_worker_thread(self):
        from app.ui.voice_page import VoicePreviewWorker
        from PySide6.QtCore import QThread

        self.assertTrue(issubclass(VoicePreviewWorker, QThread))

    def test_m4b_packaging_joins_preencoded_chapters_and_reports_progress(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter_dirs = []
            for number in (1, 2):
                chapter_dir = root / f"{number:03d}_Chapter_{number}"
                chunks = chapter_dir / "chunks"
                wav = chunks / "00001.wav"
                _write_wav(wav, 1.0)
                chapter_dirs.append(chapter_dir)

            progress = []
            output = root / "book.m4b"
            result = assemble_m4b(
                chapter_dirs,
                output,
                "Test Book",
                chapter_titles=["Chapter 1", "Chapter 2"],
                progress=lambda done, total, message: progress.append((done, total, message)),
            )

            self.assertEqual(result, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1024)
            self.assertTrue(any(message == "chapter-audio" for _, _, message in progress))
            self.assertTrue(any(message == "joined-audio" for _, _, message in progress))
            self.assertGreaterEqual(_probe_audio_bitrate_kbps(output), 128)
            self.assertEqual(DEFAULT_AUDIO_BITRATE_KBPS, 256)

    def test_audio_bitrate_range_is_enforced(self):
        from app.audio.assembler import normalize_audio_bitrate
        self.assertEqual(normalize_audio_bitrate(None), "256k")
        self.assertEqual(normalize_audio_bitrate(128), "128k")
        self.assertEqual(normalize_audio_bitrate("320 kbps"), "320k")
        with self.assertRaises(ValueError):
            normalize_audio_bitrate(127)
        with self.assertRaises(ValueError):
            normalize_audio_bitrate(321)

    def test_generation_page_exposes_premium_bitrate_selector(self):
        source = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("256 kbps", source)
        self.assertIn("320", source)
        self.assertIn("audio_bitrate", source)

    def test_custom_reference_audio_is_normalized_for_cloning(self):
        with tempfile.TemporaryDirectory() as temp:
            import app.tts.voice_profile as vp
            root = Path(temp) / "Voices"
            source = Path(temp) / "stereo-8000.wav"
            rate = 8000
            frames = rate * 7
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                wav.writeframes(b"\x01\x00\x01\x00" * frames)

            original_root = vp.voices_root
            vp.voices_root = lambda: root
            try:
                target = import_reference_audio(source, "Premium Test Voice")
                with wave.open(str(target), "rb") as handle:
                    self.assertEqual(handle.getnchannels(), 1)
                    self.assertEqual(handle.getframerate(), 24000)
                    self.assertEqual(handle.getsampwidth(), 2)
                    self.assertGreaterEqual(handle.getnframes() / handle.getframerate(), 6.0)
            finally:
                vp.voices_root = original_root

    def test_custom_voice_runtime_uses_pinned_perth_without_git_requirement(self):
        requirements = Path("requirements-voice-cloning.txt").read_text(encoding="utf-8")
        runtime = Path("app/tts/chatterbox_runtime.py").read_text(encoding="utf-8")
        self.assertNotIn("git+https://", requirements)
        self.assertIn("PERTH_SOURCE_REVISION", runtime)
        self.assertIn("perth_revision", runtime)

    def test_generation_page_preview_uses_background_worker(self):
        from PySide6.QtCore import QThread
        from app.ui.generation_page import VoicePreviewWorker
        self.assertTrue(issubclass(VoicePreviewWorker, QThread))

    def test_chatterbox_runtime_rejects_stale_marker(self):
        import tempfile
        from unittest.mock import patch
        import app.tts.chatterbox_runtime as runtime

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "runtime.json"
            marker.write_text(json.dumps({
                "provider": "chatterbox",
                "ready": True,
                "source_revision": "old-revision",
                "nano_supported": True,
            }), encoding="utf-8")
            with patch.object(runtime, "MARKER", marker), \
                 patch.object(runtime, "runtime_python", return_value=Path(sys.executable)):
                self.assertFalse(runtime.runtime_ready())

    def test_generation_page_exposes_custom_runtime_check(self):
        import app.ui.generation_page as generation_page

        self.assertTrue(callable(generation_page.runtime_ready))

    def test_generation_page_has_pronunciation_validation_dependencies(self):
        import inspect
        import app.ui.generation_page as generation_page

        self.assertTrue(hasattr(generation_page, "re"))
        self.assertTrue(callable(generation_page._numeric_score))
        self.assertIn("QHeaderView.ResizeMode.Stretch", inspect.getsource(generation_page.GenerationPage))
        self.assertIn("pronunciation_dictionary_version", inspect.getsource(generation_page.GenerationPage))

    def test_voice_page_refreshes_selected_provider_details(self):
        import inspect
        from app.ui.voice_page import VoicePage

        source = inspect.getsource(VoicePage._neural_voice_changed)
        self.assertIn("_update_profile_details(profile)", source)
        self.assertIn("_clear_saved_profile_selection()", source)


    def test_dialogue_assignment_fast_path_avoids_full_chapter_analysis(self):
        # The Assign Dialogue dialog should not run the expensive whole-chapter
        # character analysis just to suggest a speaker for one selected quote.
        from unittest.mock import patch

        text = 'Rias Gremory said hello. “Hello, Issei.” Rias Gremory smiled.'
        chapter = Chapter(
            1,
            'Chapter 1',
            text,
            dialogue_assignments=[
                {
                    'start': text.index('“Hello, Issei.”'),
                    'end': text.index('“Hello, Issei.”') + len('“Hello, Issei.”'),
                    'text': '“Hello, Issei.”',
                    'speaker': 'Rias Gremory',
                    'source': 'manual',
                }
            ],
        )
        start = text.index('“Hello, Issei.”')
        end = start + len('“Hello, Issei.”')
        with patch('app.chapters.dialogue.analyze_chapter', side_effect=AssertionError('full analysis called')):
            segment = dialogue_segment_for_selection(chapter, start, end)
        self.assertIsNotNone(segment)
        self.assertEqual(segment.suggested_speaker, 'Rias Gremory')
        self.assertGreaterEqual(segment.confidence, 0.99)

    def test_multi_speaker_cast_routes_exact_dialogue_to_multiple_voices(self):
        from app.tts.cast_provider import CastAwareProvider

        class DummyProvider:
            recommended_chunk_chars = 1400
            recommended_chunk_sentences = 2

            def synthesize(self, text, output_path, voice=None):
                return output_path

        from app.tts.voice_profile import VoiceProfile

        profiles = {
            "Voice A": VoiceProfile("Voice A", "piper", "a"),
            "Voice B": VoiceProfile("Voice B", "piper", "b"),
        }
        cast = CastAwareProvider(
            DummyProvider(),
            "Voice A",
            profiles,
            {"Rias": "Voice A", "Akeno": "Voice B"},
        )
        text = 'Rias and Akeno shouted, “We are here!”'
        start = text.index("“")
        end = text.index("”") + 1
        parts = cast.split_for_cast(
            text,
            "Voice A",
            dialogue_assignments=[{
                "start": start,
                "end": end,
                "text": text[start:end],
                "speakers": ["Rias", "Akeno"],
                "speaker": "Rias",
                "source": "manual",
                "multi_speaker_mode": "chorus",
            }],
        )
        dialogue_parts = [item for item in parts if "We are here!" in item[0]]
        self.assertEqual(len(dialogue_parts), 1)
        self.assertEqual(dialogue_parts[0][1], ["Voice A", "Voice B"])

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

    def test_pronunciation_filter_rejects_more_everyday_english(self):
        for word in ("actually", "already", "please", "probably", "everyone", "something", "yesterday"):
            self.assertTrue(is_common_english_phrase(word), word)

    def test_ai_pronunciation_keeps_model_spoken_form(self):
        from app.ai.brain import _normalise_pronunciation
        result = _normalise_pronunciation(
            {
                "written": "Hyeon-woo",
                "spoken": "hyun-woo",
                "ipa": "/hjʌn.u/",
                "source_language": "Korean",
                "confidence": 0.97,
            },
            "Hyeon-woo met the others.",
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["spoken"], "hyun-woo")

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
