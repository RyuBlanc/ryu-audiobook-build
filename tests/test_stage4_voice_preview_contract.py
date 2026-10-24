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
        for seconds in (10, 20, 30, 45, 60, 90):
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
            with self.assertRaisesRegex(ValueError, "10, 20, 30, 45, 60, or 90"):
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


    def test_voice_details_and_assignment_summary_are_loaded_or_empty(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("function ensureVoiceProfileDetails()", source)
        self.assertIn("'Voice ID':'detailVoiceId'", source)
        self.assertIn("'Language':'detailLanguage'", source)
        self.assertIn("detailAuthorization", source)
        self.assertIn("if($('sumAssign'))$('sumAssign').textContent='';", source)
        self.assertIn("if($('sumAssign'))$('sumAssign').textContent=primary;", source)


    def test_elevenlabs_catalog_renders_without_reusing_voice_design_form(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("if (!form && providerKey !== 'eleven') return;", source)
        self.assertIn("if (form) {", source)
        self.assertIn("listHost = panel.querySelector('[data-epanel=\"mine\"]');", source)
        self.assertIn("Render its My Voices catalogue directly without mutating those controls.", source)


    def test_provider_health_labels_follow_actual_catalog_readiness(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("profileHealthRow", source)
        self.assertIn("sideHealthRow", source)
        self.assertIn("const label=!result?'Checking…':result.ready?'Ready':'Setup required';", source)
        self.assertIn("updateVoiceHealthIndicator(providerKey,result);", source)


    def test_provider_filter_option_rows_are_not_rebuilt_when_unchanged(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("select.dataset.voiceFacetOptionsSignature!==signature", source)
        self.assertIn("const optionRows=[[defaultValue,defaultLabel],...values.map(value=>[value,value])];", source)
        self.assertIn("Recreating these controls on every polling refresh causes", source)
        self.assertIn("a visible flash and can steal keyboard focus from the active filter.", source)

    def test_native_preview_completion_is_bound_to_the_request_and_profile(self):
        voice_page = Path(__file__).resolve().parents[1] / "app" / "ui" / "voice_page.py"
        source = voice_page.read_text(encoding="utf-8")
        self.assertIn("self._preview_request_id = int(getattr(self, \"_preview_request_id\", 0)) + 1", source)
        self.assertIn("self._preview_requested_signature = self._voice_profile_signature(profile)", source)
        self.assertIn("if not self._preview_request_is_current(request_id):", source)
        self.assertIn("requested_signature is not None and active_signature != requested_signature", source)
        self.assertIn('tempfile.mkdtemp(prefix="ryu_audiobook_voice_preview_")', source)
        self.assertIn("self._discard_preview_output(path)", source)

    def test_voice_combo_refresh_does_not_rebuild_identical_rows_and_preserves_selection(self):
        from types import SimpleNamespace
        from app.ui.voice_page import VoicePage

        class MemoryCombo:
            def __init__(self, items, index):
                self.items = list(items)
                self.index = index
                self.blocked = False
                self.rebuilds = 0

            def count(self):
                return len(self.items)

            def itemText(self, index):
                return self.items[index][0]

            def itemData(self, index):
                return self.items[index][1]

            def currentData(self):
                return self.items[self.index][1] if 0 <= self.index < len(self.items) else None

            def blockSignals(self, blocked):
                previous = self.blocked
                self.blocked = blocked
                return previous

            def clear(self):
                self.rebuilds += 1
                self.items.clear()
                self.index = -1

            def addItem(self, label, data):
                self.items.append((label, data))
                if self.index < 0:
                    self.index = 0

            def findData(self, data):
                return next((i for i, (_, value) in enumerate(self.items) if value == data), -1)

            def setCurrentIndex(self, index):
                self.index = index

        combo = MemoryCombo([("Voice A", "a"), ("Voice B", "b")], 1)
        page = SimpleNamespace(neural_voice=combo)
        self.assertFalse(VoicePage._set_voice_combo_items(page, [("Voice A", "a"), ("Voice B", "b")]))
        self.assertEqual(combo.rebuilds, 0)
        self.assertEqual(combo.currentData(), "b")

        self.assertTrue(VoicePage._set_voice_combo_items(
            page, [("Voice A updated", "a"), ("Voice B", "b"), ("Voice C", "c")]
        ))
        self.assertEqual(combo.currentData(), "b")
        self.assertEqual(combo.items[0][0], "Voice A updated")

    def test_native_saved_profile_restores_qwen_language_and_saved_name(self):
        voice_page = Path(__file__).resolve().parents[1] / "app" / "ui" / "voice_page.py"
        source = voice_page.read_text(encoding="utf-8")
        self.assertIn("self.qwen_design_language.findText(profile.language or \"\")", source)
        self.assertIn('profile.provider in {"piper", "kokoro", "edge-tts", "elevenlabs"}', source)
        self.assertIn("self.name.setText(profile.name)", source)
        self.assertIn("self.saved_profiles.setCurrentIndex(selected_profile_index)", source)
        self.assertIn("No substitute voice was selected", source)

    def test_preview_worker_callbacks_are_routed_through_queued_qobject_slots(self):
        voice_page = Path(__file__).resolve().parents[1] / "app" / "ui" / "voice_page.py"
        source = voice_page.read_text(encoding="utf-8")
        self.assertIn("class VoicePreviewCallbackRouter(QObject)", source)
        for callback in ("on_status", "on_progress", "on_success", "on_failure", "on_cancelled", "on_thread_finished"):
            self.assertIn("def " + callback + "(", source)
        self.assertIn("worker.status.connect(router.on_status)", source)
        self.assertIn("worker.finished_ok.connect(router.on_success)", source)
        self.assertNotIn("worker.status.connect(\n            lambda", source)
        self.assertNotIn("worker.progress.connect(\n            lambda", source)
    def test_native_voice_assignment_syncs_only_assigned_character_to_series_library(self):
        voice_page = Path(__file__).resolve().parents[1] / "app" / "ui" / "voice_page.py"
        source = voice_page.read_text(encoding="utf-8")
        method = source[source.index("    def assign_to_character("):source.index("    def _set_voice_step(")]
        self.assertIn("from app.core.character_library import sync_characters", source)
        self.assertIn("sync_characters(\n                    series,\n                    [source_row]", method)
        self.assertIn('source_row = {"name": character, "voice": saved_profile.name}', method)
        self.assertIn('source_row["aliases"] = list(roster_row["aliases"])', method)
        self.assertIn("update_voice=True", method)
        self.assertIn('state["voice_cast"] = assignments', method)
        self.assertIn("but Character Library sync failed", method)
    def test_missing_saved_native_voice_stays_visible_without_substitution(self):
        voice_page = Path(__file__).resolve().parents[1] / "app" / "ui" / "voice_page.py"
        source = voice_page.read_text(encoding="utf-8")
        self.assertIn("_missing_catalog_voice_profile", source)
        self.assertIn("saved voice (catalogue unavailable)", source)
        self.assertIn("No substitute voice was selected", source)
        self.assertIn("selected_voice_changed = previous_voice_id != self.neural_voice.currentData()", source)
        self.assertIn('not getattr(self, "_restoring_saved_profile", False)', source)

    def test_character_library_normalizes_fractional_confidence_and_preserves_it_on_voice_update(self):
        from app.core.character_library import list_characters, sync_characters

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "character_library.json"
            sync_characters(
                "Series Confidence",
                [{"name": "Mira", "confidence": 0.82, "voice": "Original Voice"}],
                path=path,
            )
            row = list_characters(series="Series Confidence", path=path)[0]
            self.assertEqual(row["confidence"], 82)
            self.assertEqual(row["voice_name"], "Original Voice")

            sync_characters(
                "Series Confidence",
                [{"name": "Mira", "voice": "Updated Voice"}],
                update_voice=True,
                path=path,
            )
            row = list_characters(series="Series Confidence", path=path)[0]
            self.assertEqual(row["confidence"], 82)
            self.assertEqual(row["voice_name"], "Updated Voice")

    def test_character_library_clamps_percentage_confidence(self):
        from app.core.character_library import list_characters, sync_characters

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "character_library.json"
            sync_characters(
                "Series Confidence",
                [{"name": "Mira", "confidence": 135, "voice": "Voice"}],
                path=path,
            )
            self.assertEqual(
                list_characters(series="Series Confidence", path=path)[0]["confidence"],
                100,
            )

    def test_qwen_voice_design_preview_uses_the_friendly_preset_name(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("function voiceDisplayName(profile)", source)
        for friendly in ("Anime Heroine", "Anime Hero", "Anime Rival", "Anime Villain", "Anime Healer"):
            self.assertIn("return '" + friendly + "';", source)
        # These aliases match the prompt wording emitted by native VoicePage.py.
        for native_prompt in (
            "prompt.includes('anime protagonist timbre')",
            "prompt.includes('anime rival timbre')",
            "prompt.includes('anime villain timbre')",
            "prompt.includes('anime healer timbre')",
        ):
            self.assertIn(native_prompt, source)
        self.assertIn("presetName.includes('anime hero')", source)
        self.assertIn("const voice=voiceDisplayName(profile);", source)

    def test_native_preview_stop_invalidates_queued_completion_and_waits_for_worker_cleanup(self):
        from app.ui.voice_page import VoicePage

        worker = Mock()
        worker.isRunning.return_value = True
        player = SimpleNamespace(stop=Mock(), setSource=Mock())
        preview_button = Mock()
        preview_button.isEnabled.return_value = False
        page = SimpleNamespace(
            preview_worker=worker,
            last_preview=None,
            player=player,
            preview_button=preview_button,
            play_button=Mock(),
            save_preview_button=Mock(),
            preview_activity_bar=Mock(),
            preview_engine_status=Mock(),
            status=Mock(),
            _preview_request_id=7,
            _preview_requested_signature=("voice",),
            _preview_profile_signature=("voice",),
        )
        page._is_live_qt_object = lambda value: value is not None

        VoicePage.stop_preview_or_playback(page)

        self.assertEqual(page._preview_request_id, 8)
        self.assertIsNone(page._preview_requested_signature)
        self.assertIsNone(page._preview_profile_signature)
        worker.cancel.assert_called_once()
        player.stop.assert_called_once()
        player.setSource.assert_called_once()
        preview_button.setEnabled.assert_called_with(False)
        page.play_button.setEnabled.assert_called_with(False)

    def test_native_stale_preview_finish_reenables_preview_after_worker_exit(self):
        from app.ui.voice_page import VoicePage

        worker = object()
        preview_button = Mock()
        activity_bar = Mock()
        progress_bar = Mock()
        discarded = []
        page = SimpleNamespace(
            _preview_request_is_current=lambda _request_id=None: False,
            _is_live_qt_object=lambda value: value is not None,
            preview_worker=worker,
            preview_button=preview_button,
            preview_activity_bar=activity_bar,
            preview_percent_bar=progress_bar,
            last_preview=None,
            _discard_preview_output=lambda path: discarded.append(path),
        )
        stale_path = Path(tempfile.gettempdir()) / "stale_voice_preview.wav"

        VoicePage._preview_worker_finished(page, 7, worker, stale_path)

        self.assertIsNone(page.preview_worker)
        preview_button.setEnabled.assert_called_with(True)
        activity_bar.setVisible.assert_called_with(False)
        progress_bar.setValue.assert_called_with(0)
        self.assertEqual(discarded, [stale_path])

    def test_native_playback_button_state_and_replay_after_end_of_media(self):
        from app.ui.voice_page import QMediaPlayer, VoicePage

        page = SimpleNamespace(
            _is_live_qt_object=lambda value: value is not None,
            play_button=Mock(),
        )
        VoicePage._playback_state_changed(page, QMediaPlayer.PlaybackState.PlayingState)
        page.play_button.setText.assert_called_with("Ⅱ  Pause")
        VoicePage._playback_state_changed(page, QMediaPlayer.PlaybackState.StoppedState)
        page.play_button.setText.assert_called_with("▶  Play")

        with tempfile.TemporaryDirectory() as temp:
            preview = Path(temp) / "preview.wav"
            preview.write_bytes(b"preview")

            player = SimpleNamespace(
                playbackState=Mock(return_value=QMediaPlayer.PlaybackState.StoppedState),
                mediaStatus=Mock(return_value=QMediaPlayer.MediaStatus.EndOfMedia),
                duration=Mock(return_value=12000),
                position=Mock(return_value=12000),
                setPosition=Mock(),
                play=Mock(),
                pause=Mock(),
            )
            playback_page = SimpleNamespace(last_preview=preview, player=player)
            VoicePage.play_last_preview(playback_page)
            player.setPosition.assert_called_once_with(0)
            player.play.assert_called_once()

    def test_native_preview_refuses_to_overlap_an_unwinding_worker(self):
        from app.ui.voice_page import VoicePage

        worker = Mock()
        worker.isRunning.return_value = True
        page = SimpleNamespace(
            preview_worker=worker,
            status=Mock(),
            _is_live_qt_object=lambda value: value is not None,
        )

        VoicePage.preview(page)

        page.status.setText.assert_called_once()
        self.assertIn("still stopping", page.status.setText.call_args.args[0])

    def test_voice_cast_refresh_updates_stable_rows_in_place_to_reduce_flicker(self):
        voice_cast = Path(__file__).resolve().parents[1] / "app" / "ui" / "voice_cast_page.py"
        source = voice_cast.read_text(encoding="utf-8")
        start = source.index("    def _refresh_labels(")
        end = source.index("    def _save_cast(", start)
        refresh = source[start:end]
        self.assertIn("stable_order = current_names == desired_names", refresh)
        self.assertIn("item.setText(label)", refresh)
        self.assertIn("item.setData(Qt.ItemDataRole.UserRole, name)", refresh)
        self.assertIn("if not stable_order and updates_were_enabled:", refresh)
        self.assertIn("self.list.clear()", refresh)
        details_start = source.index("    def show_details(")
        details_end = source.index("    def assign_voice(", details_start)
        details = source[details_start:details_end]
        self.assertIn("if self.details.text() != details_text:", details)
        self.assertIn("if self.examples.toPlainText() != example_text:", details)


    def test_html_studio_controls_include_delete_batch_and_duration_flicker_guards(self):
        adapter = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("ensurePreviewDurationOptions", adapter)
        self.assertIn("90 seconds", adapter)
        self.assertIn("90s", adapter)
        self.assertIn("ryuDeleteCurrentChapter", adapter)
        self.assertIn("ryuDeleteSelectedChapters", adapter)
        self.assertIn("chapterDeleteSelection", adapter)
        self.assertIn("window.__ryuDialogueReviewRenderSignature", adapter)
        self.assertIn("panel.dataset.ryuLiveInsightsSignature", adapter)
        self.assertIn("document.activeElement === box", adapter)
        self.assertIn("call('project.get_active')", adapter)
        self.assertIn("function refreshCurrentProjectCard", adapter)
        self.assertIn("installProjectCardStatusObserver", adapter)
        self.assertIn("titleNode.title = title", adapter)
        self.assertIn("setProjectCardStatus(status)", adapter)

    def test_successful_qwen_preview_is_cached_but_full_generation_releases_it(self):
        host = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("self._cache_preview_provider(cache_signature, provider, voice)", host)
        self.assertIn("threading.Timer(90.0, self._expire_preview_provider_cache", host)
        generation = host[host.index("def _production_generate_book"):host.index("def _production_preview")]
        self.assertIn('close_cache = getattr(self, "close_preview_provider_cache", None)', generation)
        self.assertIn("if callable(close_cache):", generation)
        self.assertIn("close_cache()", generation)
        self.assertIn("close_preview_provider_cache", host[host.index("class PremiumV2Window"):])


if __name__ == "__main__":
    unittest.main()
