"""Stage 5.2 Production preview ownership and configuration parity contracts."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.ui import premium_v2_host


class ProductionPreviewSavedNarratorTests(unittest.TestCase):
    def test_production_preview_uses_saved_project_narrator_not_transient_voice_card(self):
        chapter = SimpleNamespace(
            number=3, title="The Saved Chapter", text="The actual saved chapter text.",
            chapter_id="chapter-stable-3",
        )
        project = SimpleNamespace(folder=Path("project-A"), chapters=[chapter])
        saved_profile = SimpleNamespace(name="Saved Series Narrator")
        captured = {}
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _project_series_name=lambda _project, _state: "Saved Series",
            _narrator_series_default_read=lambda _project, _state, series: {
                "series": series,
                "effective_profile_name": saved_profile.name,
                "profile_available": True,
            },
            _find_profile=lambda name: saved_profile if name == saved_profile.name else None,
            _resolve_narrator_for_generation=lambda _project, _state, _chapters: (
                saved_profile,
                {"narrator_only": False, "generation_mode": "character_cast"},
            ),
            _voice_preview=lambda payload: captured.update(payload) or {
                "job_id": "production-preview-1",
                "profile_name": saved_profile.name,
            },
        )
        transient_payload = {
            "chapter_number": 3,
            "profile_name": "Unsaved Voice Card",
            "provider": "piper",
            "voice_id": "wrong-provider-voice",
            "duration_seconds": 30,
            "text": "UNTRUSTED WHOLE-BOOK TEXT MUST NOT BE USED",
            "route_character_cast": False,
            "apply_pronunciation_rules": False,
            "include_sound_design": False,
        }
        # The saved flag is stale: preview routing must follow the shared
        # resolver's effective mode after cast-profile reconciliation.
        with patch.object(
            premium_v2_host, "load_state",
            return_value={"voice_profile": "Old Project Snapshot", "narrator_only_generation": True},
        ):
            result = premium_v2_host.PremiumV2Bridge._production_preview(bridge, transient_payload)

        self.assertEqual(result["profile_name"], saved_profile.name)
        self.assertEqual(captured["profile_name"], saved_profile.name)
        self.assertEqual(captured["chapter_number"], 3)
        self.assertEqual(captured["chapter_id"], "chapter-stable-3")
        self.assertTrue(captured["_production_preview"])
        self.assertTrue(captured["include_sound_design"])
        self.assertTrue(captured["route_character_cast"])
        self.assertTrue(captured["apply_pronunciation_rules"])
        self.assertNotIn("text", captured)
        self.assertNotIn("provider", captured)
        self.assertNotIn("voice_id", captured)


    def test_production_preview_rejects_stale_chapter_id_before_synthesis(self):
        chapter = SimpleNamespace(
            number=2, title="Replacement Chapter", text="Replacement text.",
            chapter_id="replacement-chapter-2",
        )
        project = SimpleNamespace(folder=Path("project-A"), chapters=[chapter])
        called = []
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _project_series_name=lambda _project, _state: "Series A",
            _narrator_series_default_read=lambda _project, _state, _series: {
                "effective_profile_name": "Saved narrator",
                "profile_available": True,
            },
            _find_profile=lambda _name: SimpleNamespace(name="Saved narrator"),
            _voice_preview=lambda _payload: called.append(True),
        )
        with patch.object(premium_v2_host, "load_state", return_value={}):
            with self.assertRaisesRegex(ValueError, "identity changed before preview started"):
                premium_v2_host.PremiumV2Bridge._production_preview(
                    bridge,
                    {"chapter_number": 2, "chapter_id": "deleted-chapter-2"},
                )
        self.assertEqual(called, [])

    def test_production_preview_fails_closed_when_saved_narrator_is_unavailable(self):
        chapter = SimpleNamespace(number=1, title="Opening", text="Saved text.", chapter_id="ch-1")
        project = SimpleNamespace(folder=Path("project-A"), chapters=[chapter])
        called = []
        def fail_narrator_resolution(_project, _state, _chapters):
            raise ValueError(
                "The effective narrator profile 'Unavailable narrator' is unavailable."
            )

        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _resolve_narrator_for_generation=fail_narrator_resolution,
            _voice_preview=lambda _payload: called.append(True),
        )
        with patch.object(premium_v2_host, "load_state", return_value={}):
            with self.assertRaisesRegex(ValueError, "is unavailable"):
                premium_v2_host.PremiumV2Bridge._production_preview(
                    bridge, {"chapter_number": 1, "profile_name": "Transient"}
                )
        self.assertEqual(called, [])


    def test_production_preview_uses_saved_narrator_only_mode_and_disables_cast_routing(self):
        chapter = SimpleNamespace(
            number=1,
            title="Narrator-only opening",
            text='“The journey begins,” Mira said.',
            chapter_id="chapter-narrator-only-1",
        )
        project = SimpleNamespace(folder=Path("project-narrator-only"), chapters=[chapter])
        saved_profile = SimpleNamespace(name="Saved Narrator")
        captured = {}
        resolver = Mock(return_value=(
            saved_profile,
            {
                "generation_mode": "narrator_only",
                "narrator_only": True,
                "character_voice_profile_count": 0,
                "dialogue_routing": "narrator_for_all_passages",
            },
        ))
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _resolve_narrator_for_generation=resolver,
            _voice_preview=lambda payload: captured.update(payload) or {
                "job_id": "narrator-only-preview",
                "profile_name": saved_profile.name,
            },
        )
        with patch.object(
            premium_v2_host, "load_state",
            return_value={"narrator_only_generation": True, "characters": []},
        ):
            result = premium_v2_host.PremiumV2Bridge._production_preview(
                bridge,
                {
                    "chapter_number": 1,
                    "chapter_id": chapter.chapter_id,
                    "profile_name": "Transient Voice",
                    "provider": "wrong-provider",
                    "voice_id": "wrong-voice",
                    "duration_seconds": 30,
                },
            )

        self.assertEqual(result["profile_name"], saved_profile.name)
        self.assertIs(captured["route_character_cast"], False)
        self.assertEqual(captured["profile_name"], saved_profile.name)
        self.assertEqual(captured["chapter_id"], chapter.chapter_id)
        self.assertTrue(captured["_production_preview"])
        resolver.assert_called_once_with(project, {"narrator_only_generation": True, "characters": []}, [chapter])


class ProductionPreviewOwnershipTests(unittest.TestCase):
    def test_production_preview_save_copies_only_the_completed_job_audio(self):
        with tempfile.TemporaryDirectory(prefix="ryu-production-preview-save-test-") as temp:
            root = Path(temp)
            preview_root = root / "Previews"
            preview_root.mkdir()
            source = preview_root / "preview-job.m4a"
            source.write_bytes(b"\x00\x00\x00\x18ftypM4A " + (b"test-audio" * 256))
            destination = root / "saved" / "Chapter_02_Preview.m4a"
            destination.parent.mkdir(parents=True, exist_ok=True)
            bridge = SimpleNamespace(
                _jobs_lock=threading.RLock(),
                _jobs={
                    "job-save": {
                        "job_id": "job-save",
                        "type": "production-preview",
                        "state": "completed",
                        "project_folder": "project-A",
                        "current_chapter": 2,
                        "current_chapter_id": "chapter-2",
                        "result": {"output_path": str(source)},
                    }
                },
            )
            with patch.object(premium_v2_host, "app_root", return_value=root), patch.object(
                premium_v2_host.QFileDialog,
                "getSaveFileName",
                return_value=(str(destination), "Production preview audio (*.wav *.m4a)"),
            ):
                result = premium_v2_host.PremiumV2Bridge._production_preview_save(
                    bridge,
                    {
                        "job_id": "job-save",
                        "project_folder": "project-A",
                        "chapter_number": 2,
                        "chapter_id": "chapter-2",
                        "source_path": str(source),
                        "suggested_name": "Chapter_02_Preview",
                    },
                )
            self.assertFalse(result["cancelled"])
            self.assertEqual(Path(result["path"]), destination.resolve())
            self.assertEqual(result["job_id"], "job-save")
            self.assertEqual(result["chapter_number"], 2)
            self.assertEqual(result["bytes"], source.stat().st_size)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertGreater(destination.stat().st_size, 1024)

    def test_production_preview_native_save_dialog_sanitizes_windows_filename_characters(self):
        with tempfile.TemporaryDirectory(prefix="ryu-production-preview-filename-") as temp:
            root = Path(temp)
            preview_root = root / "Previews"
            preview_root.mkdir()
            source = preview_root / "preview-filename.m4a"
            source.write_bytes(b"\x00\x00\x00\x18ftypM4A " + (b"test-audio" * 256))
            bridge = SimpleNamespace(
                _jobs_lock=threading.RLock(),
                _jobs={
                    "job-filename": {
                        "job_id": "job-filename",
                        "type": "production-preview",
                        "state": "completed",
                        "project_folder": "project-A",
                        "current_chapter": 2,
                        "current_chapter_id": "chapter-2",
                        "result": {"output_path": str(source)},
                    }
                },
            )
            dialog = {}
            def capture_save_dialog(_parent, _title, default_path, _filters):
                dialog["default_path"] = default_path
                return "", ""

            with patch.object(premium_v2_host, "app_root", return_value=root), patch.object(
                premium_v2_host.QFileDialog, "getSaveFileName", side_effect=capture_save_dialog
            ):
                result = premium_v2_host.PremiumV2Bridge._production_preview_save(
                    bridge,
                    {
                        "job_id": "job-filename",
                        "project_folder": "project-A",
                        "chapter_number": 2,
                        "chapter_id": "chapter-2",
                        "source_path": str(source),
                        "suggested_name": "Book: A\\B/Chapter?Title*\\x00",
                    },
                )
            self.assertTrue(result["cancelled"])
            filename = Path(dialog["default_path"]).name
            self.assertTrue(filename.endswith(".m4a"))
            self.assertFalse(any(character in filename for character in '<>:"/\\\\|?*'))
            self.assertFalse(any(ord(character) < 32 for character in filename))
            self.assertIn("Book- A-B-Chapter-Title-", filename)

    def test_global_pronunciation_off_excludes_all_dictionary_rules(self):
        state = {
            "pronunciation_enabled": False,
            "pronunciation_dictionary": [
                {"written_form": "Aster", "spoken_form": "ASS-ter", "enabled": True}
            ],
        }
        self.assertEqual(premium_v2_host._effective_pronunciation_dictionary(state), [])

    def test_production_preview_save_rejects_reused_chapter_number_with_different_id(self):
        bridge = SimpleNamespace(
            _jobs_lock=threading.RLock(),
            _jobs={
                "job-1": {
                    "job_id": "job-1",
                    "type": "production-preview",
                    "state": "completed",
                    "project_folder": "project-A",
                    "current_chapter": 2,
                    "current_chapter_id": "original-chapter-2",
                }
            },
        )
        with self.assertRaisesRegex(ValueError, "different saved chapter identity"):
            premium_v2_host.PremiumV2Bridge._production_preview_save(
                bridge,
                {
                    "job_id": "job-1",
                    "project_folder": "project-A",
                    "chapter_number": 2,
                    "chapter_id": "replacement-chapter-2",
                    "source_path": "unused-preview.m4a",
                },
            )


class ProductionPreviewParitySourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.host_source = (root / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        cls.adapter_source = (root / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")

    def test_production_preview_selector_uses_saved_chapter_list_and_ownership_identity(self):
        self.assertIn("function syncProductionPreviewChapterSelector()", self.adapter_source)
        self.assertIn("call('chapter.list')", self.adapter_source)
        self.assertIn("productionPreviewChapterSelect", self.adapter_source)
        self.assertIn("productionPreviewRequestChapterId", self.adapter_source)
        self.assertIn("productionPreviewSelectedChapterSignature", self.adapter_source)
        self.assertIn("String(currentRow.text || '')", self.adapter_source)
        self.assertIn("current_chapter_id", self.adapter_source)
        self.assertIn("chapter_id:productionPreviewRequestChapterId", self.adapter_source)

    def test_pronunciation_switch_is_shared_with_preview_and_final_generation(self):
        self.assertIn("call('pronunciation.settings.get')", self.adapter_source)
        self.assertIn("call('pronunciation.settings.save'", self.adapter_source)
        self.assertIn("'productionPronunciationToggle'", self.adapter_source)
        self.assertIn('if state.get("pronunciation_enabled", True) is False:', self.host_source)
        self.assertIn("pronunciation_dictionary=(", self.host_source)
        self.assertIn("_effective_pronunciation_dictionary(state)", self.host_source)

    def test_sound_design_switch_flushes_saved_configuration_before_production_preview(self):
        self.assertIn("flushSoundDesignState()", self.adapter_source)
        self.assertIn("saveSoundManifest({path, enabled})", self.adapter_source)
        self.assertIn("include_sound_design:true", self.adapter_source)
        self.assertIn("def _render_sound_design_preview", self.host_source)
        self.assertIn("effective_background_audio_mode(state)", self.host_source)
        self.assertIn("chapter_bgm_strategy=chapter_bgm_strategy", self.host_source)
        self.assertIn("chapter_bgm_overrides=", self.host_source)


    def test_preview_worker_keeps_m4a_download_output_and_creates_browser_playback_wav(self):
        worker = self.host_source[
            self.host_source.index("def _preview_worker("):
            self.host_source.index("def _character_list(", self.host_source.index("def _preview_worker("))
        ]
        self.assertIn('if preview_path.suffix.casefold() == ".m4a":', worker)
        self.assertIn('playback_path = folder / f"preview_playback_{job_id}.wav"', worker)
        self.assertIn('"output_path": str(preview_path)', worker)
        self.assertIn('"file_url": playback_path.resolve().as_uri()', worker)
        self.assertIn('"playback_output_path": str(playback_path)', worker)
        self.assertIn('"playback_format": playback_path.suffix.casefold().lstrip(".")', worker)
        self.assertIn("_run([", worker)
        self.assertIn('"-c:a", "pcm_s16le"', worker)
        self.assertIn("abs(float(playback_duration) - float(duration)) > 1.5", worker)

    def test_production_preview_download_filename_uses_project_and_chapter_identity(self):
        start = self.adapter_source.index("const downloadProductionPreview=async()=>{")
        end = self.adapter_source.index("if ($('productionPreviewDownload'))", start)
        download = self.adapter_source[start:end]
        self.assertIn("activeProject?.title", download)
        self.assertIn("activeProject?.name", download)
        self.assertIn("projectFolder.replace(", download)
        self.assertIn("const safeFilePart=value=>String(value||'')", download)
        self.assertIn("safeFilePart(activeProject?.title||activeProject?.name||folderName)", download)
        self.assertIn("safeFilePart(lastVoicePreviewChapterTitle)", download)
        self.assertIn("const suffix='_Chapter_'", download)
        self.assertIn("lastVoicePreviewChapterTitle", download)
        self.assertIn("projectBaseName.slice(0,Math.max(12,100-suffix.length))+suffix", download)
        self.assertIn("suggested_name:suggestedName", download)

    def test_production_engine_orders_preview_settings_and_full_book_actions(self):
        helper_start = self.adapter_source.index("function ensureProductionEngineLayout()")
        helper_end = self.adapter_source.index("\n  async function refreshProductionSummary()", helper_start)
        helper = self.adapter_source[helper_start:helper_end]
        for required in (
            "ryuProductionPreviewSection",
            "ryuProductionOptionsSection",
            "ryuProductionActionsSection",
            "move($('previewGenerate'),preview)",
            "move(previewDurationGroup,preview)",
            "move($('productionPreviewControls'),preview)",
            "move($('productionPreviewMonitor'),preview)",
            "move($('narratorOnlyGenerationControl'),settings)",
            "move(generateButton,actions)",
            "move($('pauseGenerate'),actions)",
            "originalActionToolbar.hidden = true",
            "!originalActionToolbar.querySelector('button')",
        ):
            self.assertIn(required, helper)
        self.assertLess(helper.index("ryuProductionPreviewSection"), helper.index("ryuProductionOptionsSection"))
        self.assertLess(helper.index("ryuProductionOptionsSection"), helper.index("ryuProductionActionsSection"))
        monitor_start = self.adapter_source.index("function ensureProductionPreviewMonitorUi()")
        monitor_end = self.adapter_source.index("\n  function monitorProductionJob(", monitor_start)
        monitor = self.adapter_source[monitor_start:monitor_end]
        self.assertIn("ensureProductionEngineLayout();", monitor)

    def test_real_cover_removes_placeholder_watermark_but_empty_cover_keeps_gradient_branding(self):
        start = self.adapter_source.index("function applyProjectCover(element, path)")
        end = self.adapter_source.index("\n  function ", start + 1)
        apply_cover = self.adapter_source[start:end]
        self.assertIn("element.classList.add('has-project-cover')", apply_cover)
        self.assertIn("element.classList.remove('has-project-cover')", apply_cover)
        self.assertIn(".has-project-cover::after{content:none!important", self.adapter_source)
        self.assertIn(".has-project-cover::before", self.adapter_source)
        self.assertNotIn(".book-cover::after{content:none!important", self.adapter_source)

    def test_preview_and_final_generation_consume_the_effective_saved_voice_configuration(self):
        self.assertIn('"_production_preview": True', self.host_source)
        self.assertIn("self._narrator_series_default_read(project, state, series)", self.host_source)
        self.assertIn("profile, narrator_selection = self._resolve_narrator_for_generation(project, state, chapters)", self.host_source)
        self.assertIn("_effective_pronunciation_dictionary(state)", self.host_source)
        self.assertIn("background_audio_mode=background_audio_mode", self.host_source)
        self.assertIn("opening_cue_path=opening_cue_path", self.host_source)
        self.assertIn("ending_cue_path=ending_cue_path", self.host_source)


if __name__ == "__main__":
    unittest.main()
