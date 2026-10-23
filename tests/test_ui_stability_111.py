from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UiStabilityRegressions(unittest.TestCase):
    def test_heavy_pages_skip_full_widget_fade_and_light_fade_is_prepared_before_show(self):
        source = (ROOT / "app/ui/workflow.py").read_text(encoding="utf-8")
        transition = source.split("def _show_page", 1)[1].split("def _sidebar_changed", 1)[0]
        self.assertIn("heavy_pages", transition)
        self.assertLess(
            transition.index("widget.setGraphicsEffect(effect)"),
            transition.index("self.stack.setCurrentWidget(widget)", transition.index("widget.setGraphicsEffect(effect)")),
        )
        self.assertIn('getattr(self, "import_page", None)', transition)
        self.assertIn('getattr(self, "library", None)', transition)

    def test_library_search_is_debounced_and_status_is_cached_per_refresh(self):
        source = (ROOT / "app/ui/library.py").read_text(encoding="utf-8")
        self.assertIn("self._refresh_timer.setInterval(120)", source)
        self.assertIn("self._state_cache =", source)
        self.assertIn("self._status_cache =", source)
        self.assertNotIn("completed = sum(project_status(project)", source)

    def test_import_studio_reports_real_worker_stages_and_resets_preview_on_new_source(self):
        source = (ROOT / "app/ui/import_page.py").read_text(encoding="utf-8")
        worker = source.split("class ImportPreviewWorker", 1)[1].split("class BookDropZone", 1)[0]
        page = source.split("class ImportPage", 1)[1]
        self.assertIn("self.progress.emit(10)", worker)
        self.assertIn("self.progress.emit(55)", worker)
        self.assertIn("self.progress.emit(90)", worker)
        self.assertIn('self.status.setText("Preparing import…")', page)
        self.assertIn("self.summary.setText", page)
        self.assertIn("self.progress.setValue(0)", page)
        self.assertNotIn("Continuing … characters", page)

    def test_application_version_remains_111(self):
        source = (ROOT / "app/version.py").read_text(encoding="utf-8")
        self.assertIn('APP_VERSION = "1.1.1"', source)


if __name__ == "__main__":
    unittest.main()
