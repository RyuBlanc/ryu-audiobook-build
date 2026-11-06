"""Safety tests for staged and verified storage-root migration."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.core.storage_migration import (
    StorageMigrationError, migrate_storage_root, prepare_migration,
    read_migration_journal,
)


class StorageMigrationTests(unittest.TestCase):
    def test_success_copies_verifies_switches_and_retains_source(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "old"
            destination = base / "new"
            source.mkdir()
            (source / "nested").mkdir()
            (source / "nested" / "weights.bin").write_bytes(b"model-weights" * 100)
            persisted = []
            plan = migrate_storage_root(
                source, destination,
                persist_root=lambda path: persisted.append(path),
                validate_root=lambda path: (path / "nested" / "weights.bin").is_file(),
                reserve_bytes=0,
            )
            self.assertEqual([Path(value).resolve() for value in persisted], [destination.resolve()])
            self.assertEqual((destination / "nested" / "weights.bin").read_bytes(),
                             (source / "nested" / "weights.bin").read_bytes())
            self.assertTrue(source.exists(), "Source must remain until explicit user cleanup.")
            self.assertEqual(read_migration_journal(plan.journal)["state"], "complete_source_retained")

    def test_preflight_rejects_nonempty_destination_and_overlapping_paths(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            source.mkdir()
            (source / "a").write_text("a", encoding="utf-8")
            target = base / "target"
            target.mkdir()
            (target / "existing").write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(StorageMigrationError, "must be empty"):
                prepare_migration(source, target, reserve_bytes=0)
            with self.assertRaisesRegex(StorageMigrationError, "must not overlap"):
                prepare_migration(source, source / "child", reserve_bytes=0)

    def test_preflight_rejects_active_job_and_insufficient_space(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            source.mkdir()
            (source / "weights").write_bytes(b"x" * 1024)
            with self.assertRaisesRegex(StorageMigrationError, "active job"):
                prepare_migration(source, base / "target", reserve_bytes=0, is_busy=lambda _p: True)
            with patch("app.core.storage_migration.shutil.disk_usage") as disk:
                disk.return_value = type("Usage", (), {"free": 1, "total": 10})()
                with self.assertRaisesRegex(StorageMigrationError, "Insufficient destination space"):
                    prepare_migration(source, base / "target", reserve_bytes=0)

    def test_validation_failure_restores_source_setting_and_keeps_source(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            destination = base / "target"
            source.mkdir()
            (source / "model.bin").write_bytes(b"safe")
            persisted = []
            with self.assertRaisesRegex(StorageMigrationError, "Post-switch inventory"):
                migrate_storage_root(
                    source, destination,
                    persist_root=lambda path: persisted.append(path),
                    validate_root=lambda _path: False,
                    reserve_bytes=0,
                )
            self.assertEqual([Path(value).resolve() for value in persisted], [destination.resolve(), source.resolve()])
            self.assertTrue(source.joinpath("model.bin").is_file())

    def test_symlinked_source_content_is_rejected(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            source.mkdir()
            outside = base / "outside"
            outside.write_text("do not copy", encoding="utf-8")
            try:
                (source / "linked").symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation is not available on this runner.")
            with self.assertRaisesRegex(StorageMigrationError, "Symbolic link"):
                prepare_migration(source, base / "target", reserve_bytes=0)


if __name__ == "__main__":
    unittest.main()
