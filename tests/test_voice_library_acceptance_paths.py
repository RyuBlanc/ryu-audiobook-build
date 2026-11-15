"""Functional security tests for opt-in packaged Voice Library acceptance paths."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.ui.voice_library_acceptance import (
    ACCEPTANCE_ROOT_ENV,
    resolve_voice_library_acceptance_path,
)


class VoiceLibraryAcceptancePathTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        (self.root / "exports").mkdir()
        self.environment = patch.dict(os.environ, {ACCEPTANCE_ROOT_ENV: str(self.root)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def test_disabled_acceptance_root_preserves_native_dialog_flow(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolve_voice_library_acceptance_path({}, "path"))

    def test_enabled_acceptance_root_fails_closed_when_payload_path_is_missing(self):
        with self.assertRaisesRegex(ValueError, "must be supplied"):
            resolve_voice_library_acceptance_path({}, "acceptance_output_path")

    def test_relative_destination_is_resolved_below_acceptance_root(self):
        result = resolve_voice_library_acceptance_path(
            {"path": "exports/profiles.ryuvoice"}, "path"
        )
        self.assertEqual(result, (self.root / "exports" / "profiles.ryuvoice").resolve())

    def test_absolute_destination_inside_acceptance_root_is_allowed(self):
        destination = self.root / "exports" / "profiles.ryuvoice"
        result = resolve_voice_library_acceptance_path({"path": str(destination)}, "path")
        self.assertEqual(result, destination.resolve())

    def test_relative_parent_traversal_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "stay inside"):
            resolve_voice_library_acceptance_path(
                {"path": "../outside.ryuvoice"}, "path"
            )

    def test_absolute_path_outside_acceptance_root_is_rejected(self):
        outside = self.root.parent / "outside.ryuvoice"
        with self.assertRaisesRegex(ValueError, "stay inside"):
            resolve_voice_library_acceptance_path({"path": str(outside)}, "path")

    def test_import_path_must_exist_and_be_a_regular_file(self):
        source = self.root / "exports" / "source.ryuvoice"
        source.write_bytes(b"bundle")
        self.assertEqual(
            resolve_voice_library_acceptance_path(
                {"path": str(source)}, "path", must_exist=True
            ),
            source.resolve(),
        )
        with self.assertRaises(FileNotFoundError):
            resolve_voice_library_acceptance_path(
                {"path": "exports/missing.ryuvoice"}, "path", must_exist=True
            )
        with self.assertRaisesRegex(ValueError, "regular file"):
            resolve_voice_library_acceptance_path(
                {"path": "exports"}, "path", must_exist=True
            )

    def test_direct_symlink_is_rejected(self):
        target = self.root / "exports" / "real.ryuvoice"
        target.write_bytes(b"bundle")
        link = self.root / "exports" / "link.ryuvoice"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Symlink creation is unavailable on this runner: {exc}")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            resolve_voice_library_acceptance_path(
                {"path": str(link)}, "path", must_exist=True
            )

    def test_symlinked_parent_is_rejected_even_when_target_is_inside_root(self):
        actual = self.root / "exports" / "actual"
        actual.mkdir()
        link = self.root / "exports" / "linked"
        try:
            link.symlink_to(actual, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Directory symlink creation is unavailable on this runner: {exc}")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            resolve_voice_library_acceptance_path(
                {"path": "exports/linked/new.ryuvoice"}, "path"
            )

    def test_acceptance_root_must_be_an_existing_directory(self):
        missing = self.root / "not-created"
        with patch.dict(os.environ, {ACCEPTANCE_ROOT_ENV: str(missing)}):
            with self.assertRaises(FileNotFoundError):
                resolve_voice_library_acceptance_path({"path": "file"}, "path")


if __name__ == "__main__":
    unittest.main()
