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
            "load_state(latest.folder)",
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
        self.assertIn("self.search.textChanged.connect(self.refresh)", library)
        self.assertIn("project_matches(project, query, status_filter)", library)
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
            'self.setObjectName("importScroll")',
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
        self.assertIn('chapter_words < int(source_words * 0.90)', import_page)
        self.assertIn('Import was stopped to protect your book from losing content.', import_page)
        self.assertIn('self.status.setText(f"Import analysis failed: {message}")', import_page)


if __name__ == "__main__":
    unittest.main()
