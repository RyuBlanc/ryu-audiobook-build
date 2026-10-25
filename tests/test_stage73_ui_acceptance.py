from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage73UIAcceptanceTests(unittest.TestCase):
    """Static guardrails for the 14-destination Dragon Studio desktop shell.

    These checks complement (not replace) Windows visual and interaction tests.
    """

    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / "app" / "ui" / "workflow.py").read_text(encoding="utf-8")
        cls.dashboard = (ROOT / "app" / "ui" / "dashboard_page.py").read_text(encoding="utf-8")
        # The original Dragon Studio prototype remains the full-app navigation
        # reference for the 14 destinations. The newer fixed all-steps HTML is
        # the approved, more detailed Voice Studio reference; it is not a
        # replacement for the other thirteen application screens.
        cls.prototype = (
            ROOT / "docs" / "prototypes" / "Ryus_Audiobook_Dragon_Studio_Premium_Final.html"
        ).read_text(encoding="utf-8")
        cls.voice_reference = (
            ROOT / "docs" / "prototypes" / "Ryus_Audiobook_Voice_Studio_Fixed_All_Steps.html"
        ).read_text(encoding="utf-8")

    def test_all_fourteen_destinations_have_sidebar_routes(self):
        expected = {
            "Dashboard", "Library", "Import", "Chapters", "Voice & Narration",
            "Voice Cast", "Pronunciation", "Sound Design", "Generate",
            "Audiobooks", "History", "Models", "Hardware", "Settings",
        }
        sidebar_keys = set(re.findall(r'\("([^"]+)",\s*"[^"]+",\s*"[^"]*"\)', self.workflow))
        self.assertTrue(expected.issubset(sidebar_keys), f"Missing sidebar destinations: {sorted(expected - sidebar_keys)}")

    def test_every_sidebar_destination_has_dispatch_behavior(self):
        start = self.workflow.index("    def _sidebar_changed(")
        end = self.workflow.index("    def _navigate_workflow_step(", start)
        dispatch = self.workflow[start:end]
        expected_handlers = {
            "Dashboard": "self._show_page(self.dashboard)",
            "Library": "self._show_page(self.library)",
            "Import": "self._show_page(self.import_page)",
            "Chapters": "self._show_page(self.editor)",
            "Voice & Narration": "self._show_page(self.voice)",
            "Voice Cast": "self._show_page(self.voice_cast)",
            "Pronunciation": 'self._open_generation_feature("pronunciation")',
            "Sound Design": 'self._open_generation_feature("sound")',
            "Generate": "self._show_page(self.generation)",
            "Audiobooks": "self._show_page(self.audiobooks_page)",
            "History": "self._show_page(self.history_page)",
            "Models": "self._show_page(self.models_page)",
            "Hardware": "self._show_page(self.hardware_page)",
            "Settings": "self._show_page(self.settings_page)",
        }
        missing = [name for name, behavior in expected_handlers.items() if behavior not in dispatch]
        self.assertEqual(missing, [], f"Destinations missing their expected route: {missing}")

    def test_generation_navigation_has_recovery_and_defers_refresh(self):
        start = self.workflow.index('        elif name == "Generate":', self.workflow.index("    def _sidebar_changed("))
        end = self.workflow.index('        elif name == "Models":', start)
        handler = self.workflow[start:end]
        self.assertIn("self.ensure_generation_page()", handler)
        self.assertIn("self._show_page(self.generation)", handler)
        self.assertIn("QTimer.singleShot(75, self._refresh_generation_context)", handler)
        self.assertIn("Generate page could not be opened", handler)
        self.assertIn("Select a book in Library or import a new book to start generating.", handler)

    def test_responsive_shell_has_one_merged_resize_handler(self):
        # A duplicate method silently overrides the earlier implementation in Python.
        self.assertEqual(len(re.findall(r"^    def resizeEvent\(", self.workflow, re.MULTILINE)), 1)
        start = self.workflow.index("    def resizeEvent(")
        end = self.workflow.find("\n    def ", start + 5)
        handler = self.workflow[start:end if end >= 0 else None]
        for required in (
            "self.project_label.setVisible(not compact_header)",
            "self.global_search.setMaximumWidth",
            "self.mini_title.setVisible(not compact_player)",
            "self.mini_position.setVisible(not compact_player)",
            "self.mini_duration.setVisible(not compact_player)",
            "self.loading_overlay.setGeometry",
        ):
            self.assertIn(required, handler)

    def test_dashboard_metrics_and_recent_cards_are_project_backed(self):
        for required in (
            "list_projects()",
            "project_status(project)",
            "states_by_folder[str(latest.folder)]",
            "self.metric_total.metric_value.setText(str(len(self.projects)))",
            "self.on_open_project(self.projects[0])",
            "self.on_open_project(self.visible_projects[row])",
            "self.on_import()",
            "self.on_open_library()",
        ):
            self.assertIn(required, self.dashboard)
        self.assertNotIn("random.", self.dashboard.lower())

    def test_canonical_full_app_prototype_contains_all_fourteen_screen_anchors(self):
        anchors = {
            "dashboard", "library", "import", "chapters", "characters",
            "pronunciation", "sound", "generate", "player", "history",
            "models", "performance", "settings",
        }
        # Voice Studio has a separately approved updated reference, so the
        # overall prototype's voice anchor is checked independently below.
        for anchor in anchors:
            self.assertRegex(self.prototype, rf"""id=["']{re.escape(anchor)}["']""")
        self.assertRegex(self.prototype, r"""id=["']voice[^"']*["']""")

    def test_updated_voice_studio_reference_keeps_four_step_workflow(self):
        for phrase in ("Voice Library", "Configure", "Voice Profile", "Preview & Assign"):
            self.assertIn(phrase, self.voice_reference)

    def test_visual_reference_does_not_replace_runtime_behavior_contract(self):
        spec = (ROOT / "docs" / "UI_UX_IMPLEMENTATION_SPEC.md").read_text(encoding="utf-8")
        self.assertIn("must not claim that visual controls are connected", spec)
        self.assertIn("must preserve", spec.lower())


    def test_library_has_distinct_empty_collection_and_no_filter_match_recovery(self):
        library = (ROOT / "app" / "ui" / "library.py").read_text(encoding="utf-8")
        self.assertIn("Your local library is empty.", library)
        self.assertIn("Import a book to create your first audiobook project.", library)
        self.assertIn("No books match the current search/filter.", library)
        self.assertIn("clear the search or choose All", library)

    def test_library_search_filters_and_destructive_actions_require_confirmation(self):
        library = (ROOT / "app" / "ui" / "library.py").read_text(encoding="utf-8")
        self.assertIn("self.search.textChanged.connect(self._schedule_refresh)", library)
        self.assertIn("self._refresh_timer.setInterval(180)", library)
        self.assertIn("_project_data_cache", library)
        self.assertIn("_file_signature", library)
        self.assertIn("project_matches(", library)
        self.assertIn("self._state_cache =", library)
        self.assertIn("self._status_cache =", library)
        self.assertIn("QListWidget.SelectionMode.ExtendedSelection", library)
        self.assertIn("QMessageBox.StandardButton.No,", library)
        self.assertIn("if answer != QMessageBox.StandardButton.Yes:", library)


    def test_import_studio_preserves_review_before_local_project_creation(self):
        import_page = (ROOT / "app" / "ui" / "import_page.py").read_text(encoding="utf-8")
        for required in (
            '"EPUB", "PDF", "TXT", "DOCX"',
            'self.drop_zone.files_dropped.connect(self._drop_files)',
            'self.worker.ready.connect(self._analysis_ready)',
            'self.worker.failed.connect(self._analysis_failed)',
            'self.preview.setPlainText',
            'self.create_button.setEnabled(True)',
            'self.on_import(self.source_path, self.book, self.chapters)',
            'Your source file remains in your chosen location',
            'scroll.setObjectName("importScroll")',
        ):
            self.assertIn(required, import_page)

    def test_import_studio_rejects_unsupported_or_missing_files_and_multiple_drops(self):
        import_page = (ROOT / "app" / "ui" / "import_page.py").read_text(encoding="utf-8")
        self.assertIn('if len(paths) != 1:', import_page)
        self.assertIn('Drop one book at a time', import_page)
        self.assertIn('if not path.is_file():', import_page)
        self.assertIn('if path.suffix.lower() not in {".pdf", ".epub", ".txt", ".docx"}:', import_page)
        self.assertIn('Unsupported file format. Choose a PDF, EPUB, TXT, or DOCX book.', import_page)
        self.assertIn('self.create_button.setEnabled(False)', import_page)

    def test_import_preview_blocks_empty_text_and_suspicious_chapter_loss(self):
        import_page = (ROOT / "app" / "ui" / "import_page.py").read_text(encoding="utf-8")
        self.assertIn('if not str(book.text or "").strip():', import_page)
        self.assertIn('if not chapters:', import_page)
        self.assertIn('validate_chapter_text_coverage(book.text, chapters, minimum=0.90)', import_page)
        self.assertIn('def validate_chapter_text_coverage(', (ROOT / "app" / "documents" / "parser.py").read_text(encoding="utf-8"))
        self.assertIn('validate_chapter_text_coverage(book.text, chapters, minimum=0.90)', import_page)
        self.assertIn('Import was stopped to protect your book from losing content.', (ROOT / "app" / "documents" / "parser.py").read_text(encoding="utf-8"))
        self.assertIn('self.status.setText(f"Import analysis failed: {message}")', import_page)



    def test_audiobooks_shelf_shows_real_local_output_author_and_cover(self):
        page = (ROOT / "app" / "ui" / "audiobooks_page.py").read_text(encoding="utf-8")
        for required in (
            'candidate.is_file() and candidate.suffix.lower() in _AUDIO_EXTENSIONS and candidate.stat().st_size > 0',
            'path.stat().st_size > 0',
            'self.cover_art = QLabel("No cover art")',
            'state.get("author") or state.get("author_name")',
            'state.get("cover_path")',
            'QPixmap(str(cover_path))',
            'pixmap.scaled(',
            'self.author_detail.setText(f"Author: {author or \'Not set\'}")',
            'self.open_project_button.setEnabled(project is not None)',
        ):
            self.assertIn(required, page)

    def test_audiobooks_player_keeps_playback_and_recovery_controls(self):
        page = (ROOT / "app" / "ui" / "audiobooks_page.py").read_text(encoding="utf-8")
        for required in (
            'self.player.positionChanged.connect(self._position_changed)',
            'self.player.durationChanged.connect(self._duration_changed)',
            'self.player.errorOccurred.connect(self._playback_error)',
            'self.play_button.clicked.connect(self.play_selected)',
            'self.pause_button.clicked.connect(self.pause_resume)',
            'self.stop_button.clicked.connect(self.stop_playback)',
            'self.open_output_button.clicked.connect(self._open_output_folder)',
            'if path is None:',
            'self.status.setText("Playback stopped.")',
        ):
            self.assertIn(required, page)

    def test_pronunciation_and_sound_design_open_dedicated_book_specific_pages(self):
        start = self.workflow.index("    def _open_generation_feature(")
        end = self.workflow.index("    def _install_generation_feature_pages(", start)
        routing = self.workflow[start:end]
        self.assertIn('key = "Pronunciation" if feature == "pronunciation" else "Sound Design"', routing)
        self.assertIn('self.pronunciation_page if feature == "pronunciation" else self.sound_design_page', routing)
        self.assertIn("self._show_page(target)", routing)
        self.assertIn("Select a book in Library or import one to open", routing)

        start = self.workflow.index("    def _install_generation_feature_pages(")
        end = self.workflow.index("    def ensure_generation_page(", start)
        feature_pages = self.workflow[start:end]
        self.assertIn('setObjectName("pronunciationStudioPage")', feature_pages)
        self.assertIn('setObjectName("soundDesignStudioPage")', feature_pages)
        self.assertIn("Pronunciation Studio", feature_pages)
        self.assertIn("Sound Design Studio", feature_pages)

    def test_page_transition_is_non_blocking_and_respects_reduced_motion(self):
        start = self.workflow.index("    def _show_page(")
        end = self.workflow.index("    def _sidebar_item_clicked(", start)
        transition = self.workflow[start:end]
        self.assertIn("self.stack.setCurrentWidget(widget)", transition)
        self.assertNotIn("QGraphicsOpacityEffect", transition)
        self.assertNotIn("animation.start()", transition)
        self.assertIn("self._page_animation_widget.setGraphicsEffect(None)", transition)
        self.assertIn("self._update_page_chrome(widget)", transition)

    def test_generation_history_uses_real_local_state_and_safe_output_paths(self):
        page = (ROOT / "app" / "ui" / "history_page.py").read_text(encoding="utf-8")
        for required in (
            "def _output_for(project: Project, state: dict)",
            "path = project.folder / path",
            "path.is_file() and path.stat().st_size > 0",
            "def _status_for(project: Project, state: dict)",
            "list_projects()",
            "load_state(project.folder)",
            "self.table.setHorizontalHeaderLabels(",
            "self.table.itemSelectionChanged.connect(self._selection_changed)",
            "self.open_button.clicked.connect(self._open_project)",
            "self.production_button.clicked.connect(self._open_generation)",
            "self.output_button.clicked.connect(self._open_output_folder)",
            "History is reconstructed from local state files; no synthetic job entries are shown.",
        ):
            self.assertIn(required, page)

    def test_settings_preserve_local_first_accessible_preferences_and_output_quality(self):
        page = (ROOT / "app" / "ui" / "settings_page.py").read_text(encoding="utf-8")
        for required in (
            'self.theme.addItem("Dark · Obsidian", "dark")',
            'self.theme.addItem("Light · Cream", "light")',
            'self.accent.addItem("Dragon Crimson", "crimson")',
            'self.accent.addItem("Velvet Red", "velvet")',
            'self.reduce_motion = QCheckBox("Reduce page and waveform motion")',
            'for kbps in (128, 160, 192, 224, 256, 288, 320):',
            'self.save_button.clicked.connect(self.save_settings)',
            '("Open Audiobook Library", library_root())',
            '("Open Voice Profiles", voices_root())',
            '("Open Audio Library", audio_library_root())',
            '("Open Models Folder", models_root())',
            '("Open Logs Folder", app_root() / "Logs")',
            "Books, voice profiles, models, audio and logs remain on this PC.",
        ):
            self.assertIn(required, page)


    def test_dashboard_progress_is_based_on_saved_records_and_has_empty_state(self):
        for required in (
            'state.get("completed_chapters")',
            'latest_state.get("completed_chapters")',
            'Progress reflects chapters recorded in local project state; it is not an ETA.',
            'No completed-chapter record is available yet.',
            'Your books and output remain on this device.',
            'self.continue_button.setEnabled(bool(self.projects))',
            'self.status_detail.setTextFormat(Qt.TextFormat.PlainText)',
        ):
            self.assertIn(required, self.dashboard)
        self.assertNotIn("random.", self.dashboard.lower())

    def test_hardware_benchmark_runs_off_ui_thread_and_reports_missing_voice(self):
        page = (ROOT / "app" / "ui" / "hardware_page.py").read_text(encoding="utf-8")
        hardware_start = page.index("class HardwarePage")
        refresh_start = page.index("    def refresh(", hardware_start)
        run_start = page.index("    def run_benchmark(", refresh_start)
        hardware_init = page[page.index("    def __init__(", hardware_start):refresh_start]
        refresh = page[refresh_start:run_start]
        self.assertIn("self.profile = None", hardware_init)
        self.assertNotIn("detect_hardware()", hardware_init)
        for required in (
            "profile = detect_hardware()",
            "for backend in profile.backends:",
            "if backend.available:",
        ):
            self.assertIn(required, refresh)
        for required in (
            'self.benchmark_button.clicked.connect(self.run_benchmark)',
            'self.benchmark_thread = _BenchmarkThread(provider_backend, voices[0].stem)',
            'self.benchmark_thread.finished_result.connect(self._benchmark_finished)',
            'self.benchmark_thread.start()',
            'Install a Piper voice first from the Models page.',
            'self.benchmark_button.setEnabled(False)',
            'self.benchmark_thread.finished.connect(lambda: self.benchmark_button.setEnabled(True))',
        ):
            self.assertIn(required, page)
        worker = page[page.index('class _BenchmarkThread'):page.index('class HardwarePage')]
        self.assertIn('benchmark_provider(', worker)

    def test_models_page_keeps_optional_runtime_install_and_repair_recovery(self):
        page = (ROOT / "app" / "ui" / "models_page.py").read_text(encoding="utf-8")
        for required in (
            'self.install_audiobook_ai.setEnabled(False)',
            'self.audiobook_ai_worker.finished_ok.connect(self._audiobook_ai_ok)',
            'self.audiobook_ai_worker.failed.connect(self._audiobook_ai_failed)',
            'self.install_audiobook_ai.setEnabled(True)',
            'self.install_chatterbox.setEnabled(False)',
            'self.chatterbox_worker.finished_ok.connect(self._chatterbox_ok)',
            'self.chatterbox_worker.failed.connect(self._chatterbox_failed)',
            'self.repair_qwen.setEnabled(False)',
            'self.qwen_repair_worker.finished_ok.connect(self._qwen_repair_ok)',
            'self.qwen_repair_worker.failed.connect(self._qwen_repair_failed)',
            'saved profiles and downloaded models were kept.',
            'Your downloaded Qwen model files will NOT be deleted.',
        ):
            self.assertIn(required, page)

    def test_premium_v2_frontend_commands_are_registered_and_callable_in_backend(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        frontend_commands = set(re.findall(r"\bcall\(\s*['\"]([^'\"]+)['\"]", adapter))

        dispatch_start = host.index("            handlers = {", host.index("class PremiumV2Bridge"))
        dispatch_end = host.index("\n            }", dispatch_start)
        dispatch = host[dispatch_start:dispatch_end]
        handler_rows = re.findall(r"""["']([^"']+)["']\s*:\s*self\.([A-Za-z0-9_]+)""", dispatch)
        backend_commands = {command for command, _method in handler_rows}
        defined_methods = set(re.findall(r"^    def (_[A-Za-z0-9_]+)\(", host, re.MULTILINE))

        self.assertGreaterEqual(len(frontend_commands), 70, "The audited frontend command set unexpectedly shrank.")
        self.assertEqual(sorted(frontend_commands - backend_commands), [],
                         "Frontend commands are missing from the Python bridge allow-list.")
        self.assertIn("const modelLifecycleCommands = {install:'models.install',repair:'models.repair',uninstall:'models.uninstall'};", adapter)
        self.assertTrue({"models.install", "models.repair", "models.uninstall"}.issubset(backend_commands))
        missing_methods = sorted({method for _command, method in handler_rows if method not in defined_methods})
        self.assertEqual(missing_methods, [], "Bridge command handlers reference missing Python methods.")

        # Verify the command map is connected to Qt WebChannel and the adapter
        # only starts backend-dependent UI work after the bridge-ready event.
        self.assertIn('channel.registerObject("ryuBackend", self.bridge)', host)
        self.assertIn("native.dispatch(String(command), JSON.stringify(payload || {}), raw =>", host)
        self.assertIn('adapter_path = frontend_path().with_name("premium_v2_backend_adapter.js")', host)
        self.assertIn("self.web.page().runJavaScript(script)", host)
        self.assertIn("window.dispatchEvent(new CustomEvent('ryu-backend-ready'))", host)
        self.assertIn("window.addEventListener('ryu-backend-ready', start, {once:true})", adapter)

if __name__ == "__main__":
    unittest.main()
