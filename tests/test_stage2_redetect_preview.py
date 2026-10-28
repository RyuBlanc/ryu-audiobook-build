"""Regression tests for the non-mutating chapter redetection preview."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
from app.ui.premium_v2_host import PremiumV2Bridge


def sample_chapters():
    body = (
        "Chapter 1: Arrival\nMira spoke softly to the guard and entered the town.\n\n"
        "Chapter 2: Return\nMira came home before the winter festival began."
    )
    return [Chapter(1, "Manual whole-book title", body)]


class Stage2RedetectionPreviewTests(unittest.TestCase):
    def _bridge_and_project(self):
        project = SimpleNamespace(chapters=sample_chapters(), save=Mock())
        bridge = SimpleNamespace(
            _active_project=Mock(return_value=project),
            _mark_project_edited=Mock(),
        )
        return bridge, project

    def test_preview_returns_before_after_and_fingerprint_without_saving(self):
        bridge, project = self._bridge_and_project()
        before_text = project.chapters[0].text
        preview = PremiumV2Bridge._chapter_redetect(bridge, {"preview": True})

        self.assertTrue(preview["preview_only"])
        self.assertFalse(preview["saved"])
        self.assertRegex(preview["source_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(len(preview["before"]), 1)
        self.assertEqual(len(preview["after"]), 2)
        self.assertIn("Mira spoke softly", preview["after"][0]["text_preview"])
        self.assertEqual(project.chapters[0].text, before_text)
        project.save.assert_not_called()

    def test_apply_without_preview_fingerprint_is_rejected_without_mutation(self):
        bridge, project = self._bridge_and_project()
        before = [(chapter.title, chapter.text) for chapter in project.chapters]
        with self.assertRaisesRegex(ValueError, "Review the before/after preview"):
            PremiumV2Bridge._chapter_redetect(bridge, {"selected_number": 1})

        self.assertEqual([(chapter.title, chapter.text) for chapter in project.chapters], before)
        project.save.assert_not_called()

    def test_apply_rejects_stale_preview_fingerprint(self):
        bridge, project = self._bridge_and_project()
        preview = PremiumV2Bridge._chapter_redetect(bridge, {"preview": True})
        project.chapters[0].title = "Changed after preview"
        with self.assertRaisesRegex(ValueError, "changed after the preview"):
            PremiumV2Bridge._chapter_redetect(bridge, {
                "selected_number": 1,
                "expected_source_fingerprint": preview["source_fingerprint"],
            })

        project.save.assert_not_called()

    def test_matching_preview_fingerprint_applies_and_persists_new_boundaries(self):
        bridge, project = self._bridge_and_project()
        preview = PremiumV2Bridge._chapter_redetect(bridge, {"preview": True})
        result = PremiumV2Bridge._chapter_redetect(bridge, {
            "selected_number": 1,
            "expected_source_fingerprint": preview["source_fingerprint"],
        })

        self.assertTrue(result["saved"])
        self.assertEqual(result["chapter_count"], 2)
        self.assertEqual(len(project.chapters), 2)
        project.save.assert_called_once()
        bridge._mark_project_edited.assert_called_once()


if __name__ == "__main__":
    unittest.main()
