"""Stage 5.2 Production preview ownership and configuration parity contracts."""
from __future__ import annotations

import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
        with patch.object(premium_v2_host, "load_state", return_value={"voice_profile": "Old Project Snapshot"}):
            result = premium_v2_host.PremiumV2Bridge._production_preview(bridge, transient_payload)

        self.assertEqual(result["profile_name"], saved_profile.name)
        self.assertEqual(captured["profile_name"], saved_profile.name)
        self.assertEqual(captured["chapter_number"], 3)
        self.assertTrue(captured["_production_preview"])
        self.assertTrue(captured["include_sound_design"])
        self.assertTrue(captured["route_character_cast"])
        self.assertTrue(captured["apply_pronunciation_rules"])
        self.assertNotIn("text", captured)
        self.assertNotIn("provider", captured)
        self.assertNotIn("voice_id", captured)

    def test_production_preview_fails_closed_when_saved_narrator_is_unavailable(self):
        chapter = SimpleNamespace(number=1, title="Opening", text="Saved text.", chapter_id="ch-1")
        project = SimpleNamespace(folder=Path("project-A"), chapters=[chapter])
        called = []
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _project_series_name=lambda _project, _state: "Series A",
            _narrator_series_default_read=lambda _project, _state, _series: {
                "effective_profile_name": "Unavailable narrator",
                "profile_available": False,
            },
            _find_profile=lambda _name: None,
            _voice_preview=lambda _payload: called.append(True),
        )
        with patch.object(premium_v2_host, "load_state", return_value={}):
            with self.assertRaisesRegex(ValueError, "is unavailable"):
                premium_v2_host.PremiumV2Bridge._production_preview(
                    bridge, {"chapter_number": 1, "profile_name": "Transient"}
                )
        self.assertEqual(called, [])


class ProductionPreviewOwnershipTests(unittest.TestCase):
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
