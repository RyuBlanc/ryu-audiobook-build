from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Set Qt's headless platform before importing any Qt modules in CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.chapters.detector import Chapter
from app.core.paths import ensure_roots
from app.core.project import Project
from app.ui.workflow import ProjectWorkflow, _import_book_icon


class GenerateNavigationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Match production startup: the Library page expects the app roots to
        # exist before ProjectWorkflow constructs and refreshes its library.
        ensure_roots()
        cls.app = QApplication.instance() or QApplication([])

    def test_branded_import_icon_resource_is_loadable(self) -> None:
        icon = _import_book_icon()
        self.assertFalse(icon.isNull(), "The branded Import control must have a packaged logo resource.")

    def test_grouped_navigation_shell_preserves_backend_page_keys(self) -> None:
        workflow = ProjectWorkflow()
        try:
            page_keys = [
                workflow.sidebar.item(i).data(32)
                for i in range(workflow.sidebar.count())
                if workflow.sidebar.item(i).data(32)
            ]
            self.assertEqual(
                page_keys,
                ["Dashboard", "Library", "Import", "Chapters", "Voice & Narration",
                 "Voice Cast", "Pronunciation", "Sound Design", "Generate", "Audiobooks",
                 "History", "Models", "Hardware", "Settings"],
            )
            group_labels = [
                workflow.sidebar.item(i).text()
                for i in range(workflow.sidebar.count())
                if not workflow.sidebar.item(i).data(32)
            ]
            self.assertEqual(group_labels, ["HOME", "PROJECT", "PRODUCTION", "SYSTEM"])
            self.assertEqual(workflow.page_heading.text(), "Dashboard")
            self.assertEqual(workflow.sidebar.currentItem().data(32), "Dashboard")
            self.assertIsNotNone(workflow.global_search)
            self.assertIsNotNone(workflow.project_mini_title)
        finally:
            workflow.close()
            workflow.deleteLater()
            self.app.processEvents()

    def _project(self, folder: Path) -> Project:
        folder.mkdir(parents=True, exist_ok=True)
        project = Project(
            title="Generate Navigation Smoke Test",
            folder=folder,
            source_path=None,
            chapters=[
                Chapter(
                    1,
                    "Smoke Test Chapter",
                    "A short sample chapter verifies that the Generate screen can be opened.",
                )
            ],
        )
        project.save()
        return project

    def test_reference_destinations_are_real_pages_and_refresh(self) -> None:
        workflow = ProjectWorkflow()
        try:
            self.assertIsNotNone(workflow.audiobooks_page)
            self.assertIsNotNone(workflow.history_page)
            self.assertIsNotNone(workflow.settings_page)

            workflow.select_section("Audiobooks")
            self.assertIs(workflow.stack.currentWidget(), workflow.audiobooks_page)
            workflow.select_section("History")
            self.assertIs(workflow.stack.currentWidget(), workflow.history_page)
            workflow.select_section("Settings")
            self.assertIs(workflow.stack.currentWidget(), workflow.settings_page)
        finally:
            workflow.close()
            workflow.deleteLater()

    def test_prototype_workflow_rail_routes_to_real_pages(self) -> None:
        workflow = ProjectWorkflow()
        try:
            self.assertEqual(
                list(workflow.workflow_step_buttons),
                ["Import", "Chapters", "Voice & Narration", "Voice Cast", "Pronunciation",
                 "Sound Design", "Generate", "Audiobooks"],
            )
            self.assertTrue(hasattr(workflow, "theme_toggle"))
            self.assertTrue(hasattr(workflow, "notifications_button"))
            self.assertTrue(hasattr(workflow, "menu_toggle"))
            self.assertTrue(hasattr(workflow, "mini_player_bar"))
            self.assertIsNotNone(workflow.audiobooks_page.player)
            workflow.select_section("Import")
            self.assertTrue(workflow.workflow_step_buttons["Import"].isChecked())
            self.assertIs(workflow.stack.currentWidget(), workflow.import_page)
            workflow.select_section("Voice Cast")
            self.assertTrue(workflow.workflow_step_buttons["Voice Cast"].isChecked())
            workflow.select_section("Pronunciation")
            self.assertTrue(workflow.workflow_step_buttons["Pronunciation"].isChecked())
            workflow.select_section("Audiobooks")
            self.assertTrue(workflow.workflow_step_buttons["Audiobooks"].isChecked())
            self.assertIs(workflow.stack.currentWidget(), workflow.audiobooks_page)
            workflow.stack.setCurrentWidget(workflow.import_page)
            workflow.workflow_step_buttons["Audiobooks"].click()
            self.assertIs(workflow.stack.currentWidget(), workflow.audiobooks_page)
        finally:
            workflow.close()
            workflow.deleteLater()

    def test_generate_page_constructs_and_is_visible_for_an_open_book(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ryu-generate-navigation-") as temp:
            root = Path(temp)
            workflow = ProjectWorkflow()
            project = self._project(root / "sample-project")
            try:
                workflow.show()
                workflow.open_project(project)
                self.app.processEvents()

                self.assertIsNotNone(workflow.generation, "Opening a project must create its Generate page.")
                page = workflow.generation
                self.assertEqual(
                    page.bgm_variation.count(),
                    1,
                    "A fresh local library should show Auto until real music files are imported.",
                )
                self.assertEqual(page.bgm_variation.currentData(), "auto")
                workflow.select_section("Generate")
                QTest.qWait(125)

                self.assertIs(workflow.stack.currentWidget(), page)
                self.assertTrue(page.isVisible(), "Generate must become the visible stacked page.")
                self.assertTrue(page.title.isVisible(), "The book metadata form must be visible.")
                self.assertTrue(page.preview_button.isVisible(), "Voice preview controls must be visible.")
                self.assertTrue(page.start_button.isVisible(), "Audiobook generation controls must be visible.")
                self.assertTrue(page.preview_opening_cue.isVisible(), "Opening-cue preview must be present.")
                self.assertTrue(page.preview_page_cue.isVisible(), "Chapter-turn preview must be present.")
                self.assertTrue(page.preview_ending_cue.isVisible(), "Book-closing preview must be present.")
                self.assertEqual(page.title.text(), project.title)
            finally:
                workflow.close()
                workflow.deleteLater()
                self.app.processEvents()

    def test_import_preview_page_constructs_and_drop_zone_is_enabled(self) -> None:
        workflow = ProjectWorkflow()
        try:
            self.assertTrue(workflow.import_page.drop_zone.acceptDrops())
            self.assertFalse(workflow.import_page.create_button.isEnabled())
            self.assertTrue(workflow.import_page.preview.isReadOnly())
            self.assertEqual(workflow.import_page.objectName(), "")
        finally:
            workflow.close()
            workflow.deleteLater()
            self.app.processEvents()

    def test_dashboard_is_backed_by_local_project_library(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ryu-dashboard-") as temp:
            workflow = ProjectWorkflow()
            project = self._project(Path(temp) / "sample-project")
            try:
                with patch("app.ui.dashboard_page.list_projects", return_value=[project]):
                    workflow.dashboard.refresh()
                self.assertEqual(workflow.dashboard.metric_total.metric_value.text(), "1")
                self.assertEqual(workflow.dashboard.recent_list.count(), 1)
                self.assertIn(project.title, workflow.dashboard.recent_list.item(0).text())
                self.assertEqual(workflow.dashboard.continue_title.text(), project.title)
                self.assertFalse(workflow.dashboard.continue_card.isHidden())
            finally:
                workflow.close()
                workflow.deleteLater()
                self.app.processEvents()

    def test_library_matches_html_segmented_filters(self) -> None:
        from app.ui.library import project_matches
        from app.core.project import Project
        from app.chapters.detector import Chapter
        from pathlib import Path
        project = Project("A Test Book", Path("/tmp/a-test-book"), Path("/tmp/source.txt"), [Chapter(1, "Chapter 1", "Text")])
        self.assertTrue(project_matches(project, "test", "All"))
        self.assertFalse(project_matches(project, "source", "Active"))
        self.assertFalse(project_matches(project, "test", "Completed"))

    def test_library_supports_grid_and_list_views(self) -> None:
        workflow = ProjectWorkflow()
        try:
            self.assertEqual(workflow.library.list.viewMode(), workflow.library.list.ViewMode.IconMode)
            workflow.library.set_view_mode("list")
            self.assertEqual(workflow.library.list.viewMode(), workflow.library.list.ViewMode.ListMode)
            workflow.library.set_view_mode("grid")
            self.assertEqual(workflow.library.list.viewMode(), workflow.library.list.ViewMode.IconMode)
        finally:
            workflow.close()
            workflow.deleteLater()
            self.app.processEvents()

    def test_failed_generate_refresh_preserves_a_live_page_for_the_same_book(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ryu-generate-transaction-") as temp:
            workflow = ProjectWorkflow()
            project = self._project(Path(temp) / "sample-project")
            try:
                workflow.show()
                workflow.open_project(project)
                page = workflow.generation
                self.assertIsNotNone(page)
                workflow.stack.setCurrentWidget(page)

                with patch(
                    "app.ui.workflow.GenerationPage",
                    side_effect=RuntimeError("simulated page-construction failure"),
                ):
                    workflow.ensure_generation_page()

                self.assertIs(workflow.generation, page)
                self.assertGreaterEqual(workflow.stack.indexOf(page), 0)
                self.assertIs(workflow.stack.currentWidget(), page)
                self.assertIn("Generate refresh failed", page.status.text())
            finally:
                workflow.close()
                workflow.deleteLater()
                self.app.processEvents()

    def test_clicking_already_selected_generate_item_recovers_navigation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ryu-generate-reclick-") as temp:
            workflow = ProjectWorkflow()
            project = self._project(Path(temp) / "sample-project")
            try:
                workflow.show()
                workflow.open_project(project)
                workflow.select_section("Generate")
                QTest.qWait(100)

                self.assertEqual(
                    workflow.sidebar.currentItem().data(32),
                    "Generate",
                    "Test setup requires Generate to be selected in the sidebar.",
                )
                self.assertIs(workflow.stack.currentWidget(), workflow.generation)

                # Simulate a stale stack/page transition while the sidebar remains
                # on Generate. Clicking that same row must still restore Generate.
                workflow.stack.setCurrentWidget(workflow.import_page)
                item = workflow.sidebar.currentItem()
                rect = workflow.sidebar.visualItemRect(item)
                QTest.mouseClick(
                    workflow.sidebar.viewport(),
                    Qt.MouseButton.LeftButton,
                    pos=rect.center(),
                )
                QTest.qWait(100)

                self.assertIs(workflow.stack.currentWidget(), workflow.generation)
                self.assertTrue(workflow.generation.isVisible())
            finally:
                workflow.close()
                workflow.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
