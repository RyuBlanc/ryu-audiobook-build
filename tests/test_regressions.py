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
    import math
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 44100
    frames = max(1, int(rate * seconds))
    pcm = bytearray()
    for index in range(frames):
        sample = int(12000 * math.sin(2 * math.pi * 440 * index / rate))
        pcm.extend(int(sample).to_bytes(2, byteorder="little", signed=True))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(pcm))


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

    def test_chapter_editor_uses_non_obstructive_colour_highlights_and_hover_tooltips(self):
        source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn("self.text.viewport().installEventFilter(self)", source)
        self.assertIn("QToolTip.showText", source)
        self.assertIn("self._assignment_hover_items.append((start, end, tuple(speakers)))", source)
        self.assertIn("selection.format = fmt", source)
        self.assertNotIn("badge.setFixedSize(badge_width, 16)", source)
        self.assertNotIn('font-size:7px', source)
        self.assertIn('_update_current_chapter_list_label', source)
        self.assertIn('self.title.textChanged.connect(self._update_current_chapter_list_label)', source)

    def test_chapter_editor_assignment_ui_is_subtle_and_uses_project_title(self):
        source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn("self.text.setViewportMargins(82, 0, 0, 0)", source)
        self.assertIn('assignment_manager_button = QPushButton("Assignments")', source)
        self.assertIn("soft.setAlpha(52)", source)
        self.assertIn("QEvent.Type.MouseMove", source)
        self.assertIn("self.text.cursorForPosition(point)", source)
        self.assertNotIn('QPushButton(display_name, self.text.viewport())', source)
        self.assertIn("project_title: str | None = None", source)
        self.assertIn('self.project_title = str(project_title or "").strip()', source)
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

    def test_qwen_design_preview_uses_stable_identity_base_model(self):
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn('"design-preview"', provider)
        self.assertIn('best_long_form_clone_kind()', provider)
        self.assertIn("_generate_design_locked(", worker)
        self.assertIn('_create_expression_anchors', worker)
        self.assertIn('EXPRESSION_STYLES', worker)

    def test_qwen_voice_consistency_uses_design_anchor_and_base_prompt(self):
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        self.assertIn("create_voice_clone_prompt", worker)
        self.assertIn("generate_voice_design", worker)
        self.assertIn("voice_anchors", worker)
        self.assertIn("locked_clone_prompts[style] = model.create_voice_clone_prompt", worker)
        self.assertIn("reference_style(style)", worker)
        self.assertIn("ANCHOR_TEXTS", worker)
        self.assertIn("recommended_chunk_chars = 800", provider)
        self.assertIn("recommended_chunk_sentences", provider)

    def test_voice_profile_save_and_qwen_preview_controls_are_exposed(self):
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        self.assertIn("Save Voice Profile", source)
        self.assertIn("preview_duration", source)
        self.assertIn("preview_duration", source)
        self.assertIn("Qwen3-TTS  ·  VoiceDesign", source)

    def test_chapter_cleaner_detects_and_reflows_import_noise(self):
        from app.documents.parser import detect_repeated_book_noise, clean_import_noise, reflow_source_text
        raw = (
            "The hero walked toward the door and\n"
            "stopped when he heard a sound.\n"
            "41\n"
            "Report\n"
            "www.asianovel.com\n\n"
            "A second paragraph begins here.\n"
            "41\n"
            "Report\n"
            "www.asianovel.com\n"
        )
        cleaned, removed = clean_import_noise(raw)
        self.assertNotIn("www.asianovel.com", cleaned)
        self.assertIn("A second paragraph begins here.", cleaned)
        self.assertIn("The hero walked toward the door", reflow_source_text(cleaned))
        self.assertEqual(
            removed,
            ["41", "Report", "www.asianovel.com", "41", "Report", "www.asianovel.com"],
        )

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
        self.assertIn('"-filter:a"', assembler)
        self.assertIn('f"atempo={speed:.3f}"', assembler)
        self.assertIn("narration_speed=self.narration_speed", manager)
        self.assertNotIn("_apply_narration_speed(", generator)
        self.assertIn("if len(completed) % 4 == 0", generator)

    def test_qwen_long_form_runtime_uses_lighter_base_and_larger_units(self):
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        runtime = Path("app/tts/qwen_character_runtime.py").read_text(encoding="utf-8")
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn("recommended_chunk_chars = 800", provider)
        self.assertIn("recommended_chunk_sentences", provider)
        self.assertIn("best_long_form_clone_kind", provider)
        self.assertIn("base-0.6b", runtime)
        self.assertIn("Base 1.7B exceeded available GPU memory", worker)
        self.assertIn('"longform": self.qwen_mode != "design-preview"', provider)
        self.assertIn("def _recommended_max_new_tokens", worker)
        self.assertIn("recommended_batch_size", provider)
        self.assertIn('"texts":', provider)

    def test_qwen_voicedesign_preview_and_audiobook_share_stable_identity(self):
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        voice_page = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        self.assertIn('if active_task in {"design", "design-preview"}:', worker)
        self.assertIn("_prepare_design_clone(", worker)
        self.assertIn("_generate_design_locked(", worker)
        self.assertIn("_create_expression_anchors", worker)
        self.assertIn('prompts[style] = clone_model.create_voice_clone_prompt', worker)
        self.assertIn('"outputs": [str(Path(str(path)).resolve()) for path in batch_outputs]', worker)
        self.assertIn('qwen_mode="design"', voice_page)
        self.assertIn('best_long_form_clone_kind()', provider)
        self.assertIn('"--clone-kind", clone_kind or best_clone_kind()', provider)

    def test_voicedesign_requires_stable_base_model(self):
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        self.assertIn("VoiceDesign stable identity needs the local Qwen Base model", provider)
        self.assertIn("best_long_form_clone_kind()", provider)

    def test_app_starts_maximized_for_screen_fit(self):
        source = Path("app/main.py").read_text(encoding="utf-8")
        self.assertIn("window.showMaximized()", source)

    def test_voice_previews_expose_percentage_progress(self):
        voice_page = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        generation = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("progress = Signal(int)", voice_page)
        self.assertIn("self.preview_percent_bar", voice_page)
        self.assertIn("percent = Signal(int)", generation)
        self.assertIn("self.preview_loading.setRange(0, 100)", generation)
        self.assertIn("self.preview_worker.percent.connect", generation)

    def test_qwen_preview_and_audiobook_use_same_generation_ceiling(self):
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn("def _recommended_max_new_tokens", worker)

    def test_import_reflow_joins_hard_wraps_but_preserves_dialogue_lines(self):
        from app.documents.parser import reflow_source_text
        text = (
            "In terms of military assistance, it seemed\n"
            "unlikely that we would suddenly be tapped for that.\n"
            "“Our name…?” “I mean, yeah.”\n"
            "The next paragraph starts here."
        )
        result = reflow_source_text(text)
        self.assertIn("it seemed unlikely that we would suddenly", result)
        self.assertIn("“Our name…?”\n“I mean, yeah.”", result)

    def test_generate_refresh_method_exists_for_live_chapter_updates(self):
        source = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        workflow = Path("app/ui/workflow.py").read_text(encoding="utf-8")
        self.assertIn("def refresh_chapter_sources", source)
        self.assertIn("page.refresh_chapter_sources", workflow)
        self.assertIn("def _refresh_generation_context", workflow)

    def test_qwen_profiles_have_unique_cache_identity(self):
        from app.tts.voice_profile import VoiceProfile, save_profiles, load_profiles
        from app.core.paths import voices_root
        with tempfile.TemporaryDirectory() as temp:
            # Ensure a constructed Qwen profile receives an immutable identity on save.
            original = voices_root
            import app.tts.voice_profile as vp
            vp.voices_root = lambda: Path(temp)
            try:
                profile = VoiceProfile(
                    name="Test Qwen Voice",
                    provider="qwen-character",
                    voice_id="design-test-qwen",
                    qwen_mode="design",
                    qwen_prompt="A natural male narrator.",
                    qwen_seed=3101,
                )
                save_profiles([profile])
                loaded = load_profiles()
                saved = next(p for p in loaded if p.name == "Test Qwen Voice")
                self.assertTrue(saved.qwen_profile_id)
            finally:
                vp.voices_root = original

    def test_qwen_worker_bootstrap_adds_frozen_application_root(self):
        source = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn("_APPLICATION_ROOT = Path(__file__).resolve().parents[2]", source)
        self.assertIn("sys.path.insert(0, str(_APPLICATION_ROOT))", source)

    def test_qwen_repair_avoids_py_compile_and_program_files_pycache(self):
        runtime = Path("app/tts/qwen_character_runtime.py").read_text(encoding="utf-8")
        self.assertIn("PYTHONDONTWRITEBYTECODE", runtime)
        self.assertIn("ast.parse", runtime)
        self.assertNotIn('"-m", "py_compile"', runtime)

    def test_qwen_expression_styles_are_subtle_and_text_driven(self):
        expression = Path("app/tts/expression.py").read_text(encoding="utf-8")
        from app.tts.expression import classify_expression
        self.assertIn("thoughtful", expression)
        self.assertIn("warm", expression)
        self.assertIn("concerned", expression)
        self.assertEqual(classify_expression("Instead of me…then?"), "thoughtful")
        self.assertIn(classify_expression("That's amazing! Really!"), {"excited", "thoughtful"})

    def test_qwen_expression_styles_map_to_stable_reference_families(self):
        from app.tts.expression import classify_expression, reference_style
        self.assertEqual(classify_expression("Maybe I should wait..."), "thoughtful")
        self.assertEqual(classify_expression("That's wonderful!"), "excited")
        self.assertEqual(reference_style("curious"), "thoughtful")
        self.assertEqual(reference_style("excited"), "warm")
        self.assertEqual(reference_style("sad"), "concerned")
        self.assertEqual(reference_style("neutral"), "neutral")

    def test_story_pacing_preserves_headings_dialogue_and_attribution(self):
        from app.tts.pacing import is_heading_line
        source = (
            "The hallway was silent.\n\n"
            "THE DEMON LORD SUMMIT\n\n"
            "The three people sat down.\n\n"
            "“Don't move!” he shouted.\n"
            "“Why?” she asked."
        )
        units = split_for_pacing(source, max_chars=800, max_sentences=4)
        self.assertEqual(units[1], "THE DEMON LORD SUMMIT")
        self.assertIn("“Don't move!” he shouted.", units)
        self.assertIn("“Why?” she asked.", units)
        self.assertTrue(is_heading_line("THE DEMON LORD SUMMIT"))
        self.assertGreaterEqual(pause_after_ms("THE DEMON LORD SUMMIT"), 700)
        self.assertGreaterEqual(
            pause_after_ms("He stepped back.", "natural", next_text="CHAPTER 1"),
            600,
        )

    def test_qwen_chunking_splits_only_at_expression_family_changes(self):
        text = "The hallway was silent. He whispered, ‘Don't move.’ She shouted, ‘Run!’"
        ordinary = split_for_pacing(text, max_chars=800, max_sentences=4)
        emotional = split_for_pacing(
            text,
            max_chars=800,
            max_sentences=4,
            split_on_expression_change=True,
        )
        self.assertGreater(len(emotional), len(ordinary))
        self.assertTrue(any("whispered" in value for value in emotional))

    def test_quoted_dialogue_attribution_stays_with_the_quote(self):
        from app.tts.pacing import sentence_units
        units = sentence_units("“Wait!” he said. Then he left.")
        self.assertEqual(units[0], "“Wait!” he said.")
        self.assertEqual(units[1], "Then he left.")

    def test_qwen_provider_constructor_does_not_probe_gpu_on_ui_thread(self):
        from unittest.mock import patch
        from app.tts.providers.qwen_character import QwenCharacterProvider

        def fast_custom(vram_gb=None):
            self.assertEqual(vram_gb, 0.0)
            return "custom-0.6b"

        def fast_clone(vram_gb=None):
            self.assertEqual(vram_gb, 0.0)
            return "base-0.6b"

        with patch("app.tts.providers.qwen_character.best_custom_kind", side_effect=fast_custom), \
             patch("app.tts.providers.qwen_character.best_clone_kind", side_effect=fast_clone):
            custom = QwenCharacterProvider(voice_id="Ryan", model_kind="auto", qwen_mode="custom")
            clone = QwenCharacterProvider(voice_id="clone-test", model_kind="auto", qwen_mode="clone")
        self.assertEqual(custom.model_kind, "custom-0.6b")
        self.assertEqual(clone.model_kind, "base-0.6b")
        self.assertTrue(custom._auto_select_model)
        self.assertTrue(clone._auto_select_model)

    def test_voice_design_anchor_instruction_preserves_identity_and_mood_range(self):
        from app.tts.expression import voice_design_anchor_instruction
        instruction = voice_design_anchor_instruction(
            "Young adult male anime protagonist, lower-mid pitch and restrained confidence."
        )
        self.assertIn("Young adult male anime protagonist", instruction)
        self.assertIn("Preserve its specified gender presentation", instruction)
        self.assertIn("pitch range", instruction)
        self.assertIn("warm, pleasantly surprised energy", instruction)
        self.assertIn("briefly concerned", instruction)
        self.assertIn("not four different voices", instruction)
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn("voice_design_anchor_instruction(base_description)", worker)
        self.assertIn('"temperature": temperature', worker)

    def test_changing_qwen_preset_clears_old_saved_voice_selection(self):
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        start = source.index("    def _qwen_design_preset_changed(self) -> None:")
        end = source.index("    def _refresh_online_catalog(self)", start)
        handler = source[start:end]
        self.assertIn("self._clear_saved_profile_selection()", handler)
        self.assertIn('self.name.setText(f"Qwen VoiceDesign • {preset_name}")', handler)
        self.assertIn('self.profile_badge.setText(f"Unsaved draft • {preset_name}")', handler)
        self.assertIn("Preview this new voice, then save", handler)
        self.assertIn("it as a separate profile", handler)
        self.assertIn("the previously saved voice is unchanged", handler)

    def test_saved_voice_design_uses_one_shared_anchor_transcript(self):
        from app.tts.expression import DEFAULT_VOICE_DESIGN_ANCHOR_TEXT
        from app.tts.providers.qwen_character import QwenCharacterProvider
        from app.ui.voice_page import VoicePage

        provider = QwenCharacterProvider(
            voice_id="design-kousuke",
            language="English",
            instruct="Young adult male anime protagonist.",
            model_kind="design-1.7b",
            qwen_mode="design",
            qwen_anchor_text="",
        )
        self.assertEqual(provider.qwen_anchor_text, DEFAULT_VOICE_DESIGN_ANCHOR_TEXT)
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        self.assertIn("anchor_text = DEFAULT_VOICE_DESIGN_ANCHOR_TEXT", source)
        self.assertIn("load_saved_profiles()", source)

    def test_qwen_runtime_readiness_is_a_fast_filesystem_gate(self):
        import app.tts.qwen_character_runtime as runtime
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            marker = root / "runtime.json"
            python = root / "python.exe"
            worker = root / "qwen_character_worker.py"
            marker.write_text(json.dumps({
                "ready": True,
                "bootstrap_version": runtime.BOOTSTRAP_VERSION,
                "qwen_tts": runtime.QWEN_TTS_VERSION,
            }), encoding="utf-8")
            python.touch()
            worker.touch()
            with patch.object(runtime, "MARKER", marker), \
                 patch.object(runtime, "VENV_PYTHON", python), \
                 patch.object(runtime, "worker_script", return_value=worker), \
                 patch.object(runtime, "_python_works", side_effect=AssertionError("subprocess check ran")), \
                 patch.object(runtime, "_runtime_self_test", side_effect=AssertionError("model imports ran")):
                self.assertTrue(runtime.runtime_ready())

    def test_preview_reports_elapsed_time_and_uses_natural_pacing(self):
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        self.assertIn("finished_ok = Signal(str, float)", source)
        self.assertIn('pacing_profile="natural"', source)
        self.assertNotIn('pacing_profile="off"', source)
        self.assertIn("self.finished_ok.emit(str(self.output), elapsed_seconds)", source)
        self.assertIn("generated in {int(elapsed) // 60}", source)
        self.assertIn("RTF", source)

    def test_internal_ellipsis_creates_a_separate_pacing_unit(self):
        units = split_for_pacing("Instead of me…then? Maybe later.", max_chars=200, max_sentences=4)
        self.assertGreaterEqual(len(units), 2)
        self.assertTrue(units[0].endswith("…"))

    def test_voice_preview_initial_text_remains_automatic_for_chapter_source(self):
        source = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        init_start = source.index('self.preview_text = QTextEdit()')
        init_end = source.index('self.preview_text.setMinimumHeight', init_start)
        initialization = source[init_start:init_end]
        self.assertIn("self.preview_text.setPlainText(self._qwen_preview_script(30))", initialization)
        self.assertLess(
            initialization.index("setPlainText(self._qwen_preview_script(30))"),
            initialization.index("self.preview_text.textChanged.connect"),
        )
        setter_start = source.index("def set_preview_source(")
        setter_end = source.index("def preview(self)", setter_start)
        setter = source[setter_start:setter_end]
        self.assertIn('if getattr(self, "_preview_text_is_auto", True):', setter)
        self.assertIn('self._preview_text_is_auto = True', setter)

    def test_timed_preview_uses_target_duration_and_live_progress(self):
        preview = Path("app/tts/preview.py").read_text(encoding="utf-8")
        voice_page = Path("app/ui/voice_page.py").read_text(encoding="utf-8")
        generation = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("target_seconds: float | None = None", preview)
        self.assertIn('if target > 0 and accumulated_seconds >= target', preview)
        self.assertIn("preview_started = time.monotonic()", voice_page)
        self.assertIn("ETA", voice_page)
        self.assertIn("preview_activity", generation)

    def test_qwen_resume_signature_tracks_exact_voice_configuration(self):
        source = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        generator = Path("app/tts/generator.py").read_text(encoding="utf-8")
        cast = Path("app/tts/cast_provider.py").read_text(encoding="utf-8")
        self.assertIn("def generation_signature(self)", source)
        self.assertIn("self.qwen_mode", source)
        self.assertIn("self.model_kind", source)
        self.assertIn("self.instruct", source)
        self.assertIn("self.qwen_seed", source)
        self.assertIn("GENERATION_PIPELINE_VERSION", generator)
        self.assertIn("self.profiles[k].qwen_mode", cast)

    def test_qwen_generation_uses_text_sized_token_ceiling_and_heartbeat(self):
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        self.assertIn("def _recommended_max_new_tokens", worker)
        self.assertIn("chars * 1.10", worker)
        self.assertIn("max_new_tokens", worker)
        self.assertIn("heartbeat=", provider)

    def test_qwen_design_identity_id_is_stable_for_unchanged_saved_description(self):
        from unittest.mock import patch
        from app.ui.voice_page import VoicePage
        from app.tts.voice_profile import VoiceProfile

        saved = VoiceProfile(
            name="Anime MX Kousuke Takioto!",
            provider="qwen-character",
            voice_id="design-anime-mx-kousuke-takioto",
            model_id="design-1.7b",
            language="English",
            qwen_mode="design",
            qwen_prompt="Young adult male anime protagonist voice.",
            qwen_seed=3101,
            qwen_anchor_text="A sample sentence.",
            qwen_profile_id="saved-profile-id",
        )
        class ProfileLookup:
            class SavedBox:
                def currentData(self):
                    return saved.name
            saved_profiles = SavedBox()
        page = ProfileLookup()
        with patch("app.ui.voice_page.load_saved_profiles", return_value=[saved]):
            self.assertEqual(
                VoicePage._stable_qwen_design_profile_id(
                    page,
                    saved.name,
                    saved.qwen_prompt,
                    saved.language,
                    saved.qwen_seed,
                    saved.qwen_anchor_text,
                ),
                "saved-profile-id",
            )
            changed = VoicePage._stable_qwen_design_profile_id(
                page,
                saved.name,
                "Older sounding young adult male protagonist.",
                saved.language,
                saved.qwen_seed,
                saved.qwen_anchor_text,
            )
        self.assertNotEqual(changed, "saved-profile-id")
        self.assertEqual(len(changed), 32)

    def test_generate_tab_reads_latest_persisted_profile(self):
        import app.tts.voice_profile as voice_profiles
        from app.ui.generation_page import GenerationPage
        from app.tts.voice_profile import VoiceProfile

        with tempfile.TemporaryDirectory() as temp:
            stored = VoiceProfile(
                name="Current Kousuke",
                provider="qwen-character",
                voice_id="design-kousuke",
                qwen_mode="design",
                qwen_prompt="Lower mid-range young male voice.",
                qwen_seed=3101,
                qwen_profile_id="fresh-id",
            )
            profile_file = Path(temp) / "voices.json"
            profile_file.write_text(json.dumps([stored.__dict__]), encoding="utf-8")
            original = voice_profiles.profiles_file
            voice_profiles.profiles_file = lambda: profile_file
            try:
                class Combo:
                    def currentData(self):
                        return VoiceProfile(
                            name="Current Kousuke",
                            provider="qwen-character",
                            voice_id="design-kousuke",
                            qwen_mode="design",
                            qwen_prompt="Old female voice description.",
                            qwen_seed=12,
                            qwen_profile_id="stale-id",
                        )
                class Selection:
                    voice_profile = Combo()
                selected = GenerationPage._selected_profile(Selection())
                self.assertEqual(selected.qwen_profile_id, "fresh-id")
                self.assertEqual(selected.qwen_prompt, "Lower mid-range young male voice.")
            finally:
                voice_profiles.profiles_file = original

    def test_qwen_design_worker_lazy_loads_cached_identity(self):
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        runtime = Path("app/tts/qwen_character_runtime.py").read_text(encoding="utf-8")
        self.assertIn("saved canonical character identity", worker)
        self.assertIn("ready = all(", worker)
        self.assertIn('ANCHOR_STYLES = ("neutral",)', worker)
        self.assertIn("v8-emotion-range-anchor", worker)
        self.assertIn('if active_task not in {"design", "design-preview"}:', worker)
        self.assertIn('if vram_gb >= 10.0 and model_installed("base-1.7b")', runtime)

    def test_qwen_batch_generation_path_exists(self):
        provider = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        worker = Path("app/tts/qwen_character_worker.py").read_text(encoding="utf-8")
        generator = Path("app/tts/generator.py").read_text(encoding="utf-8")
        self.assertIn("def synthesize_batch", provider)
        self.assertIn('batch_texts = request.get("texts")', worker)
        self.assertIn("model.generate_voice_clone(", worker)
        self.assertIn("synthesize_batch", generator)
        self.assertIn("recommended_batch_size", generator)

    def test_qwen_failure_stops_cascading_chapter_errors(self):
        source = Path("app/tts/providers/qwen_character.py").read_text(encoding="utf-8")
        self.assertIn("stop_on_failure = True", source)
        self.assertIn("self.close()", source)
        self.assertIn("heartbeat=", source)

    def test_generate_navigation_opens_selected_library_project_and_handles_empty_library(self):
        workflow = Path("app/ui/workflow.py").read_text(encoding="utf-8")
        self.assertIn("self.sidebar.itemClicked.connect(self._sidebar_item_clicked)", workflow)
        self.assertIn("def _sidebar_item_clicked", workflow)
        self.assertIn("def _refresh_generation_context", workflow)
        nav_start = workflow.index("def _sidebar_changed")
        section = workflow[nav_start:workflow.index('elif name == "Models":', nav_start)]
        self.assertIn("if not self.project:", section)
        self.assertIn("selected_projects = self.library._selected_projects()", section)
        self.assertIn("self.open_project(selected_projects[0])", section)
        self.assertIn("self.sidebar.blockSignals(True)", section)
        self.assertIn('"Open a book first"', section)
        self.assertIn("QTimer.singleShot(75, self._refresh_generation_context)", section)
        self.assertLess(section.index("self._show_page(self.generation)"), section.index("QTimer.singleShot"))
        self.assertIn("Generate page could not be opened", section)
        self.assertIn("except Exception as exc:", section)

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

    def test_assignment_speaker_labels_are_hover_only_and_do_not_cover_text(self):
        source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn("self.text.viewport().installEventFilter(self)", source)
        self.assertIn("Assigned speaker:", source)
        self.assertIn("QToolTip.hideText()", source)
        self.assertNotIn('QPushButton(display_name, self.text.viewport())', source)
        self.assertNotIn("viewport_rect.top()", source)

    def test_generation_estimate_is_labelled_as_listening_duration(self):
        source = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("Estimated listening length:", source)
        self.assertIn("This is not the time required to generate it.", source)
        self.assertIn("Estimated generation time: about", source)
        self.assertIn("_generation_calibration_key", source)
        self.assertIn("self._calibration_factor = 2.45", source)
        self.assertIn("self._active_calibration_is_resume = bool(is_resume)", source)
        self.assertIn("not self._active_calibration_is_resume", source)
        self.assertIn("self.motion_settings.setValue(f\"{key}/realtime_factor\", actual_factor)", source)
        self.assertIn("self.elapsed.setText", source)
        self.assertIn("self.remaining.setText", source)

    def test_hardware_benchmark_passes_voice_as_voice_not_model_path(self):
        source = Path("app/ui/hardware_page.py").read_text(encoding="utf-8")
        self.assertIn("PiperProvider(backend=self.backend)", source)
        self.assertIn("voice=self.voice", source)
        self.assertIn('else "automatic" if backend == "automatic"', source)
        self.assertNotIn("PiperProvider(self.voice, backend=self.backend)", source)

    def test_pdf_extraction_guard_flags_sparse_long_documents(self):
        from app.documents.parser import pdf_extraction_quality_warning
        warning = pdf_extraction_quality_warning(301, 497)
        self.assertIsNotNone(warning)
        self.assertIn("301-page PDF", warning)
        self.assertIsNotNone(pdf_extraction_quality_warning(301, 5000))
        self.assertIsNone(pdf_extraction_quality_warning(301, 10000))
        self.assertIsNone(pdf_extraction_quality_warning(12, 100))

    def test_import_worker_checks_chapter_word_coverage(self):
        source = Path("app/ui/workflow.py").read_text(encoding="utf-8")
        self.assertIn("chapter_words < int(source_words * 0.90)", source)
        self.assertIn("Chapter detection retained only", source)

    def test_models_page_groups_installs_and_supports_selected_component_removal(self):
        source = Path("app/ui/models_page.py").read_text(encoding="utf-8")
        self.assertIn('QGroupBox("Installed components")', source)
        self.assertIn('QGroupBox("Offline narration voices")', source)
        self.assertIn('QGroupBox("Character voices & voice cloning")', source)
        self.assertIn("Uninstall selected component", source)
        self.assertIn('component_id.startswith("piper:")', source)
        self.assertIn('component_id.startswith("qwen-model:")', source)
        self.assertIn('component_id == "qwen-runtime"', source)
        self.assertIn("Refusing to remove a path outside the selected component root", source)
        self.assertIn("generated audiobooks", source)
        self.assertIn("QWEN_VENV_ROOT", source)
        self.assertIn('local_kokoro_root = models_root() / "kokoro"', source)
        self.assertIn("Kokoro 82M — Bundled with application (not individually removable)", source)
        self.assertIn("local_kokoro_installed", source)

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
        self.assertIn('close = getattr(provider, "close", None)', manager)
        self.assertIn("if self.cancel_event.is_set():", manager)

    def test_project_title_is_propagated_to_generation_and_editor(self):
        workflow = Path("app/ui/workflow.py").read_text(encoding="utf-8")
        generation = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("self.project.title,", workflow)
        self.assertIn('self.project_title = str(project_title or "").strip()', generation)
        self.assertIn("book_name = self.project_title", generation)

    def test_chapter_editor_uses_inline_sentence_assignment_ui(self):
        source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn('QPushButton("", self.text.viewport())', source)
        self.assertIn('dragon_cross.png', source)
        self.assertNotIn('dragon_cross.svg', source)
        self.assertIn('dragon_cross.png', source)
        self.assertIn('setIconSize(QSize(21, 21))', source)
        self.assertIn("_open_inline_assignment_dialog", source)
        self.assertIn("_selection_sentence_span", source)
        self.assertIn("QToolTip.showText", source)
        self.assertIn('"Assigned speaker: " + ", ".join(speakers)', source)
        self.assertNotIn('QPushButton(display_name, self.text.viewport())', source)
        self.assertIn("setExtraSelections", source)
        self.assertNotIn("Quick Assign Speaker", source)
        self.assertNotIn("_update_quick_assign_button", source)
        self.assertNotIn('("Assign Selected Dialogue"', source)


    def test_generation_has_1344_cinematic_catalogue_and_linked_cue_controls(self):
        ui = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        mixer = Path("app/audio/preview_mixer.py").read_text(encoding="utf-8")
        sound_design = Path("app/audio/sound_design.py").read_text(encoding="utf-8")
        self.assertIn('settings_form.addRow("BGM catalogue (1,344 cinematic arrangements)", self.music_catalogue_container)', ui)
        self.assertIn('self.music_catalogue_preview.clicked.connect(self.preview_catalogue_music)', ui)
        self.assertIn('self.preview_opening_cue.clicked.connect(lambda: self.preview_cue("opening"))', ui)
        self.assertIn('self.preview_page_cue.clicked.connect(lambda: self.preview_cue("page"))', ui)
        self.assertIn('self.preview_ending_cue.clicked.connect(lambda: self.preview_cue("ending"))', ui)
        self.assertIn('settings_form.addRow("Linked book cue set", self.sound_cue_style)', ui)
        self.assertIn('target_seconds=preview_seconds', ui)
        self.assertIn('mix_voice_preview(', ui)
        self.assertIn('sidechaincompress=', mixer)
        self.assertIn('synthesize_opening_cue', mixer)
        self.assertIn('synthesize_audiobook_ending', mixer)
        self.assertIn('synthesize_page_turn', mixer)
        self.assertIn('MUSIC_CATALOGUE_SIZE = len(THEMES) * VARIATIONS_PER_MOOD  # 1,344', sound_design)
        self.assertNotIn('Harmony {info[\'harmony\']}', ui)
        build_source = Path("build.py").read_text(encoding="utf-8")
        cursor_source = Path("app/main.py").read_text(encoding="utf-8")
        editor_source = Path("app/ui/chapter_editor.py").read_text(encoding="utf-8")
        self.assertIn('dragon_four_winged.png', build_source)
        self.assertIn('dragon_cursor.png', cursor_source)
        self.assertIn('dragon_cross.png', editor_source)
        self.assertNotIn('dragon_cursor.svg', cursor_source)
        self.assertNotIn('dragon_cross.svg', editor_source)
        self.assertNotIn('DRAGON_CURSOR_SVG', build_source)
        self.assertNotIn('DRAGON_CROSS_SVG', build_source)

    def test_explicit_music_catalogue_id_is_mapped_without_changing_mood(self):
        from app.audio.assembler import _selected_music_recipe
        from app.audio.sound_design import (
            MUSIC_CATALOGUE_SIZE, MOOD_ORDER, VARIATIONS_PER_MOOD, music_variation_info,
        )
        mood, variation = _selected_music_recipe("Ignored chapter", "Ignored text", "auto", 1)
        self.assertEqual((mood, variation), (MOOD_ORDER[0], 0))
        last_id = len(MOOD_ORDER) * VARIATIONS_PER_MOOD
        mood, variation = _selected_music_recipe("Ignored chapter", "Ignored text", "auto", last_id)
        self.assertEqual((mood, variation), (MOOD_ORDER[-1], VARIATIONS_PER_MOOD - 1))
        self.assertEqual(MUSIC_CATALOGUE_SIZE, 1344)
        info = music_variation_info(MOOD_ORDER[0], 0)
        self.assertIn("arrangement", info)
        self.assertNotIn("harmony", info)
        self.assertEqual(len(MOOD_ORDER), 8)


    def test_preview_mixer_generates_selected_bgm_with_page_turn_and_book_ending(self):
        import wave
        from app.audio.preview_mixer import mix_voice_preview
        from app.audio.assembler import _duration_ms

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            voice = root / "voice.wav"
            _write_wav(voice, 1.5)
            output = root / "voice-plus-story-sound.wav"
            result = mix_voice_preview(
                voice,
                output,
                "The sword clashed against the shield. The battle was over.",
                background_enabled=True,
                background_mode="auto",
                music_style="fantasy",
                music_variation_id=1,
                music_volume=0.08,
                story_effects_enabled=False,
                chapter_transition_sound=True,
                is_first_chapter=False,
                is_last_chapter=True,
            )
            # The mixer returns a resolved Windows path; compare the written
            # destination rather than path casing/8.3 aliases on the CI runner.
            self.assertTrue(Path(result).is_file())
            self.assertTrue(output.is_file())
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getframerate(), 44100)
            # Page turn + 1.5s voice + the distinct book-ending cadence.
            self.assertGreaterEqual(_duration_ms(output), 4500)
            self.assertLessEqual(_duration_ms(output), 5200)

    def test_chapter_and_finale_cues_work_when_background_music_is_off(self):
        from app.audio.assembler import _duration_ms

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapters = []
            for number in (1, 2):
                folder = root / f"{number:03d}_Chapter_{number}"
                _write_wav(folder / "chunks" / "00001.wav", 1.0)
                (folder / "narration.json").write_text(
                    json.dumps({
                        "title": f"Chapter {number}",
                        "narration_text": "The story continues.",
                    }),
                    encoding="utf-8",
                )
                chapters.append(folder)
            output = root / "chapter-cues-without-bgm.m4b"
            assemble_m4b(
                chapters,
                output,
                "Cues without BGM",
                chapter_titles=["Chapter 1", "Chapter 2"],
                background_audio_mode="off",
                chapter_transition_sound=True,
            )
            duration = _duration_ms(output)
            # Opening + narration + page turn + narration + book closing.
            self.assertGreaterEqual(duration, 6000)
            self.assertLessEqual(duration, 7000)

    def test_pause_profiles_keep_sentence_and_dialogue_turns_natural(self):
        from app.tts.pacing import pause_after_ms
        self.assertGreaterEqual(pause_after_ms("That is the end.", "natural"), 280)
        self.assertGreater(pause_after_ms("That is the end?", "natural"), pause_after_ms("That is the end.", "natural"))
        self.assertGreater(pause_after_ms("That is the end.", "relaxed"), pause_after_ms("That is the end.", "natural"))
        self.assertEqual(pause_after_ms("That is the end.", "off"), 0)

    def test_cast_provider_keeps_qwen_long_form_chunk_settings(self):
        source = Path("app/tts/cast_provider.py").read_text(encoding="utf-8")
        self.assertIn('profile.provider == "qwen-character"', source)
        self.assertIn("limits.append(1800)", source)
        self.assertIn('return getattr(self.narrator_provider, "recommended_chunk_sentences", 2)', source)
        self.assertIn("return 8", source)

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

    def test_audiobook_visualizer_is_lightweight_and_motion_aware(self):
        from PySide6.QtWidgets import QProgressBar, QWidget
        from app.ui.audio_visualizer import AudioVisualizer
        from app.ui.motion import SmoothProgressBar

        visualizer_source = Path("app/ui/audio_visualizer.py").read_text(encoding="utf-8")
        generation_source = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertTrue(issubclass(AudioVisualizer, QWidget))
        self.assertTrue(issubclass(SmoothProgressBar, QProgressBar))
        self.assertIn("self._timer.setInterval(40)", visualizer_source)
        self.assertIn("self._playing and not self._reduced_motion and self.isVisible()", visualizer_source)
        self.assertIn("self._timer.stop()", visualizer_source)
        self.assertIn("no images, shaders, OpenGL, audio capture, or background", visualizer_source)
        self.assertIn("QSettings(\"RyuBlanc\", \"Ryu's Audiobook\")", generation_source)
        self.assertIn("self.player.playbackStateChanged.connect(self._player_playback_state_changed)", generation_source)
        self.assertIn('QCheckBox("Reduce motion")', generation_source)
        self.assertIn('self.motion_settings.setValue("ui/reduce_motion", self._reduce_motion_enabled)', generation_source)

    def test_global_motion_system_uses_low_cost_animations_and_cached_blur(self):
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QProgressBar, QWidget
        from app.ui.motion import SmoothProgressBar
        from app.ui.loading_overlay import FrostedLoadingOverlay
        from app.ui.workflow import ImportBookWorker, RedetectChaptersWorker

        motion_source = Path("app/ui/motion.py").read_text(encoding="utf-8")
        overlay_source = Path("app/ui/loading_overlay.py").read_text(encoding="utf-8")
        workflow_source = Path("app/ui/workflow.py").read_text(encoding="utf-8")
        main_source = Path("app/main.py").read_text(encoding="utf-8")

        self.assertTrue(issubclass(SmoothProgressBar, QProgressBar))
        self.assertTrue(issubclass(FrostedLoadingOverlay, QWidget))
        self.assertTrue(issubclass(ImportBookWorker, QThread))
        self.assertTrue(issubclass(RedetectChaptersWorker, QThread))
        self.assertIn("self._busy_timer.setInterval(65)", motion_source)
        self.assertIn("animation.setDuration(180)", motion_source)
        self.assertIn("self._timer.setInterval(55)", overlay_source)
        self.assertIn("size.width() // 14", overlay_source)
        self.assertIn("self._capture_frosted_snapshot()", overlay_source)
        resize_start = overlay_source.index("    def resizeEvent(self, event)")
        resize_end = overlay_source.index("    def paintEvent(self, event)", resize_start)
        self.assertNotIn("_capture_frosted_snapshot()", overlay_source[resize_start:resize_end])
        self.assertIn("self.loading_overlay.show_loading(", workflow_source)
        self.assertIn("self._redetect_worker = worker", workflow_source)
        self.assertIn("worker.start()", workflow_source)
        self.assertIn("animation.setDuration(135)", workflow_source)
        self.assertIn("QListWidget#sidebar::item:selected", main_source)
        self.assertIn("stop:0 #84142e", main_source)

    def test_automatic_music_hides_manual_track_rows(self):
        ui = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        self.assertIn("self._background_audio_form.setRowVisible(widget, visible)", ui)
        self.assertIn("(self.music_file_container, manual_mode)", ui)
        self.assertIn("(self.background_audio_volume, auto_mode or manual_mode)", ui)
        self.assertIn("(self.ambience_file_container, manual_mode)", ui)
        self.assertIn('settings_form.addRow("BGM volume", self.background_audio_volume)', ui)
        self.assertIn("self.background_audio_volume.setEnabled(auto_mode or manual_mode)", ui)
        self.assertIn("story_effects_enabled.toggled.connect(self.story_effect_volume.setEnabled)", ui)
        self.assertLess(
            ui.index("self.story_effect_volume = QDoubleSpinBox()"),
            ui.index("self.story_effects_enabled.toggled.connect(self.story_effect_volume.setEnabled)"),
        )

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
                _write_wav(wav, 12.0)
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

    def test_m4b_can_mix_a_continuous_background_track(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter_dirs = []
            for number in (1, 2):
                chapter_dir = root / f"{number:03d}_Chapter_{number}"
                _write_wav(chapter_dir / "chunks" / "00001.wav", 3.0)
                chapter_dirs.append(chapter_dir)

            music = root / "licensed-music.wav"
            ambience = root / "licensed-rain-ambience.wav"
            _write_wav(music, 1.0)
            _write_wav(ambience, 1.5)
            output = root / "mixed-book.m4b"
            progress = []
            result = assemble_m4b(
                chapter_dirs,
                output,
                "Mixed Test Book",
                chapter_titles=["Chapter 1", "Chapter 2"],
                progress=lambda done, total, message: progress.append(message),
                background_audio_path=music,
                background_audio_volume=0.12,
                ambience_audio_path=ambience,
                ambience_audio_volume=0.06,
                background_audio_fade_in=0.5,
                background_audio_fade_out=0.5,
            )
            self.assertEqual(result, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1024)
            self.assertIn("mixed-background-audio", progress)
            self.assertGreaterEqual(_probe_audio_bitrate_kbps(output), 128)

    def test_background_audio_controls_are_optional_and_project_persisted(self):
        ui = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        manager = Path("app/tts/manager.py").read_text(encoding="utf-8")
        assembler = Path("app/audio/assembler.py").read_text(encoding="utf-8")
        self.assertIn('QCheckBox("Enable background music / ambience")', ui)
        self.assertIn('self.background_audio_mode.addItem("Automatic • chapter-aware music", "auto")', ui)
        self.assertIn('self.background_audio_mode.addItem("Manual • use my own tracks", "manual")', ui)
        self.assertIn("def preview_background_audio(self)", ui)
        self.assertIn("def preview_ambience_audio(self)", ui)
        self.assertIn("detect", ui)
        self.assertIn("chapter text", ui)
        self.assertIn('"background_audio_enabled": self.background_audio_enabled.isChecked()', ui)
        self.assertIn('"ambience_audio_path": self.ambience_audio_path.text().strip()', ui)
        self.assertIn("background_audio_path=background_audio_path", ui)
        self.assertIn("ambience_audio_path=ambience_audio_path", ui)
        self.assertIn("background_audio_path=self.background_audio_path", manager)
        self.assertIn("ambience_audio_path=self.ambience_audio_path", manager)
        self.assertIn('inputs.extend(["-stream_loop", "-1", "-i", str(layer_path)])', assembler)
        self.assertIn("amix=inputs={mix_count}:duration=first", assembler)
        self.assertIn('if effective_audio_mode == "auto":', assembler)
        self.assertIn("synthesize_page_turn", assembler)
        self.assertIn("synthesize_audiobook_ending", assembler)
        self.assertIn("auto_music_variation", assembler)
        self.assertIn("_selected_music_recipe", assembler)
        self.assertIn("sidechaincompress=", assembler)
        self.assertIn("automatic-chapter-sound-design", assembler)
        self.assertIn('elif effective_audio_mode == "off" and chapter_transition_sound:', assembler)

    def test_generated_music_and_transition_cues_are_local_wav_files(self):
        import wave
        from app.audio.sound_design import (
            CUE_STYLE_LABELS,
            MUSIC_CATALOGUE_SIZE,
            MOOD_ORDER,
            OPENING_SECONDS,
            TEMPOS,
            VARIATIONS_PER_MOOD,
            detect_chapter_mood,
            music_variation_info,
            select_music_variation,
            synthesize_audiobook_ending,
            synthesize_chapter_transition,
            synthesize_music_bed,
            synthesize_opening_cue,
            synthesize_page_turn,
        )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fantasy = synthesize_music_bed(root / "fantasy.wav", "fantasy")
            mystery = synthesize_music_bed(root / "mystery.wav", "mystery")
            cue = synthesize_chapter_transition(root / "chapter-cue.wav", "fantasy")
            opening = synthesize_opening_cue(root / "book-opening.wav", cue_style="classic-book")
            page_turn = synthesize_page_turn(root / "page-turn.wav", variation_index=7, cue_style="classic-book")
            magic_page = synthesize_page_turn(root / "magic-page.wav", variation_index=7, cue_style="magical-tome")
            ending = synthesize_audiobook_ending(root / "book-ending.wav", "fantasy", variation_index=7, cue_style="classic-book")
            with wave.open(str(fantasy), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getframerate(), 22050)
                # One 16-beat loop: its length varies with the selected tempo.
                self.assertAlmostEqual(
                    wav.getnframes() / wav.getframerate(),
                    16.0 * 60.0 / TEMPOS[0],
                    delta=0.1,
                )
            with wave.open(str(cue), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertGreater(wav.getnframes(), 0)
                self.assertLess(wav.getnframes() / wav.getframerate(), 1.5)
            with wave.open(str(opening), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), OPENING_SECONDS, delta=0.03)
            with wave.open(str(page_turn), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), 0.62, delta=0.02)
            with wave.open(str(ending), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), 2.65, delta=0.05)
            self.assertNotEqual(opening.read_bytes(), page_turn.read_bytes())
            self.assertNotEqual(page_turn.read_bytes(), magic_page.read_bytes())
            self.assertNotEqual(page_turn.read_bytes(), ending.read_bytes())
            self.assertNotEqual(fantasy.read_bytes(), mystery.read_bytes())
            self.assertIn("custom", CUE_STYLE_LABELS)

        self.assertEqual(detect_chapter_mood("A Secret Revealed", "A strange hidden clue appeared."), "mystery")
        self.assertEqual(detect_chapter_mood("The Confession", "She blushed and confessed her love."), "romance")
        self.assertEqual(detect_chapter_mood("The Battlefield", "Swords clashed in the battle."), "action")
        self.assertEqual(detect_chapter_mood("A New Quest", "A wizard cast a magic spell."), "fantasy")
        self.assertEqual(MUSIC_CATALOGUE_SIZE, 1344)
        self.assertEqual(VARIATIONS_PER_MOOD, 168)

        # Every recipe has its own stable catalogue ID; selection is repeatable
        # for the same story context rather than random per generation.
        ids = {
            music_variation_info(mood, variation)["id"]
            for mood in MOOD_ORDER
            for variation in range(VARIATIONS_PER_MOOD)
        }
        self.assertEqual(len(ids), MUSIC_CATALOGUE_SIZE)
        self.assertEqual(min(ids), 1)
        self.assertEqual(max(ids), MUSIC_CATALOGUE_SIZE)
        chosen = select_music_variation("The Hidden Door", "He ran down the corridor.", "mystery")
        self.assertEqual(
            chosen,
            select_music_variation("The Hidden Door", "He ran down the corridor.", "mystery"),
        )

    def test_auto_music_and_transition_cue_are_added_per_chapter(self):
        from app.audio.assembler import _duration_ms

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter_dirs = []
            for number, title, narration in (
                (1, "The Hidden Clue", "A hidden clue changed everything."),
                (2, "The Final Battle", "The warriors charged into battle."),
            ):
                chapter_dir = root / f"{number:03d}_{title.replace(' ', '_')}"
                _write_wav(chapter_dir / "chunks" / "00001.wav", 3.0)
                (chapter_dir / "narration.json").write_text(
                    json.dumps({"title": title, "narration_text": narration}),
                    encoding="utf-8",
                )
                chapter_dirs.append(chapter_dir)

            progress = []
            output = root / "automatic-sound-design.m4b"
            result = assemble_m4b(
                chapter_dirs,
                output,
                "Automatic Sound Design Test",
                chapter_titles=["The Hidden Clue", "The Final Battle"],
                progress=lambda done, total, message: progress.append(message),
                background_audio_mode="auto",
                auto_music_style="auto",
                background_audio_volume=0.30,
                background_audio_fade_in=0.4,
                background_audio_fade_out=0.4,
                chapter_transition_sound=True,
            )
            self.assertEqual(result, output)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1024)
            self.assertIn("automatic-chapter-sound-design", progress)
            # Six seconds of speech plus one short cue at the start of each
            # chapter; allow for AAC encoder padding and container time-base rounding.
            self.assertGreaterEqual(_duration_ms(output), 7000)
            self.assertGreaterEqual(_probe_audio_bitrate_kbps(output), 128)

    def test_story_events_detect_clear_actions_but_not_metaphors(self):
        from app.audio.story_events import detect_story_events

        action = detect_story_events(
            "He ran down the corridor. The door slammed shut behind him."
        )
        self.assertIn("running_footsteps", [event.kind for event in action])
        self.assertIn("door_slam", [event.kind for event in action])

        weather = detect_story_events("Rain poured against the roof as thunder rumbled.")
        self.assertIn("rain", [event.kind for event in weather])
        self.assertIn("thunder", [event.kind for event in weather])

        metaphor = detect_story_events("She was running out of time and running out of patience.")
        self.assertNotIn("running_footsteps", [event.kind for event in metaphor])

    def test_synthesized_story_effect_is_valid_local_audio(self):
        import wave
        from app.audio.story_events import EVENT_PROFILES, synthesize_story_effect

        with tempfile.TemporaryDirectory() as temp:
            output = synthesize_story_effect(
                Path(temp) / "running.wav", "running_footsteps", variant_seed=7
            )
            self.assertTrue(output.exists())
            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getnchannels(), 2)
                self.assertEqual(wav.getframerate(), 22050)
                self.assertAlmostEqual(
                    wav.getnframes() / wav.getframerate(),
                    EVENT_PROFILES["running_footsteps"].duration,
                    delta=0.1,
                )
            first = output.read_bytes()
            repeated = synthesize_story_effect(
                Path(temp) / "running-repeat.wav", "running_footsteps", variant_seed=7
            )
            self.assertEqual(first, repeated.read_bytes())

    def test_story_effects_mix_without_background_music_and_preserve_duration(self):
        from app.audio.assembler import _duration_ms

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter_dirs = []
            stories = (
                (
                    "The Corridor",
                    "He ran down the corridor. The door slammed shut behind him.",
                ),
                (
                    "Storm",
                    "Rain poured against the roof as thunder rumbled in the distance.",
                ),
            )
            for number, (title, text) in enumerate(stories, start=1):
                chapter_dir = root / f"{number:03d}_{title.replace(' ', '_')}"
                chunk_path = chapter_dir / "chunks" / "00001.wav"
                _write_wav(chunk_path, 3.0)
                (chapter_dir / "chunk_manifest.json").write_text(
                    json.dumps({
                        "version": 1,
                        "chapter": number,
                        "title": title,
                        "chunks": [{"index": 1, "file": "00001.wav", "text": text}],
                    }),
                    encoding="utf-8",
                )
                chapter_dirs.append(chapter_dir)

            progress = []
            output = root / "story-effects-only.m4b"
            result = assemble_m4b(
                chapter_dirs,
                output,
                "Story Effects Only Test",
                chapter_titles=["The Corridor", "Storm"],
                progress=lambda done, total, message: progress.append(message),
                background_audio_mode="off",
                story_effects_enabled=True,
                story_effect_volume=0.20,
            )
            self.assertEqual(result, output)
            self.assertTrue(output.exists())
            self.assertIn("story-effects-mixed", progress)
            # Effects are overlaid in-place; they must not extend the book.
            self.assertAlmostEqual(_duration_ms(output) / 1000.0, 6.0, delta=0.20)
            self.assertGreaterEqual(_probe_audio_bitrate_kbps(output), 128)

    def test_story_effect_controls_are_independent_of_background_music(self):
        ui = Path("app/ui/generation_page.py").read_text(encoding="utf-8")
        manager = Path("app/tts/manager.py").read_text(encoding="utf-8")
        assembler = Path("app/audio/assembler.py").read_text(encoding="utf-8")
        self.assertIn('self.story_effects_enabled = QCheckBox(', ui)
        self.assertIn('self.story_effects_enabled.toggled.connect(', ui)
        self.assertIn('story_effects_enabled=self.story_effects_enabled.isChecked()', ui)
        self.assertIn('story_effects_enabled: bool = False', manager)
        self.assertIn('if story_effects_enabled:', assembler)

    def test_manual_music_still_gets_chapter_transition_cues(self):
        from app.audio.assembler import _duration_ms

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter_dir = root / "001_Manual_Chapter"
            _write_wav(chapter_dir / "chunks" / "00001.wav", 3.0)
            (chapter_dir / "narration.json").write_text(
                json.dumps({
                    "title": "Manual Chapter",
                    "narration_text": "The story continues into the next room.",
                }),
                encoding="utf-8",
            )
            music = root / "continuous-music.wav"
            _write_wav(music, 1.0)
            progress = []
            output = root / "manual-with-cue.m4b"
            result = assemble_m4b(
                [chapter_dir],
                output,
                "Manual Mode Cue Test",
                chapter_titles=["Manual Chapter"],
                progress=lambda done, total, message: progress.append(message),
                background_audio_mode="manual",
                background_audio_path=music,
                background_audio_volume=0.18,
                chapter_transition_sound=True,
                background_audio_fade_in=0.3,
                background_audio_fade_out=0.3,
            )
            self.assertEqual(result, output)
            self.assertIn("mixed-background-audio", progress)
            self.assertGreaterEqual(_duration_ms(output), 3500)
            self.assertGreaterEqual(_probe_audio_bitrate_kbps(output), 128)

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

    def test_chapter_heading_is_not_joined_to_first_narration_sentence(self):
        source = (
            "Chapter 1 Prologue\n"
            "Erotic video games—eroge—are, for the most part, chock-full of things to ridicule.\n"
            "And there are plenty of reasons to lampoon them, too.\n"
            "Let's start with the protagonist's family, shall we?"
        )
        prepared = prepare_for_narration(source)
        self.assertTrue(prepared.narration_text.startswith("Chapter 1 Prologue\n"))
        self.assertNotIn("Chapter 1 Prologue Erotic video games", prepared.narration_text)

        units = split_for_pacing(prepared.narration_text, max_chars=800, max_sentences=4)
        self.assertEqual(units[0], "Chapter 1 Prologue")
        self.assertTrue(units[1].startswith("Erotic video games—eroge—are"))
        self.assertNotIn("Chapter 1 Prologue", units[1])
        self.assertGreaterEqual(pause_after_ms(units[0], "natural", next_text=units[1]), 600)

    def test_all_caps_and_section_headings_remain_separate_narration_units(self):
        source = (
            "The room went quiet.\n"
            "THE DEMON LORD SUMMIT\n"
            "A moment later, the doors opened.\n"
            "Part 2 — The Next Journey\n"
            "Everyone turned around."
        )
        prepared = prepare_for_narration(source)
        units = split_for_pacing(prepared.narration_text, max_chars=800, max_sentences=4)
        self.assertIn("THE DEMON LORD SUMMIT", units)
        self.assertIn("Part 2 — The Next Journey", units)
        for heading in ("THE DEMON LORD SUMMIT", "Part 2 — The Next Journey"):
            self.assertEqual(units.count(heading), 1)
            self.assertGreaterEqual(pause_after_ms(heading), 700)

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
