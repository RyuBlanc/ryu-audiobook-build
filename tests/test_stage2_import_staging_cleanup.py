"""Stage 2 regression tests for streamed duplicate checks and safe import staging cleanup."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.ui.premium_v2_host import _cleanup_staged_import_file, _sha256_file


class ImportStagingCleanupTests(unittest.TestCase):
    def test_hash_reads_large_files_incrementally_and_matches_sha256(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large-book.txt"
            content = (b"chapter text\n" * 180_000) + b"last line"
            path.write_bytes(content)
            self.assertEqual(_sha256_file(path, chunk_size=64 * 1024), hashlib.sha256(content).hexdigest())

    def test_cleanup_removes_a_temporary_drop_file_under_incoming_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "incoming_imports"
            incoming.mkdir()
            staged = incoming / "drop-123.txt"
            staged.write_text("temporary content", encoding="utf-8")
            with patch("app.ui.premium_v2_host.app_root", return_value=root):
                _cleanup_staged_import_file(staged)
            self.assertFalse(staged.exists())

    def test_cleanup_preserves_a_user_selected_source_outside_incoming_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "incoming_imports"
            incoming.mkdir()
            original = root / "My Novel.txt"
            original.write_text("preserve this source", encoding="utf-8")
            with patch("app.ui.premium_v2_host.app_root", return_value=root):
                _cleanup_staged_import_file(original)
            self.assertTrue(original.is_file())
            self.assertEqual(original.read_text(encoding="utf-8"), "preserve this source")

    def test_cleanup_is_idempotent_for_missing_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            incoming = root / "incoming_imports"
            incoming.mkdir()
            staged = incoming / "already-removed.txt"
            with patch("app.ui.premium_v2_host.app_root", return_value=root):
                _cleanup_staged_import_file(staged)
                _cleanup_staged_import_file(staged)
            self.assertFalse(staged.exists())


if __name__ == "__main__":
    unittest.main()
