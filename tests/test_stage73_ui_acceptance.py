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


if __name__ == "__main__":
    unittest.main()
