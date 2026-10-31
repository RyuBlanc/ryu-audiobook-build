import unittest
from types import MethodType, SimpleNamespace

from app.ui.voice_page import VoicePage


class VoicePreviewRaceTests(unittest.TestCase):
    def _page(self, sender, current_worker, current_generation, worker_generation, signature=("saved-profile",)):
        page = SimpleNamespace(
            sender=lambda: sender,
            preview_worker=current_worker,
            _preview_generation=current_generation,
            _preview_worker_contexts={
                id(sender): (sender, worker_generation, signature)
            },
        )
        page._preview_worker_context = MethodType(VoicePage._preview_worker_context, page)
        page._preview_event_is_current = MethodType(VoicePage._preview_event_is_current, page)
        return page

    def test_invalidated_preview_success_cannot_resurrect_old_audio(self):
        worker = object()
        page = self._page(
            sender=worker,
            current_worker=worker,
            current_generation=9,
            worker_generation=8,
        )
        page.last_preview = None
        # The callback must return before touching player controls or profile state.
        VoicePage._preview_worker_ok(page, "stale-preview.wav", 12.0)
        self.assertIsNone(page.last_preview)

    def test_late_status_from_invalidated_worker_is_ignored(self):
        worker = object()
        page = self._page(
            sender=worker,
            current_worker=worker,
            current_generation=4,
            worker_generation=3,
        )
        # If this stale signal is not rejected, the missing widget raises here.
        VoicePage._preview_worker_status(page, "stale worker status")
        self.assertEqual(page._preview_generation, 4)

    def test_old_worker_finish_does_not_clear_new_worker(self):
        old_worker = object()
        current_worker = object()

        class Button:
            def __init__(self):
                self.enabled = False

            def setEnabled(self, value):
                self.enabled = bool(value)

        page = self._page(
            sender=old_worker,
            current_worker=current_worker,
            current_generation=5,
            worker_generation=4,
        )
        page.preview_button = Button()
        VoicePage._preview_worker_finished(page)
        self.assertIs(page.preview_worker, current_worker)
        self.assertFalse(page.preview_button.enabled)
        self.assertNotIn(id(old_worker), page._preview_worker_contexts)

    def test_current_worker_is_the_only_worker_allowed_to_update_ui(self):
        worker = object()
        page = self._page(
            sender=worker,
            current_worker=worker,
            current_generation=6,
            worker_generation=6,
        )
        self.assertTrue(VoicePage._preview_event_is_current(page))


if __name__ == "__main__":
    unittest.main()
