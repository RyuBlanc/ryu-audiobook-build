"""Stage 2 import edge-case tests: duplicate detection, cancellation and failure status."""
import base64
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
from app.ui.premium_v2_host import PremiumV2Bridge


def bridge_harness(job_id="import-test"):
    event = threading.Event()
    bridge = SimpleNamespace(
        _jobs_lock=threading.RLock(),
        _import_cancel_events={job_id: event},
        _new_job=Mock(return_value=job_id),
        _job_update=Mock(return_value={}),
        _now=Mock(return_value="2026-10-28T00:00:00Z"),
        _format_import_error=PremiumV2Bridge._format_import_error,
        _import_worker=Mock(),
        settings=SimpleNamespace(setValue=Mock(), sync=Mock()),
    )
    return bridge, event


class Stage2ImportEdgeCaseTests(unittest.TestCase):
    def test_duplicate_import_is_rejected_with_existing_project_guidance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            selected = root / "selected.txt"
            existing = root / "already-imported.txt"
            content = "Chapter 1: Arrival\nMira reached the old city gate before sunset."
            selected.write_text(content, encoding="utf-8")
            existing.write_text(content, encoding="utf-8")
            project = SimpleNamespace(title="Existing Local Book", source_path=existing)
            bridge, _event = bridge_harness()

            with patch("app.ui.premium_v2_host.list_projects", return_value=[project]), \
                 patch("app.ui.premium_v2_host.threading.Thread") as thread:
                with self.assertRaisesRegex(ValueError, "Open that project from Audiobook Library"):
                    PremiumV2Bridge._import_start(bridge, {"file_path": str(selected)})

            bridge._new_job.assert_not_called()
            thread.assert_not_called()
            self.assertTrue(selected.is_file())
            self.assertTrue(existing.is_file())

    def test_duplicate_dropped_file_cleans_temporary_staging_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            existing = root / "already-imported.txt"
            content = b"Chapter 1: Arrival\\nMira reached the old city gate before sunset."
            existing.write_bytes(content)
            project = SimpleNamespace(title="Existing Drop", source_path=existing)
            bridge, _event = bridge_harness()
            incoming = root / "incoming_imports"

            with patch("app.ui.premium_v2_host.app_root", return_value=root), \
                 patch("app.ui.premium_v2_host.list_projects", return_value=[project]):
                with self.assertRaisesRegex(ValueError, "Open that project from Audiobook Library"):
                    PremiumV2Bridge._import_start(bridge, {
                        "content_base64": base64.b64encode(content).decode("ascii"),
                        "file_name": "same-book.txt",
                    })

            bridge._new_job.assert_not_called()
            self.assertTrue(existing.is_file())
            self.assertTrue(incoming.is_dir())
            self.assertEqual(list(incoming.iterdir()), [])

    def test_empty_and_unsupported_files_are_rejected_before_job_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            empty = root / "empty.txt"
            empty.write_bytes(b"")
            unsupported = root / "book.zip"
            unsupported.write_bytes(b"archive")
            bridge, _event = bridge_harness()

            with self.assertRaisesRegex(ValueError, "file is empty"):
                PremiumV2Bridge._import_start(bridge, {"file_path": str(empty)})
            with self.assertRaisesRegex(ValueError, "Unsupported format"):
                PremiumV2Bridge._import_start(bridge, {"file_path": str(unsupported)})

            bridge._new_job.assert_not_called()

    def test_cancel_after_extraction_publishes_no_project_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "cancel-me.txt"
            source.write_text("Chapter 1: Arrival\nMira reaches the city gate.", encoding="utf-8")
            bridge, cancel_event = bridge_harness()
            with patch("app.ui.premium_v2_host.app_root", return_value=root), \
                 patch("app.ui.premium_v2_host.extract_text",
                       side_effect=lambda _path: (cancel_event.set() or SimpleNamespace(
                           text="Chapter 1: Arrival\nMira reaches the city gate.", title="Cancelled"
                       ))), \
                 patch("app.ui.premium_v2_host.create_project") as create:
                PremiumV2Bridge._import_worker(bridge, "import-test", source, "Cancelled", cancel_event)

            self.assertTrue(source.is_file())
            create.assert_not_called()
            self.assertTrue(any(
                call.kwargs.get("state") == "cancelled" and call.kwargs.get("stage") == "Import cancelled"
                for call in bridge._job_update.call_args_list
            ))

    def test_cancel_after_detection_publishes_no_project_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "cancel-after-detect.txt"
            source_text = "Chapter 1: Arrival\nMira reaches the old city gate before sunset."
            source.write_text(source_text, encoding="utf-8")
            bridge, cancel_event = bridge_harness()

            def detect_then_cancel(_text):
                cancel_event.set()
                return [Chapter(1, "Chapter 1: Arrival", source_text)]

            with patch("app.ui.premium_v2_host.app_root", return_value=root), \
                 patch("app.ui.premium_v2_host.extract_text",
                       return_value=SimpleNamespace(text=source_text, title="Cancelled")), \
                 patch("app.ui.premium_v2_host.detect_chapters", side_effect=detect_then_cancel), \
                 patch("app.ui.premium_v2_host.validate_chapter_text_coverage"), \
                 patch("app.ui.premium_v2_host.detect_repeated_book_noise", return_value={}), \
                 patch("app.ui.premium_v2_host.clean_import_noise", side_effect=lambda text, _noise: (text, [])), \
                 patch("app.ui.premium_v2_host.create_project") as create:
                PremiumV2Bridge._import_worker(bridge, "import-test", source, "Cancelled", cancel_event)

            self.assertTrue(source.is_file())
            create.assert_not_called()
            self.assertTrue(any(
                call.kwargs.get("state") == "cancelled" and call.kwargs.get("stage") == "Import cancelled"
                for call in bridge._job_update.call_args_list
            ))

    def test_failed_import_can_be_retried_without_losing_the_original_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "retry-book.txt"
            source.write_text("Chapter 1: Arrival\\nMira reaches the city gate.", encoding="utf-8")
            bridge, cancel_event = bridge_harness("import-first")
            bridge._new_job.side_effect = ["import-first", "import-retry"]
            with patch("app.ui.premium_v2_host.app_root", return_value=root), \
                 patch("app.ui.premium_v2_host.extract_text", side_effect=ValueError("temporary extraction failure")):
                PremiumV2Bridge._import_worker(bridge, "import-first", source, "Retry Book", cancel_event)

            self.assertTrue(source.is_file())
            self.assertTrue(any(
                call.kwargs.get("state") == "failed" and call.kwargs.get("recoverable") is True
                for call in bridge._job_update.call_args_list
            ))

            with patch("app.ui.premium_v2_host.list_projects", return_value=[]), \
                 patch("app.ui.premium_v2_host.threading.Thread") as thread:
                result = PremiumV2Bridge._import_start(bridge, {"file_path": str(source)})

            self.assertEqual(result["job_id"], "import-retry")
            self.assertEqual(result["state"], "running")
            self.assertTrue(source.is_file())
            bridge._new_job.assert_called_with("import", "Import retry-book", "Extract text and detect chapters")
            thread.assert_called_once()
            thread.return_value.start.assert_called_once()

    def test_extract_failure_reports_actionable_failed_job_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "damaged.txt"
            source.write_text("not readable", encoding="utf-8")
            bridge, cancel_event = bridge_harness()
            with patch("app.ui.premium_v2_host.app_root", return_value=root), \
                 patch("app.ui.premium_v2_host.extract_text", side_effect=ValueError("parser rejected damaged input")), \
                 patch("app.ui.premium_v2_host.create_project") as create:
                PremiumV2Bridge._import_worker(bridge, "import-test", source, "Damaged", cancel_event)

            self.assertTrue(source.is_file())
            create.assert_not_called()
            failed = [
                call.kwargs for call in bridge._job_update.call_args_list
                if call.kwargs.get("state") == "failed" and call.kwargs.get("stage") == "Import failed"
            ]
            self.assertEqual(len(failed), 1)
            self.assertEqual(failed[0]["error"]["code"], "import_failed")
            self.assertIn("parser rejected damaged input", failed[0]["message"])
            self.assertTrue(failed[0]["recoverable"])


if __name__ == "__main__":
    unittest.main()
