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
        self.assertIn('"chapter.split": True', self.host)
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
        self.assertIn('"diagnostics.export_logs": self._diagnostics_export_logs', self.host)
        self.assertIn('"diagnostics.export_logs": True', self.host)
        self.assertIn("def _sanitize_diagnostic_text(", self.host)
        self.assertIn("Bearer [REDACTED]", self.host)
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("call('diagnostics.export_logs')", adapter)
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
            "job.cancel", "settings.save", "sound.catalog", "sound.import", "sound.assign", "sound.save_manifest",
            "sound.cues.get", "sound.cues.save", "sound.cues.clear", "sound.chapter_bgm.get", "sound.chapter_bgm.save", "models.install",
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

    def test_chapter_merge_preserves_assignment_offsets_and_final_chapter(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('if len(project.chapters) <= 1:', host)
        self.assertIn('A project must keep at least one chapter.', host)
        self.assertIn('assignment_offset = len(previous_text + separator)', host)
        self.assertIn('removed_leading = len(current_original) - len(current_text)', host)
        self.assertIn('shifted["start"] = max(0, shifted["start"] - removed_leading) + assignment_offset', host)
        self.assertIn('shifted["end"] = max(0, shifted["end"] - removed_leading) + assignment_offset', host)
        self.assertIn('await persistChapterSnapshot(number,', adapter)
        self.assertIn("await chapterSavePromise.catch(() => {});", adapter)

    def test_chapter_operations_missing_from_visual_controls_are_reachable_contextually(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for command, handler in {
            "chapter.add": "_chapter_add",
            "chapter.delete": "_chapter_delete",
            "chapter.reorder": "_chapter_reorder",
            "chapter.merge": "_chapter_merge",
        }.items():
            self.assertIn(f'"{command}": self.{handler}', host)
            self.assertIn(f'"{command}": True', host)
            self.assertIn("call('" + command + "'", adapter)
        for action in ("add", "rename", "delete", "up", "down", "merge"):
            self.assertIn(action, adapter[adapter.index("Chapter actions for"):adapter.index("if ($('chapterEditor')) $('chapterEditor').addEventListener")])

    def test_import_detects_exact_content_duplicates_before_creating_a_job(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("import hashlib", host)
        self.assertIn("source_digest = hashlib.sha256(path.read_bytes()).hexdigest()", host)
        self.assertIn("for existing_project in list_projects():", host)
        self.assertIn("existing_digest = hashlib.sha256(existing_source.read_bytes()).hexdigest()", host)
        self.assertIn("Open that project from Audiobook Library instead of importing a duplicate.", host)
        self.assertLess(host.index("source_digest = hashlib.sha256(path.read_bytes()).hexdigest()"),
                        host.index('job_id = self._new_job("import", "Import " + title'))

    def test_import_cancel_is_checked_at_safe_boundaries_and_staged_files_are_cleaned(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("self._import_cancel_events: dict[str, threading.Event]", host)
        self.assertIn("cancel_event.is_set()", host)
        self.assertIn("Import cancelled before creating a project", host)
        self.assertIn("self._import_cancel_events.pop(job_id, None)", host)
        self.assertIn('incoming_root = (app_root() / "incoming_imports").resolve()', host)
        self.assertIn("const canCancelImport = j.type === 'import'", adapter)
        self.assertIn("call(commands[b.dataset.jobAction] || 'job.cancel'", adapter)

    def test_malformed_imports_report_actionable_format_specific_diagnostics(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("def _format_import_error(path: Path, error: Exception", host)
        self.assertIn("scanned pages may require OCR", host)
        self.assertIn("re-exporting it or importing a TXT/DOCX copy", host)
        self.assertIn("password-protected or damaged", host)
        self.assertIn("source file was preserved", host)

    def test_import_report_includes_source_and_chapter_review_warning(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('"source_file": str(project.source_path or path)', host)
        self.assertIn('Detected {len(chapters)} chapter(s); review chapter boundaries before production.', host)
        self.assertIn('shutil.copy2(source_path, destination)', (ROOT / "app" / "core" / "project.py").read_text(encoding="utf-8"))

    def test_chapter_clean_button_uses_backend_cleaner(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("call('chapter.clean',{text:source})", adapter)
        self.assertIn("typeof result.text!=='string'", adapter)
        self.assertIn("def _chapter_clean(self, payload: dict[str, Any])", host)
        self.assertIn('"chapter.clean": self._chapter_clean', host)
        self.assertIn("clean_import_noise(text_value)", host)
        self.assertIn('"removed_count": len(removed)', host)

    def test_chapter_find_replace_and_bounded_undo_redo_are_connected(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("choice === 'find' || choice === 'replace'", adapter)
        self.assertIn("Replace every case-insensitive match with:", adapter)
        self.assertIn("chapterUndoStacks", adapter)
        self.assertIn("chapterRedoStacks", adapter)
        self.assertIn("changeChapterHistory(key === 'z' && !event.shiftKey ? 'undo' : 'redo')", adapter)
        self.assertIn("chapterHistoryLimit = 10", adapter)
        self.assertIn("Undo/redo is limited to chapters of 1,000,000 characters", adapter)
        self.assertIn("Type one: add, rename, delete, up, down, merge, review, skip, find, replace, undo, redo", adapter)

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
        self.assertIn("call('sound.cues.save'", adapter)
        self.assertIn("call('sound.cues.get')", adapter)
        self.assertIn("call('sound.cues.clear')", adapter)
        self.assertIn("refreshSoundCues().catch", adapter)
        self.assertIn("Playing assigned cue clips in book order.", adapter)
        self.assertIn("call('sound.preview_book')", adapter)
        self.assertIn("Generating the full-book mix preview from saved chapter narration", adapter)
        self.assertIn("def _render_sound_design_preview(", self.host)
        self.assertIn('state["_include_sound_design_preview"] = True', self.host)

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
        self.assertIn('chapters = [c for c in project.chapters if not getattr(c, "skip_for_generation", False) and (c.text or "").strip()]', worker)
        self.assertIn("skipped = len(project.chapters) - len(chapters)", worker)
        self.assertIn('empty_skipped = sum(1 for c in project.chapters if not (c.text or "").strip())', worker)
        self.assertIn('excluded_skipped = sum(1 for c in project.chapters if getattr(c, "skip_for_generation", False) and (c.text or "").strip())', worker)
        self.assertIn("if not chapters:", worker)
        self.assertIn("No chapters are eligible for generation. Restore chapter text or re-include a skipped chapter.", worker)
        self.assertIn('"empty_chapters_skipped": empty_skipped', worker)
        self.assertIn('"excluded_chapters_skipped": excluded_skipped', worker)
        self.assertIn('"chapters_skipped_for_generation": skipped', worker)
        self.assertIn("Render {len(chapters)} eligible chapter(s)", worker)
        self.assertIn("Starting with {empty_skipped} empty and {excluded_skipped} excluded chapter(s) skipped", worker)

    def test_preview_duration_setting_accepts_every_supported_target(self):
        self.assertIn('if key == "preview_seconds" and int(value) not in {10, 20, 30, 45, 60}:', self.host)
        self.assertIn('Preview duration must be 10, 20, 30, 45, or 60 seconds.', self.host)

    def test_chapter_bgm_and_scene_cues_reach_final_assembly(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        assembler = (ROOT / "app" / "audio" / "assembler.py").read_text(encoding="utf-8")
        manager = (ROOT / "app" / "tts" / "manager.py").read_text(encoding="utf-8")
        self.assertIn('"sound.chapter_bgm.get": self._sound_chapter_bgm_get', self.host)
        self.assertIn('"sound.chapter_bgm.save": self._sound_chapter_bgm_save', self.host)
        self.assertIn('state["chapter_bgm_overrides"] = overrides', self.host)
        self.assertIn('chapter_bgm_overrides=state.get("chapter_bgm_overrides")', self.host)
        self.assertIn("call('sound.chapter_bgm.save'", adapter)
        self.assertIn("function renderChapterBgm()", adapter)
        self.assertIn("def _mix_chapter_bgm(", assembler)
        self.assertIn("chapter_bgm_overrides: dict[str, dict] | None = None", assembler)
        self.assertIn("mixed-chapter-background-audio", assembler)
        self.assertIn("scene_transition_cue_path: Path | str | None = None", assembler)
        self.assertIn("auto-real-scene-cue-", assembler)
        self.assertIn("scene_transition_cue_path=self.scene_transition_cue_path", manager)

    def test_performance_screen_never_displays_unmeasured_hardware_as_fact(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("async function refreshPerformance()", adapter)
        self.assertIn("await refreshPerformance().catch(()=>{});", adapter)
        self.assertIn("CPU telemetry unavailable", adapter)
        self.assertIn("GPU / VRAM telemetry unavailable", adapter)
        self.assertIn("section?.querySelectorAll('.ready-list .ready b').forEach(node => { node.textContent = 'Not measured'; });", adapter)
        self.assertIn("const result=await refreshPerformance();", adapter)
        self.assertIn('"performance.info": False', (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8"))

    def test_scene_cue_feedback_matches_current_assembly_support(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("Scene transition cue saved to this book and will be included during audiobook assembly.", adapter)
        self.assertIn("const assignedSlot = pendingCueSlot;", adapter)
        self.assertNotIn("current audiobook assembly does not yet render a separate scene cue", adapter)
        self.assertIn("scene_transition_cue_path=self.scene_transition_cue_path", (ROOT / "app" / "tts" / "manager.py").read_text(encoding="utf-8"))

    def test_sound_cue_assignments_are_allowlisted_and_persisted(self):
        for command, method in (
            ("sound.cues.get", "_sound_cues_get"),
            ("sound.cues.save", "_sound_cues_save"),
            ("sound.cues.clear", "_sound_cues_clear"),
        ):
            self.assertIn(f'"{command}": self.{method}', self.host)
        start = self.host.index("def _sound_cues_save")
        end = self.host.index("def _sound_cues_clear", start)
        worker = self.host[start:end]
        self.assertIn('{"opening", "chapter", "scene", "closing"}', worker)
        self.assertIn('state["sound_cues"] = cues', worker)
        self.assertIn('state["opening_cue_path"] = selected_path', worker)
        self.assertIn('state["page_turn_cue_path"] = selected_path', worker)
        self.assertIn('state["ending_cue_path"] = selected_path', worker)
        self.assertIn('"generation_supported": True', worker)
        self.assertIn('state["sound_cues"] = {"opening": None, "chapter": None, "scene": None, "closing": None}', self.host)


    def test_settings_get_returns_saved_effects_preference(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('"effects": self.settings.value("ui/effects", "high")', host)
        self.assertIn("if ($('effectsModeAdvanced') && settings.effects) $('effectsModeAdvanced').value = settings.effects;", adapter)

    def test_pronunciation_term_preview_uses_real_voice_preview_job(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("if ($('previewPronTerm')) $('previewPronTerm').onclick=act(async()=>", adapter)
        self.assertIn("call('voice.preview', {profile_name:profile, text:term, duration_seconds:10})", adapter)
        self.assertIn("monitorJob(data.job_id, async job=>", adapter)
        self.assertIn("await previewAudio.play()", adapter)

    def test_output_folder_resume_and_history_controls_use_backend(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("buttonLabel === 'open output folder'", adapter)
        self.assertIn("call('system.open_output')", adapter)
        self.assertIn("buttonLabel === 'resume production'", adapter)
        self.assertIn("call('job.resume', {job_id:paused.job_id})", adapter)
        self.assertIn("e.target.closest('#historyFilters button')", adapter)
        self.assertIn("e.target.closest('[data-history-job]')", adapter)
        self.assertIn("call('history.list')", adapter)

    def test_stage829_gap_controls_are_backend_bound_or_explicitly_honest(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "waitForTerminalJob", "previewSavedProfile", "testSelectedVoices",
            "testAllVoices", "call('models.install'", "refreshVoices()",
            "Credential management is not connected to a secure provider-specific credential store",
            "Premium cloud candidate generation is not connected to a provider endpoint",
            "call('chapter.review', {number, review_status:nextStatus})",
            "row.hidden = chapter?.review_status === 'reviewed'",
            "playerAudio.playbackRate",
        ):
            self.assertIn(token, adapter)

    def test_stage829_remaining_demo_actions_are_guarded_and_profile_delete_is_real(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        for token in (
            "previewSavedProfile(profile, 'Hello, my name is ' + c.name",
            "call('character.update'",
            "call('character.delete'",
            "Per-line AI speaker suggestions are still prototype-only",
            "Custom project-library and audio-assets root selection is not implemented",
            "call('diagnostics.export_logs')",
            "termList.innerHTML = terms.map",
            "call('voice.delete'",
        ):
            self.assertIn(token, adapter)
        self.assertIn('"voice.delete": self._voice_delete', host)
        self.assertIn('"voice.delete": True', host)
        self.assertIn("def _voice_delete(", host)
        self.assertIn("Built-in voices cannot be deleted", host)

    def test_stage829_pronunciation_matrix_and_model_registry_never_fake_success(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "button.id === 'addPronunciationAdvanced'",
            "button.id === 'modalSave'",
            "call('pronunciation.save'",
            "button.matches('[data-test-pron]')",
            "button.matches('[data-qwen-install]')",
            "Per-model ' + action + ' is not connected to a backend operation",
            "Dialogue-line speaker assignment is not persisted by the current backend",
        ):
            self.assertIn(token, adapter)

    def test_character_library_series_scope_matches_default_filter(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("c?.scope || 'Series · Slime'", adapter)
        self.assertIn("const series = /^Series\\s*[·:-]\\s*Slime$/i.test(scope) ? 'Slime series' : scope;", adapter)
        self.assertIn("librarySeriesName(c) === series", adapter)
        self.assertIn("return /^Series\\s*[·:-]\\s*Slime$/i.test(raw) ? 'Slime series' : raw;", adapter)

    def test_reusable_character_library_is_persisted_and_connected(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for command, handler in {
            "character_library.list": "_character_library_list",
            "character_library.save": "_character_library_save",
            "character_library.delete": "_character_library_delete",
            "character_library.import": "_character_library_import",
        }.items():
            self.assertIn(f'"{command}": self.{handler}', host)
            self.assertIn(f'"{command}": True', host)
        self.assertIn('settings_root() / "character_library.json"', host)
        self.assertIn("temporary.replace(path)", host)
        self.assertIn("call('character_library.list')", adapter)
        self.assertIn("call('character_library.save'", adapter)
        self.assertIn("call('character_library.delete'", adapter)
        self.assertIn("call('character_library.import'", adapter)
        self.assertIn("importCharacterLibraryFile()", adapter)
        self.assertIn("openLibraryEditor(null)", adapter)
        self.assertIn("saveLibraryEditor()", adapter)
        self.assertIn("Character Library imports are limited to 10 MB.", adapter)


    def test_chapter_review_status_is_persisted_and_filter_is_backend_driven(self):
        detector = (ROOT / "app" / "chapters" / "detector.py").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('review_status: str = "needs_review"', detector)
        self.assertIn('"chapter.review": self._chapter_review', host)
        self.assertIn('"chapter.review": True', host)
        self.assertIn('chapter.review_status = status', host)
        self.assertIn('"review_status": getattr(c, "review_status", "needs_review")', host)
        self.assertIn("call('chapter.review', {number, review_status:nextStatus})", adapter)
        self.assertIn("row.hidden = chapter?.review_status === 'reviewed'", adapter)
        self.assertNotIn("Review status is not yet supplied by the chapter backend", adapter)

    def test_chapter_generation_exclusion_is_persisted_and_applied(self):
        detector = (ROOT / "app" / "chapters" / "detector.py").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("skip_for_generation: bool = False", detector)
        self.assertIn('"chapter.skip": self._chapter_skip', host)
        self.assertIn('"chapter.skip": True', host)
        self.assertIn('"skip_for_generation": getattr(c, "skip_for_generation", False)', host)
        self.assertIn("chapter.skip_for_generation = value", host)
        self.assertIn('not getattr(c, "skip_for_generation", False)', host)
        self.assertIn('"excluded_chapters_skipped": excluded_skipped', host)
        self.assertIn("call('chapter.skip', {number, skip_for_generation:nextSkip})", adapter)
        self.assertIn("Chapter included in audiobook generation again.", adapter)

    def test_legacy_chapter_json_remains_compatible_with_review_and_skip_defaults(self):
        detector = (ROOT / "app" / "chapters" / "detector.py").read_text(encoding="utf-8")
        project = (ROOT / "app" / "core" / "project.py").read_text(encoding="utf-8")
        self.assertIn('review_status: str = "needs_review"', detector)
        self.assertIn("skip_for_generation: bool = False", detector)
        self.assertIn("chapters = [Chapter(**item) for item in chapter_data]", project)


if __name__ == "__main__":
    unittest.main()
