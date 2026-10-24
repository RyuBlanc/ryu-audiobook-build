"""Stage 4 contract tests for selected voice profile and requested preview duration."""
from pathlib import Path
from types import SimpleNamespace
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.ui import premium_v2_host


class VoicePreviewContractTests(unittest.TestCase):
    def test_preview_handler_preserves_selected_profile_and_all_supported_durations(self):
        profile = SimpleNamespace(name="Saved Narrator")
        project = SimpleNamespace(folder=Path("unused"), chapters=[])
        for seconds in (10, 20, 30, 45, 60):
            with self.subTest(seconds=seconds):
                thread = Mock()
                bridge = SimpleNamespace(
                    _active_project=lambda: project,
                    _assert_no_active_model_lifecycle=lambda _activity: None,
                    _find_profile=lambda name: profile if name == profile.name else None,
                    _new_job=Mock(return_value="preview-job"),
                    _job_update=Mock(),
                    _now=premium_v2_host.PremiumV2Bridge._now,
                    _preview_worker=premium_v2_host.PremiumV2Bridge._preview_worker,
                )
                with patch.object(premium_v2_host, "load_state", return_value={}), \
                     patch.object(premium_v2_host.threading, "Thread", return_value=thread) as thread_factory:
                    result = premium_v2_host.PremiumV2Bridge._voice_preview(
                        bridge,
                        {"profile_name": profile.name, "text": "A sufficiently long preview passage.",
                         "duration_seconds": seconds},
                    )
                self.assertEqual(result["duration_seconds"], seconds)
                self.assertEqual(result["profile_name"], profile.name)
                self.assertEqual(result["state"], "running")
                args = thread_factory.call_args.kwargs["args"]
                self.assertEqual(args[1], profile)
                self.assertEqual(args[3], seconds)
                thread.start.assert_called_once()

    def test_preview_handler_rejects_unsupported_duration_before_starting_worker(self):
        profile = SimpleNamespace(name="Saved Narrator")
        project = SimpleNamespace(folder=Path("unused"), chapters=[])
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _assert_no_active_model_lifecycle=lambda _activity: None,
            _find_profile=lambda _name: profile,
            _new_job=Mock(),
            _job_update=Mock(),
            _now=premium_v2_host.PremiumV2Bridge._now,
        )
        with patch.object(premium_v2_host, "load_state", return_value={}), \
             patch.object(premium_v2_host.threading, "Thread") as thread_factory:
            with self.assertRaisesRegex(ValueError, "10, 20, 30, 45, or 60"):
                premium_v2_host.PremiumV2Bridge._voice_preview(
                    bridge, {"profile_name": profile.name, "text": "A preview passage.",
                             "duration_seconds": 15}
                )
        thread_factory.assert_not_called()
        bridge._new_job.assert_not_called()

    def test_preview_worker_reports_requested_and_measured_duration(self):
        profile = SimpleNamespace(name="Saved Narrator")
        provider = object()
        updates = []

        def update(_job_id, **kwargs):
            updates.append(kwargs)
            return kwargs

        bridge = SimpleNamespace(_job_update=update)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def fake_build(_text, _provider, _voice, output_path, **kwargs):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"preview")
                return SimpleNamespace(output_path=output_path, voices_used=("voice-id",), segments=3)

            with patch.object(premium_v2_host, "provider_from_profile", return_value=(provider, "voice-id")) as provider_factory, \
                 patch.object(premium_v2_host, "load_profiles", return_value=[]), \
                 patch.object(premium_v2_host, "app_root", return_value=root), \
                 patch.object(premium_v2_host, "build_voice_preview", side_effect=fake_build) as build, \
                 patch("app.audio.assembler._duration_ms", return_value=30_400):
                premium_v2_host.PremiumV2Bridge._preview_worker(
                    bridge, "preview-job", profile, "A longer source passage.", 30, {}
                )

        provider_factory.assert_called_once_with(profile)
        self.assertEqual(build.call_args.kwargs["target_seconds"], 30)
        completed = next(item for item in updates if item.get("state") == "completed")
        self.assertEqual(completed["result"]["requested_duration_seconds"], 30)
        self.assertEqual(completed["result"]["actual_duration_seconds"], 30.4)
        self.assertEqual(completed["result"]["voices_used"], ["voice-id"])
        self.assertEqual(completed["result"]["segments"], 3)

    def test_preview_worker_fails_closed_when_duration_cannot_be_measured(self):
        profile = SimpleNamespace(name="Saved Narrator")
        provider = object()
        updates = []

        def update(_job_id, **kwargs):
            updates.append(kwargs)
            return kwargs

        bridge = SimpleNamespace(_job_update=update)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def fake_build(_text, _provider, _voice, output_path, **kwargs):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"not-a-readable-audio-file")
                return SimpleNamespace(output_path=output_path, voices_used=("voice-id",), segments=1)

            with patch.object(premium_v2_host, "provider_from_profile", return_value=(provider, "voice-id")):
                with patch.object(premium_v2_host, "load_profiles", return_value=[]):
                    with patch.object(premium_v2_host, "app_root", return_value=root):
                        with patch.object(premium_v2_host, "build_voice_preview", side_effect=fake_build):
                            with patch("app.audio.assembler._duration_ms", side_effect=RuntimeError("probe unavailable")):
                                premium_v2_host.PremiumV2Bridge._preview_worker(
                                    bridge, "preview-job", profile, "A longer source passage.", 30, {}
                                )

        self.assertFalse(any(item.get("state") == "completed" for item in updates))
        failed = next(item for item in updates if item.get("state") == "failed")
        self.assertIn("duration could not be measured", failed["message"])
        self.assertTrue(failed["recoverable"])

    def test_frontend_does_not_mark_unplayable_or_unmeasured_preview_ready(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("!Number.isFinite(actual)||actual<=0", source)
        self.assertIn("return false;", source)
        self.assertIn("const playable=preparePreviewPlayback(job,Number(duration));", source)
        self.assertIn("if($('previewState')&&playable)$('previewState').textContent='Ready · 100%';", source)
        self.assertIn("Preview job completed without a valid measured audio duration", source)



    def test_voice_profile_load_and_voice_design_preset_share_explicit_identity_state(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("applySavedVoiceProfile(profile);", source)
        self.assertIn("selectedVoice=profile.name;profileEditOriginalName=profile.name;", source)
        self.assertIn("selectedVoiceProvider=profile.provider;", source)
        self.assertIn("const label=String(button.textContent||'Custom Description').trim(),name='Qwen VoiceDesign · '+label;", source)
        self.assertIn("selectedVoice=null;selectedVoiceId=null;selectedVoiceProvider='qwen-character';profileEditOriginalName='';", source)

    def test_preview_controls_are_bound_to_validated_audio_and_native_save_dialog(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("if(!previewAudio||!voicePreviewValid)", source)
        self.assertIn("if($('playPreview'))$('playPreview').disabled=!voicePreviewValid;", source)
        self.assertIn("previewAudio.volume=previewVolume", source)
        self.assertIn("previewAudio.ontimeupdate=syncPreviewPlaybackTime", source)
        self.assertIn("voice.preview.save", source)
        self.assertIn("Synthesizing preview · ", source)
        self.assertIn("lastVoicePreviewPath=String(job?.result?.output_path||'')", source)

    def test_provider_catalog_has_normalized_facets_and_optional_category_filter(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("function voiceGenderFacet(row)", source)
        self.assertIn("function voiceCategories(row)", source)
        self.assertIn("optionsFor(categoryLabel?.querySelector('select'),'All categories',categoryValues,'All categories')", source)
        self.assertIn("same(voiceLanguageFacet(row),languageFilter)", source)
        self.assertIn("same(voiceRegionFacet(row),regionFilter)", source)


    def test_preview_save_uses_native_location_picker_and_only_accepts_preview_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            preview_dir = root / "Previews"
            export_dir = root / "chosen-location"
            preview_dir.mkdir()
            export_dir.mkdir()
            source = preview_dir / "preview_voice-test.wav"
            source.write_bytes(b"V" * 2048)
            destination = export_dir / "voice-test.wav"
            bridge = SimpleNamespace()
            with patch.object(premium_v2_host, "app_root", return_value=root), \
                 patch.object(premium_v2_host.QFileDialog, "getSaveFileName",
                              return_value=(str(destination), "WAV audio (*.wav)")) as dialog:
                result = premium_v2_host.PremiumV2Bridge._voice_preview_save(
                    bridge, {"source_path": str(source), "suggested_name": "voice-test"}
                )
            dialog.assert_called_once()
            self.assertEqual(result["path"], str(destination.resolve()))
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertFalse(result["cancelled"])

            external = export_dir / "untrusted.wav"
            external.write_bytes(b"V" * 2048)
            with patch.object(premium_v2_host, "app_root", return_value=root):
                with self.assertRaisesRegex(ValueError, "Only a generated Ryu voice-preview WAV"):
                    premium_v2_host.PremiumV2Bridge._voice_preview_save(
                        bridge, {"source_path": str(external)}
                    )

    def test_character_library_core_keeps_voice_profile_assignment(self):
        from app.core.character_library import list_characters, sync_characters, update_character
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "character_library.json"
            rows = sync_characters("Series A", [{"name": "Mira"}], path=path)
            updated = update_character(rows[0]["id"], {
                "series": "Series A", "primary_name": "Mira", "voice_name": "Qwen Hero"
            }, path=path)
            self.assertEqual(updated["voice_name"], "Qwen Hero")
            self.assertEqual(list_characters(path=path)[0]["voice_name"], "Qwen Hero")


    def test_character_created_from_voice_assignment_enters_matching_active_cast(self):
        from unittest.mock import call
        with tempfile.TemporaryDirectory() as temp:
            project = SimpleNamespace(folder=Path(temp) / "active", title="Series A · Vol 1")
            state = {"characters": []}
            records = []

            def sync_characters(series, rows, **kwargs):
                item = rows[0]
                records.append({
                    "id": "character-1", "series": series,
                    "primary_name": item["name"], "short": item.get("short") or "",
                    "aliases": item.get("aliases") or [], "voice_name": item.get("voice") or "",
                    "notes": item.get("notes") or "", "confidence": 100,
                    "line_count": 0, "chapter_count": 0,
                })
                return records

            bridge = SimpleNamespace(
                _character_library_bootstrap=lambda: None,
                settings=SimpleNamespace(value=lambda key: str(project.folder) if key == "project/active_folder" else ""),
                _find_profile=lambda name: SimpleNamespace(name=name),
                _project_series_name=lambda active_project, active_state: "Series A",
                _now=lambda: "2026-10-24T00:00:00+00:00",
                _sync_saved_cast=Mock(),
                _character_library_ui_record=premium_v2_host.PremiumV2Bridge._character_library_ui_record,
            )
            with patch.object(premium_v2_host, "list_reusable_characters", side_effect=lambda: records), \
                 patch.object(premium_v2_host, "sync_reusable_characters", side_effect=sync_characters), \
                 patch.object(premium_v2_host, "list_projects", return_value=[project]), \
                 patch.object(premium_v2_host, "load_state", return_value=state), \
                 patch.object(premium_v2_host, "save_state") as save_state:
                result = premium_v2_host.PremiumV2Bridge._character_library_save(
                    bridge, {
                        "name": "Mira", "series": "Series A", "scope": "Series · Series A",
                        "short": "Mira", "aliases": [], "voice_profile": "Qwen Anime Hero",
                    }
                )

            self.assertTrue(result["saved"])
            self.assertTrue(result["project_updated"])
            self.assertEqual(len(state["characters"]), 1)
            self.assertEqual(state["characters"][0]["name"], "Mira")
            self.assertEqual(state["characters"][0]["voice_profile"], "Qwen Anime Hero")
            save_state.assert_called_once()
            bridge._sync_saved_cast.assert_called_once_with(
                project, state["characters"], state, update_names=False, update_voice=True
            )


    def test_premium_v2_adapter_passes_javascript_syntax_check(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed on this test runner.")
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        result = subprocess.run(
            [node, "--check", str(adapter)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


    def test_elevenlabs_web_opener_only_allows_official_destinations(self):
        bridge = SimpleNamespace()
        with patch.object(premium_v2_host.QDesktopServices, "openUrl", return_value=True) as open_url:
            studio = premium_v2_host.PremiumV2Bridge._elevenlabs_open_web(bridge, {"target": "studio"})
            self.assertTrue(studio["opened"])
            self.assertEqual(studio["url"], "https://elevenlabs.io/text-to-speech")
            self.assertEqual(open_url.call_args.args[0].toString(), studio["url"])

            keys = premium_v2_host.PremiumV2Bridge._elevenlabs_open_web(bridge, {"target": "api_keys"})
            self.assertTrue(keys["opened"])
            self.assertEqual(keys["url"], "https://elevenlabs.io/app/settings/api-keys")
            self.assertEqual(open_url.call_args.args[0].toString(), keys["url"])

        with patch.object(premium_v2_host.QDesktopServices, "openUrl", return_value=True) as open_url:
            with self.assertRaisesRegex(ValueError, "official ElevenLabs"):
                premium_v2_host.PremiumV2Bridge._elevenlabs_open_web(
                    bridge, {"target": "https://malicious.example"}
                )
            open_url.assert_not_called()

    def test_voice_catalog_refreshes_do_not_rebuild_unchanged_dropdowns(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("select.dataset.backendOptionsSignature === signature", source)
        self.assertIn("profileSelect.dataset.savedOptionsSignature !== optionSignature", source)
        self.assertIn("row.region_name,row.accent,row.gender,row.category,row.use_case", source)

    def test_elevenlabs_without_api_key_exposes_manual_website_route_and_blocks_in_app_creation(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn('"elevenlabs.open_web": self._elevenlabs_open_web', 
                      (Path(__file__).resolve().parents[1] / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8"))
        self.assertIn("button.disabled = !result.ready", source)
        self.assertIn("Ryu cannot fetch account audio without supported API access.", source)
        self.assertIn("call('elevenlabs.open_web',{target:'api_keys'})", source)
        self.assertIn("data-open-elevenlabs-web", source)


    def test_loaded_profile_updates_every_preview_target_identity_field(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("function updatePreviewTarget(profile,libraryLabel,key)", source)
        for field in ("profileLibrary", "profileVoice", "previewLibrary", "previewProvider",
                      "previewVoice", "previewModel", "previewProfile"):
            self.assertIn(field + ":", source)
        self.assertIn("updatePreviewTarget(profile,libraryLabel,key);", source)
        self.assertIn("model=profile?.qwen_mode==='design'?'VoiceDesign'", source)

if __name__ == "__main__":
    unittest.main()
