"""Safety tests for staged and verified storage-root migration."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.core.storage_migration import (
    StorageMigrationError, migrate_storage_root, prepare_migration,
    read_migration_journal, recover_migration_journal, safe_cleanup, cleanup_migrated_source, inventory_storage_root,
)


class StorageMigrationTests(unittest.TestCase):
    def test_inventory_reports_exact_sizes_hashes_and_unavailable_roots(self):
        with TemporaryDirectory() as temp:
            root = Path(temp) / "models"
            root.mkdir()
            (root / "a.bin").write_bytes(b"abc")
            (root / "nested").mkdir()
            (root / "nested" / "b.bin").write_bytes(b"12345")
            result = inventory_storage_root(root, include_hashes=True)
            self.assertTrue(result["available"])
            self.assertEqual(result["file_count"], 2)
            self.assertEqual(result["total_bytes"], 8)
            self.assertTrue(all(len(item["sha256"]) == 64 for item in result["files"]))
            missing = inventory_storage_root(root / "disconnected-drive")
            self.assertFalse(missing["available"])
            self.assertEqual(missing["error"], "Location unavailable")

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



    def test_source_cleanup_requires_completed_verified_migration(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            destination = base / "target"
            source.mkdir()
            (source / "weights.bin").write_bytes(b"verified weights")
            plan = migrate_storage_root(
                source, destination, persist_root=lambda _path: None,
                validate_root=lambda path: path.joinpath("weights.bin").is_file(),
                reserve_bytes=0, journal_dir=base,
            )
            result = cleanup_migrated_source(plan.journal)
            self.assertTrue(result["deleted"])
            self.assertFalse(source.exists())
            self.assertTrue(destination.joinpath("weights.bin").is_file())
            self.assertEqual(read_migration_journal(plan.journal)["state"], "source_cleanup_confirmed")
            recovered = recover_migration_journal(plan.journal, persist_root=lambda _path: self.fail("terminal journal must not rewrite settings"))
            self.assertEqual(recovered["state"], "source_cleanup_confirmed")

    def test_source_cleanup_refuses_protected_active_root(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            destination = base / "target"
            source.mkdir()
            (source / "model.bin").write_bytes(b"model")
            plan = migrate_storage_root(
                source, destination, persist_root=lambda _path: None,
                validate_root=lambda path: path.joinpath("model.bin").is_file(),
                reserve_bytes=0, journal_dir=base,
            )
            with self.assertRaisesRegex(StorageMigrationError, "protected root"):
                cleanup_migrated_source(plan.journal, protected_roots=(source,))
            self.assertTrue(source.joinpath("model.bin").is_file())

    def test_recovery_restores_source_and_removes_only_staging(self):
        with TemporaryDirectory() as temp:
            import json
            base = Path(temp)
            source = base / "source"
            source.mkdir()
            destination = base / "target"
            staging = base / ".target.ryu-migration-token.staging"
            staging.mkdir()
            (staging / "partial").write_text("partial", encoding="utf-8")
            journal = base / "journal.json"
            journal.write_text(json.dumps({
                "schema_version": 1, "state": "copying",
                "source": str(source), "destination": str(destination),
                "staging": str(staging),
            }), encoding="utf-8")
            persisted = []
            result = recover_migration_journal(journal, persist_root=lambda p: persisted.append(p))
            self.assertEqual([Path(p).resolve() for p in persisted], [source.resolve()])
            self.assertFalse(staging.exists())
            self.assertEqual(result["state"], "recovered_source_restored")

    def test_safe_cleanup_dry_run_and_protected_path(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            temp_root = base / "temporary"
            temp_root.mkdir()
            old = temp_root / "staging"
            old.mkdir()
            (old / "blob.bin").write_bytes(b"x" * 128)
            protected = temp_root / "tmp"
            protected.mkdir()
            (protected / "keep.wav").write_bytes(b"voice")
            preview = safe_cleanup(temporary_roots=(temp_root,), dry_run=True, protected_paths=(protected,))
            self.assertEqual(preview["candidate_count"], 1)
            self.assertTrue(old.exists())
            self.assertTrue(protected.exists())
            result = safe_cleanup(temporary_roots=(temp_root,), dry_run=False, protected_paths=(protected,))
            self.assertFalse(old.exists())
            self.assertTrue(protected.joinpath("keep.wav").is_file())
            self.assertEqual(len(result["removed"]), 1)

    def test_rollback_does_not_delete_destination_if_setting_restore_fails(self):
        with TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            destination = base / "target"
            source.mkdir()
            (source / "model.bin").write_bytes(b"model")
            journal_paths = []
            def persist(path):
                path = Path(path)
                if Path(path).resolve() == source.resolve():
                    raise OSError("settings backend unavailable")
            def progress(_stage, _done, _total):
                pass
            with self.assertRaises(StorageMigrationError):
                migrate_storage_root(
                    source, destination, persist_root=persist,
                    validate_root=lambda _path: False, reserve_bytes=0,
                    progress=progress, journal_dir=base,
                )
            self.assertTrue(source.joinpath("model.bin").is_file())
            self.assertTrue(destination.joinpath("model.bin").is_file())
            journal = next(base.glob("ryu-storage-migration-*.json"))
            self.assertEqual(read_migration_journal(journal)["state"], "rollback_required")

if __name__ == "__main__":
    unittest.main()
