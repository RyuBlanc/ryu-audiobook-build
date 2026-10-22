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
        self.assertIn("def _sha256_file(path: Path", host)
        self.assertIn('for chunk in iter(lambda: handle.read(chunk_size), b"")', host)
        self.assertIn("def _cleanup_staged_import_file(path: Path | None)", host)
        self.assertIn("source_digest = _sha256_file(path)", host)
        self.assertIn("existing_digest = _sha256_file(existing_source)", host)
        self.assertIn("for existing_project in list_projects():", host)
        self.assertIn("Open that project from Audiobook Library instead of importing a duplicate.", host)
        import_start = host[host.index("def _import_start("):host.index("def _format_import_error(")]
        self.assertIn("_cleanup_staged_import_file(path)", import_start)
        self.assertLess(host.index("source_digest = _sha256_file(path)"),
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
        self.assertIn("shutil.copy2(source_path, staged_source)", (ROOT / "app" / "core" / "project.py").read_text(encoding="utf-8"))
        self.assertIn("staging_folder.rename(final_folder)", (ROOT / "app" / "core" / "project.py").read_text(encoding="utf-8"))

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
        self.assertNotIn("await refreshPerformance().catch(()=>{});", adapter)
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
            "Automatic per-line AI speaker suggestions remain prototype-only",
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
            "call('chapter.dialogue.assign'",
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

    def test_import_has_no_re_detection_command_that_can_replace_manual_edits(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertNotIn('"chapter.redetect":', host)
        self.assertNotIn("def _chapter_redetect(", host)
        worker = host[host.index("def _import_worker("):host.index("def _chapter_clean(", host.index("def _import_worker("))]
        self.assertIn("chapters = detect_chapters(text)", worker)
        self.assertIn("project = create_project(title, path, chapters)", worker)
        self.assertNotIn("existing_project.chapters", worker)

    def test_explicit_dialogue_assignment_is_registered_persisted_and_source_validated(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        helper = (ROOT / "app" / "chapters" / "assignment_utils.py").read_text(encoding="utf-8")
        self.assertIn('"chapter.dialogue.assign": self._chapter_dialogue_assign', host)
        self.assertIn('"chapter.dialogue.assign": True', host)
        self.assertIn("def _chapter_dialogue_assign(", host)
        self.assertIn("assign_dialogue_to_chapters(", host)
        self.assertIn("call('chapter.dialogue.assign'", adapter)
        self.assertIn("window.ryuPremiumPendingDialogueText", adapter)
        self.assertIn("savedCharacters.filter(c => c && c.name)", adapter)
        self.assertIn("button.matches('[data-assign-character]')", adapter)
        self.assertNotIn("Dialogue-line speaker assignment is not persisted by the current backend", adapter)
        self.assertIn("def assign_dialogue_to_chapters(", helper)
        self.assertIn("no assignment was saved", helper)
        self.assertIn('normalized["source"] = "manual"', helper)
        self.assertIn('normalized["confidence"] = 1.0', helper)


    def test_adapter_calls_match_dispatcher_and_capability_map(self):
        """Every literal adapter call must be routed or deliberately disabled.

        This guards the frontend/backend boundary. It does not claim that all
        HTML controls have been manually exercised in the packaged app.
        """
        handler_match = re.search(
            r"handlers\s*=\s*\{([\s\S]*?)\n\s*\}\n\s*handler\s*=",
            self.host,
        )
        self.assertIsNotNone(handler_match, "Could not find the allow-listed dispatcher table.")
        handler_commands = set(re.findall(
            r"""["']([^"']+)["']\s*:\s*self\._[A-Za-z0-9_]+""",
            handler_match.group(1),
        ))

        capability_match = re.search(
            r"def _capabilities[\s\S]*?return\s*\{([\s\S]*?)\n\s*\}",
            self.host,
        )
        self.assertIsNotNone(capability_match, "Could not find the capability map.")
        capabilities = dict(re.findall(
            r"""["']([^"']+)["']\s*:\s*(True|False)""",
            capability_match.group(1),
        ))

        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(
            encoding="utf-8"
        )
        adapter_commands = set(re.findall(
            r"""\bcall\(\s*['"]([^'"]+)['"]""",
            adapter,
        ))

        self.assertFalse(
            adapter_commands - handler_commands,
            "Adapter calls without registered dispatcher handlers: "
            + ", ".join(sorted(adapter_commands - handler_commands)),
        )
        self.assertFalse(
            handler_commands - set(capabilities),
            "Registered handlers missing capability entries: "
            + ", ".join(sorted(handler_commands - set(capabilities))),
        )
        advertised_without_handler = {
            command for command, enabled in capabilities.items()
            if enabled == "True" and command not in handler_commands
        }
        self.assertFalse(
            advertised_without_handler,
            "Capabilities advertised as connected without handlers: "
            + ", ".join(sorted(advertised_without_handler)),
        )
        self.assertEqual(
            capabilities.get("performance.info"),
            "False",
            "Unmeasured hardware telemetry must remain truthfully unavailable.",
        )


    def test_dashboard_recent_project_cards_open_real_local_project(self):
        """Dashboard cards must open their own backend project, not a prototype card."""
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "if ($('dashboard')) $('dashboard').addEventListener('click', async e => {",
            adapter,
        )
        self.assertIn("e.target.closest('.recent-grid [data-project-folder]')", adapter)
        self.assertIn("call('project.open', {folder})", adapter)
        self.assertIn("await refreshChapters()", adapter)
        self.assertIn("await refreshCharacters()", adapter)
        self.assertIn("window.go('chapters')", adapter)


    def test_workflow_tracker_highlights_only_the_active_screen(self):
        """The Import-to-Generate tracker must follow navigation, not static demo states."""
        go_start = self.html.index("function go(id){")
        go_end = self.html.index("\n$$('[data-page]')", go_start)
        go = self.html[go_start:go_end]
        for page in ("import", "chapters", "voices", "characters", "pronunciation", "sound", "generate"):
            self.assertIn(f"{page}:'{page}'", go)
        self.assertIn("b.classList.toggle('is-current',Boolean(currentWorkflowStage)&&b.dataset.go===currentWorkflowStage)", go)
        self.assertIn("b.classList.remove('is-done','has-warning')", go)
        self.assertIn("link.classList.remove('is-done','is-current','has-warning')", go)
        self.assertNotRegex(self.html, r'<button class="flow-stage (?:is-current|is-done|has-warning)')
        self.assertNotRegex(self.html, r'<span class="flow-link (?:is-current|is-done|has-warning)')


    def test_model_verification_uses_real_local_file_checks(self):
        """The Models screen's Verify action must inspect installed files, not report fake success."""
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('"models.verify": True', host)
        self.assertIn('"models.verify": self._models_verify', host)
        self.assertIn("def _models_verify(self, payload: dict[str, Any])", host)
        self.assertIn("from app.tts.qwen_character_runtime import MODEL_IDS, MODEL_DIRS, model_installed", host)
        self.assertIn("if (action === 'verify')", adapter)
        self.assertIn("call('models.verify', {model_id:id})", adapter)
        self.assertIn("result.models.map(model => model.model_id).join(', ')", adapter)
        self.assertIn("One or more required model files are missing or incomplete.", host)
        self.assertNotRegex(
            host[host.index("def _models_verify"):host.index("def _performance_info")],
            r"(?i)\b(?:requests\.(?:get|post)|urlopen|snapshot_download|download_model|hf_hub_download)\s*\("
        )

    def test_legacy_controls_without_ids_have_semantic_successors_and_event_paths(self):
        """Map no-ID legacy control groups to stable selectors and real event/backend paths."""
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        soup = BeautifulSoup(self.html, "html.parser")
        # Navigation and workflow strip are delegated by stable data attributes, not per-button IDs.
        for selector in ('button.nav-btn[data-page]', '[data-go]', '#voices .toolbar', '#voices .seg'):
            self.assertTrue(soup.select(selector), selector)
        self.assertIn("function go(id){", self.html)
        self.assertIn("b.dataset.go===currentWorkflowStage", self.html)
        # Provider cards, sound filters/tracks, and background jobs use semantic data attributes.
        for selector in ('[data-provider]', '#soundSourceFilter', '[data-source]', '#soundTrackGrid', '#previewSelectedTrack', '#soundPreviewBook', '#backgroundJobsButton'):
            self.assertTrue(soup.select(selector), selector)
        for marker in ('data-select-sound=', 'data-job-action=', 'data-job-id='):
            self.assertIn(marker, self.html + adapter)
        self.assertIn("button.closest('.provider')", adapter)
        self.assertIn("document.querySelector('#soundSourceFilter [data-source].active')", adapter)
        self.assertIn("box.innerHTML = jobs.map(j =>", adapter)
        self.assertIn("dataset.jobAction", adapter)
        # Player transport controls intentionally use visible labels; bind them to the real Audio element.
        self.assertIn("playerAudio.playbackRate = Number(audioLabel.replace('×',''))", adapter)
        self.assertIn("playerAudio.currentTime = Math.max(0, playerAudio.currentTime - 15)", adapter)
        self.assertIn("playerAudio.currentTime = Math.min(playerAudio.duration || Infinity, playerAudio.currentTime + 15)", adapter)
        self.assertIn("const lengthGroup = [...document.querySelectorAll('#voices .toolbar')]", adapter)
        self.assertIn("const duration = lengthGroup?.querySelector('.seg button.active')?.textContent.match(/\\d+/)?.[0] || '30'", adapter)
        # Chapter context actions and track selection have source-backed host calls.
        self.assertIn("Type one: add, rename, delete, up, down, merge, review, skip, find, replace, undo, redo", adapter)
        for command in ("chapter.add", "chapter.delete", "chapter.reorder", "chapter.merge", "sound.catalog", "sound.assign", "sound.save_manifest"):
            self.assertIn("call('" + command + "'", adapter)
        self.assertIn("call('player.get_active')", adapter)


    def test_legacy_control_ids_are_preserved_or_have_named_successors(self):
        """Guard the old UI ID inventory against silent markup regressions."""
        soup = BeautifulSoup(self.html, "html.parser")
        current_ids = {node.get("id") for node in soup.select("[id]") if node.get("id")}
        legacy_ids = {
            "app", "sidebar", "nav", "menuToggle", "pageTitle", "globalSearch",
            "themeToggle", "notifyBtn", "workspace", "dashboard", "pauseDash",
            "library", "librarySearch", "libraryFilters", "libraryGrid", "import",
            "dropzone", "fileInput", "browseBtn", "importStatus", "importBar",
            "chapters", "cleanText", "saveChapter", "chapterSearch", "chapterList",
            "chapterTitle", "chapterEditor", "saveState", "wordCount", "voices",
            "saveProfile", "voiceGrid", "voiceWave", "voicePlay", "voiceStop",
            "selectedVoice", "characters", "analyzeCharacters", "characterList",
            "characterName", "characterVoice", "characterVoiceSelect", "assignVoice",
            "pronunciation", "addPronunciation", "pronSearch", "pronTable", "sound",
            "saveSoundPreset", "trackGrid", "selectedTrack", "musicVolumeValue",
            "musicVolume", "generate", "cancelJob", "genRing", "genPercent",
            "genStage", "genChapter", "elapsed", "remaining", "previewGenerate",
            "startGenerate", "pauseGenerate", "player", "playerTimeline", "currentTime",
            "mainPlay", "history", "historyFilters", "models", "performance",
            "runBenchmark", "benchmarkResult", "settings", "saveSettings", "themeSelect",
            "miniPlayer", "miniPlay", "miniProgress", "hideMini", "toasts", "modalBack",
            "modalTitle", "modalWord", "modalPron", "modalCancel", "modalSave",
        }
        successors = {
            "voiceGrid": {"voiceWorkspace", "profileLibrary"},
            "voiceWave": {"wave", "assignedWave", "soundWave"},
            "voicePlay": {"playPreview"},
            "voiceStop": {"stopPreview"},
            "selectedVoice": {"profileVoice", "previewVoice", "previewProvider"},
            "characterList": {"assignedCharacterList", "quickCharacterList", "manualStory"},
            "characterName": {"editCharacterName"},
            "characterVoice": {"editCharacterVoice", "assignCharacter"},
            "characterVoiceSelect": {"editCharacterVoice"},
            "assignVoice": {"assignCharacter", "confirmAiCharacter"},
            "addPronunciation": {"addPronunciationAdvanced", "saveNewPron"},
            "pronSearch": {"pronTermSearch", "pronSearchAdvanced"},
            "pronTable": {"pronDictionaryBody"},
            "saveSoundPreset": {"saveSoundPresetAdvanced", "applySoundToProduction"},
            "trackGrid": {"soundTrackGrid", "cueGrid"},
            "selectedTrack": {"selectedSoundTitle", "selectedSoundMeta"},
            "musicVolumeValue": {"advancedMusicVolumeValue"},
            "musicVolume": {"advancedMusicVolume"},
            "saveSettings": {"saveSettingsAdvanced"},
            "themeSelect": {"themeSelectAdvanced"},
        }
        self.assertEqual(89, len(legacy_ids))
        missing_ids = legacy_ids - current_ids
        self.assertEqual(set(successors), missing_ids)
        for old_id, candidates in successors.items():
            self.assertTrue(
                candidates & current_ids,
                f"Legacy control {old_id} has no markup successor from {sorted(candidates)}",
            )

    def test_initial_backend_hydration_does_not_block_ui_handler_registration(self):
        """Optional backend panels hydrate after handlers are registered and yield between calls."""
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(
            encoding="utf-8"
        )
        wire_start = adapter.index("async function wire()")
        hydration_start = adapter.index("const hydrateInitialState = async () =>", wire_start)
        first_handler = adapter.index("document.addEventListener('click', e => {", wire_start)
        timer_start = adapter.index("if (!window.__ryuBackendJobTimer)", hydration_start)
        wire_end = adapter.index("message('Premium V2 local backend connected.')", timer_start)
        self.assertLess(first_handler, hydration_start)
        self.assertLess(hydration_start, timer_start)
        hydration = adapter[hydration_start:timer_start]
        self.assertIn("[refreshProjects, refreshVoices, refreshChapters, loadSettings]", hydration)
        self.assertIn("[refreshCharacters, refreshCharacterLibrary, refreshTerms]", hydration)
        self.assertIn("[refreshSounds, refreshSoundCues, refreshChapterBgm]", hydration)
        self.assertIn("[refreshJobs, refreshHistory, refreshModels]", hydration)
        self.assertIn("await new Promise(resolve => setTimeout(resolve, 0))", hydration)
        self.assertIn("void hydrateInitialState()", hydration)
        self.assertNotIn("refreshPerformance", hydration)

    def test_job_polling_updates_existing_rows_without_rebuilding_hidden_panel(self):
        """Job polling should not repeatedly replace DOM rows and trigger visible flicker."""
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(
            encoding="utf-8"
        )
        start = adapter.index("async function refreshJobs()")
        end = adapter.index("async function monitorJob(", start)
        refresh_jobs = adapter[start:end]
        self.assertIn("const panelVisible = Boolean($('backgroundJobsModal')?.classList.contains('show'))", refresh_jobs)
        self.assertIn("if (box && panelVisible)", refresh_jobs)
        self.assertIn("box.dataset.backendJobsSignature !== signature", refresh_jobs)
        self.assertIn("row.querySelector('[data-job-progress]')", refresh_jobs)
        self.assertIn("progress.style.width = pct + '%'", refresh_jobs)


    def test_unavailable_prototype_actions_are_disabled_with_truthful_reasons(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function applyUnavailableControlStates()")
        end = adapter.index("async function wire()", start)
        guard = adapter[start:end]
        for selector in (
            "#acceptHighConfidence", "#skipAiSuggestion", "#aiUseLibrary",
            "#aiCreateNew", "#createCharacterQuick",
            "[data-ai-line]:not([data-dialogue-id])",
            "[data-model-update]", "[data-model-repair]", "[data-model-uninstall]",
            "#settings button", "$('runBenchmark')",
        ):
            self.assertIn(selector, guard)
        self.assertIn("element.disabled = true", guard)
        self.assertIn("element.setAttribute('aria-disabled', 'true')", guard)
        self.assertIn("element.title = reason", guard)
        self.assertIn("Bulk AI predictions are not verified against source passages", guard)
        self.assertIn("Per-model update, repair, and uninstall are not implemented", guard)
        self.assertIn("Changing the application storage root is not implemented", guard)
        self.assertIn("performance is intentionally marked Not tested", guard)
        self.assertIn("applyUnavailableControlStates();", adapter[adapter.index("async function wire()"):])


if __name__ == "__main__":
    unittest.main()
