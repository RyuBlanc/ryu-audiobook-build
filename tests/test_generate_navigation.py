from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# Set Qt's headless platform before importing any Qt modules in CI.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.chapters.detector import Chapter
from app.core.project import Project
from app.ui.workflow import ProjectWorkflow


class GenerateNavigationSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

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
                workflow.select_section("Generate")
                QTest.qWait(125)

                self.assertIs(workflow.stack.currentWidget(), page)
                self.assertTrue(page.isVisible(), "Generate must become the visible stacked page.")
                self.assertTrue(page.title.isVisible(), "The book metadata form must be visible.")
                self.assertTrue(page.preview_button.isVisible(), "Voice preview controls must be visible.")
                self.assertTrue(page.start_button.isVisible(), "Audiobook generation controls must be visible.")
                self.assertEqual(page.title.text(), project.title)
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
