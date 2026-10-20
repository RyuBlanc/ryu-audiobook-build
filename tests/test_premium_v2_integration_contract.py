from pathlib import Path
import re
import unittest
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"
MAIN = ROOT / "app" / "main.py"
BUILD = ROOT / "build.py"


class PremiumV2IntegrationContractTests(unittest.TestCase):
    """Static release guards for the embedded Premium V2 frontend and bridge."""

    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.host = HOST.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.build = BUILD.read_text(encoding="utf-8")

    def test_authoritative_html_has_all_fifteen_destinations(self):
        self.assertTrue(HTML.is_file())
        soup = BeautifulSoup(self.html, "html.parser")
        destinations = [button.get("data-page") for button in soup.select("button.nav-btn[data-page]")]
        self.assertEqual(
            destinations,
            ["dashboard", "library", "import", "chapters", "voices", "characters",
             "pronunciation", "sound", "generate", "player", "history", "models",
             "performance", "settings", "help"],
        )
        for page in destinations:
            self.assertRegex(self.html, rf'<section[^>]+id="{re.escape(page)}"')

    def test_embedded_host_uses_local_html_and_qt_webchannel(self):
        self.assertIn("QWebEngineView", self.host)
        self.assertIn("QWebChannel", self.host)
        self.assertIn("QUrl.fromLocalFile", self.host)
        self.assertIn("qrc:///qtwebchannel/qwebchannel.js", self.host)
        self.assertIn("JavascriptCanOpenWindows, False", self.host)
        self.assertIn("def dispatch(", self.host)

    def test_voice_preview_bridge_accepts_every_supported_duration_target(self):
        # Keep the real desktop bridge aligned with the frontend and duration regression suite.
        self.assertIn("if seconds not in {10, 20, 30, 45, 60}:", self.host)
        self.assertIn("Preview duration must be 10, 20, 30, 45, or 60 seconds.", self.host)
        self.assertIn("for requested_seconds in (10, 20, 30, 45, 60):", (ROOT / "tests" / "test_stage823_preview_duration_acceptance.py").read_text(encoding="utf-8"))

    def test_only_real_bridge_commands_are_advertised_as_connected(self):
        self.assertIn('"app.get_info": True', self.host)
        self.assertIn('"project.list": True', self.host)
        self.assertIn('"settings.get": True', self.host)
        self.assertIn('"project.open": True', self.host)
        self.assertIn('"chapter.list": True', self.host)
        self.assertIn('"chapter.update": True', self.host)
        # New commands must point to real handlers; never preserve the old
        # "not connected" placeholders as release requirements.
        for command, handler in {
            "import.start": "_import_start",
            "voice.list": "_voice_list",
            "voice.select": "_voice_select",
            "voice.preview": "_voice_preview",
            "voice.save": "_voice_save",
            "voice.import_reference": "_voice_import_reference",
            "character.analyze": "_character_analyze",
            "character.update": "_character_update",
            "character.delete": "_character_delete",
            "pronunciation.save": "_pronunciation_save",
            "production.generate_book": "_production_generate_book",
            "job.list": "_job_list",
            "history.list": "_history_list",
            "sound.catalog": "_sound_catalog",
        }.items():
            self.assertIn(f'"{command}": self.{handler}', self.host)
        self.assertIn('"project.create": False', self.host)
        self.assertIn('"production.generate_book": True', self.host)
        self.assertIn('"voice.save": True', self.host)
        self.assertIn('"voice.import_reference": True', self.host)
        self.assertIn('"models.install": self._models_install', self.host)
        self.assertIn('"models.install": True', self.host)
        self.assertIn('"character.update": True', self.host)
        self.assertIn('"character.delete": True', self.host)
        self.assertIn('match = re.search(r"(?<!\\d)(\\d{1,3})%", detail)', self.host)
        self.assertIn("Confirm that you have permission", self.host)
        self.assertIn("def _voice_save(", self.host)
        self.assertIn('if provider_name == "chatterbox" and not voice_id:', self.host)
        self.assertIn("voice_id = name", self.host)
        self.assertIn("def _voice_import_reference(", self.host)
        self.assertIn("def _generation_finished(", self.host)
        self.assertIn("from app.tts.cast_provider import CastAwareProvider", self.host)
        self.assertIn("cast_assignments[character_name] = assigned_profile.name", self.host)
        self.assertIn("provider = CastAwareProvider(", self.host)
        self.assertIn("def _import_worker(", self.host)
        self.assertIn("not_connected", self.host)

    def test_authoritative_html_remains_presentation_source_and_adapter_owns_backend_calls(self):
        # The approved HTML stays visually authoritative and free of injected bridge edits.
        self.assertIn("<title>Ryu's Audiobook · Dragon Studio</title>", self.html)
        self.assertNotIn("window.ryuBackend", self.html)
        for control in ("browseBtn", "saveChapter", "saveProfile", "analyzeCharacters", "startGenerate"):
            self.assertRegex(self.html, rf'id="{re.escape(control)}"')
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("call('project.list')", adapter)
        self.assertIn("call('chapter.list')", adapter)
        self.assertIn("call('chapter.update'", adapter)
        self.assertIn("call('import.start'", adapter)
        self.assertIn("call('voice.save'", adapter)
        self.assertIn("call('character.analyze'", adapter)
        self.assertIn("call('production.generate_book'", adapter)

    def test_backend_adapter_is_loaded_and_bundled(self):
        adapter = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        self.assertTrue(adapter.is_file())
        script = adapter.read_text(encoding="utf-8")
        for command in (
            "project.list", "project.open", "import.choose_file", "import.start", "chapter.update",
            "voice.list", "voice.save", "voice.import_reference", "voice.preview",
            "character.analyze", "character.assign", "character.update", "character.delete", "pronunciation.list",
            "pronunciation.save", "pronunciation.analyze", "production.preview",
            "production.generate_book", "player.get_active", "job.list", "job.pause", "job.resume",
            "job.cancel", "settings.save", "sound.catalog", "sound.import", "sound.assign", "sound.save_manifest", "models.install",
        ):
            self.assertIn(command, script)
        self.assertIn('adapter_path = frontend_path().with_name("premium_v2_backend_adapter.js")', self.host)
        self.assertIn('adapter_path.read_text(encoding="utf-8")', self.host)
        self.assertIn("premium_v2_backend_adapter.js", self.build)
        self.assertIn("function preparePreviewPlayback(job, requestedSeconds)", script)
        self.assertIn("previewAudio.play()", script)
        self.assertIn("previewAudio.pause()", script)
        self.assertIn("lengthGroup?.querySelector('.seg button.active')", script)
        self.assertIn("duration_seconds:Number(duration)", script)
        self.assertIn("function openPlayer()", script)
        self.assertIn("playerAudio.play()", script)
        self.assertIn("async function refreshHistory()", script)
        self.assertIn("async function refreshModels()", script)
        self.assertIn("call('diagnostics.check')", script)
        self.assertIn("call('models.install'", script)
        self.assertIn("qwen_mode:provider === 'qwen-character' ? qwenMode", script)
        self.assertIn("qwen_prompt:choice === 'voicedesign' ? designPrompt", script)
        self.assertIn("qwen_seed:choice === 'voicedesign' ? designSeed", script)
        self.assertIn("call('character.update'", script)
        self.assertIn("call('character.delete'", script)
        self.assertIn("voices.map(v=>'<option value=", script)
        self.assertIn("window.confirm('Remove", script)

    def test_preview_ui_reports_requested_vs_actual_duration(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("function preparePreviewPlayback(job, requestedSeconds)", adapter)
        self.assertIn("Preview shorter than requested", adapter)
        self.assertIn("requested_duration_seconds", adapter)
        self.assertIn("preparePreviewPlayback(job, Number(duration))", adapter)

    def test_chapter_split_is_persisted_and_connected_to_visible_control(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('"chapter.split": self._chapter_split', self.host)
        self.assertIn("def _chapter_split(self, payload: dict[str, Any])", self.host)
        self.assertIn("project.chapters.insert(index + 1, new_chapter)", self.host)
        self.assertIn("project.save()", self.host[self.host.index("def _chapter_split"):self.host.index("def _voice_import_reference")])
        self.assertIn("Both sides of a split must contain text.", self.host)
        self.assertIn("textContent.trim().toLowerCase() === 'split chapter'", adapter)
        self.assertIn("call('chapter.split'", adapter)
        self.assertIn("split_at:splitAt", adapter)
        self.assertIn("window.ryuPremiumSelectedChapter = result.new_number", adapter)
        self.assertIn("Cancel a queued snapshot and wait for any already-started save before persisting the split.", adapter)
        self.assertIn("if (chapterSaveTimer) { clearTimeout(chapterSaveTimer); chapterSaveTimer = null; }", adapter)
        self.assertIn("await chapterSavePromise.catch(() => {});", adapter)
        self.assertIn("Serialize snapshots so a slower earlier save can never overwrite newer text.", adapter)
        self.assertIn("$('chapterEditor').addEventListener('input'", adapter)
        self.assertIn("chapterSaveTimer = setTimeout", adapter)
        self.assertIn("Autosaved just now", adapter)
        self.assertIn("Chapter autosave failed:", adapter)

    def test_voice_preview_uses_saved_character_voice_assignments(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        worker = host.split("def _preview_worker", 1)[1].split("def _character_list", 1)[0]
        self.assertIn("available_profiles = {p.name.casefold(): p for p in load_profiles()}", worker)
        self.assertIn("from app.tts.cast_provider import CastAwareProvider", worker)
        self.assertIn("cast_assignments[character_name] = assigned_profile.name", worker)
        self.assertIn("target_seconds=seconds", worker)
        self.assertIn('"actual_duration_seconds": duration', worker)

    def test_file_input_and_dropzone_start_real_import_jobs(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("async function importDroppedFile(file)", adapter)
        self.assertIn("content_base64:btoa(binary)", adapter)
        self.assertIn("$('fileInput').onchange", adapter)
        self.assertIn("$('dropzone').ondrop", adapter)
        self.assertIn("await startImportPayload", adapter)
        self.assertNotIn("simulateImport", adapter)
        self.assertIn("base64.b64decode(encoded, validate=True)", self.host)
        self.assertIn("Dropped files are limited to 25 MB.", self.host)

    def test_dashboard_recent_projects_and_actions_are_backend_driven(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("dash.querySelector('.recent-grid')", adapter)
        self.assertIn("data-project-folder=", adapter)
        self.assertIn("e.target.closest('#dashboard .recent-grid [data-project-folder]')", adapter)
        self.assertIn("label === 'continue project'", adapter)
        self.assertIn("label === 'view job'", adapter)
        self.assertIn("dashboardButton.id === 'pauseDash'", adapter)
        self.assertIn("call('project.get_active')", adapter)

    def test_library_search_and_filters_use_real_project_records(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("e.target?.id === 'librarySearch'", adapter)
        self.assertIn("e.target.closest('#libraryFilters button')", adapter)
        self.assertIn("refreshProjects().catch", adapter)
        self.assertIn("call('project.list')", adapter)
        self.assertIn("No local projects found. Import a book to start your library.", adapter)

    def test_sound_design_controls_do_not_fall_back_to_prototype_success_toasts(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("#importMusicTracks, #importCueClips, #previewSelectedTrack", adapter)
        self.assertIn("call('sound.import')", adapter)
        self.assertIn("call('sound.assign'", adapter)
        self.assertIn("call('sound.save_manifest'", adapter)
        self.assertIn("The selected local audio file could not be played", adapter)
        self.assertIn("Per-chapter BGM overrides are not connected yet.", adapter)
        self.assertIn("Story cue assignments are not connected to persistent backend storage yet", adapter)
        self.assertIn("Cue search is unavailable because chapter cue assets are not yet connected", adapter)

    def test_background_jobs_screen_uses_backend_state_and_actions(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("let backendJobFilter = 'active'", adapter)
        self.assertIn("call('job.list', {include_hidden:false})", adapter)
        self.assertIn("data-backend-job=", adapter)
        self.assertIn("stopImmediatePropagation()", adapter)
        self.assertIn("const commands = {pause:'job.pause',resume:'job.resume',cancel:'job.cancel'}", adapter)
        self.assertIn("call(commands[b.dataset.jobAction] || 'job.cancel'", adapter)
        self.assertIn("call('job.clear_completed')", adapter)
        self.assertIn("window.__ryuBackendJobsObserver", adapter)
        self.assertIn("No backend jobs in this view.", adapter)
        self.assertIn("const canControlGeneration = j.type === 'audiobook-generation'", adapter)
        self.assertIn("j.type === 'audiobook-generation' && j.state === 'running'", adapter)
        self.assertIn("const resumable = rows.filter(j => j.type === 'audiobook-generation' && ['paused','pause_requested'].includes(j.state))", adapter)
        self.assertIn("call('job.resume', {job_id:job.job_id})", adapter)
        self.assertIn("No active audiobook generation jobs support pause or resume.", adapter)

    def test_every_static_adapter_backend_call_has_an_allowlisted_handler(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        # Static command calls from the frontend adapter must all be registered in
        # the desktop bridge dispatch table. Dynamic command maps have separate
        # explicit coverage in their feature-specific tests.
        commands = set(re.findall(r"\bcall\(['\"]([^'\"\n]+)['\"]", adapter))
        registered = set(re.findall(r'"([a-z][a-z0-9_.]+)": self\._[A-Za-z0-9_]+', self.host))
        self.assertTrue(commands, "Expected frontend adapter to call backend commands")
        self.assertEqual(commands - registered, set(), "Adapter commands without backend handlers: " + repr(sorted(commands - registered)))

    def test_frontend_is_packaged_and_selected_by_desktop_entrypoint(self):
        self.assertIn("ryu_audiobook_premium_v2.html", self.build)
        self.assertIn("PremiumV2Window", self.main)
        self.assertIn("frontend_path().is_file()", self.main)

    def test_production_skips_empty_chapters_and_rejects_all_empty_books(self):
        start = self.host.index("def _production_generate_book")
        end = self.host.index("def _generation_progress", start)
        worker = self.host[start:end]
        self.assertIn("chapters = [c for c in project.chapters if (c.text or \"\").strip()]", worker)
        self.assertIn("skipped = len(project.chapters) - len(chapters)", worker)
        self.assertIn("if not chapters:", worker)
        self.assertIn("No chapters contain narration text. Restore chapter text before generating.", worker)
        self.assertIn('"empty_chapters_skipped": skipped', worker)
        self.assertIn("Render {len(chapters)} non-empty chapter(s)", worker)


if __name__ == "__main__":
    unittest.main()


    def test_preview_duration_setting_accepts_every_supported_target(self):
        self.assertIn('if key == "preview_seconds" and int(value) not in {10, 20, 30, 45, 60}:', self.host)
        self.assertIn('Preview duration must be 10, 20, 30, 45, or 60 seconds.', self.host)

