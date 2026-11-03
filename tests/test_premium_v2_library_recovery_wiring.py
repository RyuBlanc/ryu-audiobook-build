from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PremiumV2LibraryRecoveryWiringTests(unittest.TestCase):
    """Guard the actual Premium V2 frontend/bridge, not the older Qt Library page."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        cls.host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        cls.trash = (ROOT / "app" / "core" / "project_trash.py").read_text(encoding="utf-8")
        cls.characters = (ROOT / "app" / "core" / "character_library.py").read_text(encoding="utf-8")

    def test_audiobook_library_card_delete_is_connected_to_recoverable_backend(self) -> None:
        self.assertIn("data-delete-project", self.adapter)
        self.assertIn("data-select-project", self.adapter)
        # Premium V2 exposes recoverable Trash separately from confirmed permanent deletion.
        self.assertIn("Move to Trash (", self.adapter)
        self.assertIn("call('project.trash'", self.adapter)
        self.assertIn("async function deleteSelectedProjectsPermanently()", self.adapter)
        self.assertIn("call('project.delete', {folder: project.folder})", self.adapter)
        self.assertIn('"project.delete": self._project_delete', self.host)
        self.assertIn("Deleted Books / Recover", self.adapter)
        self.assertIn("call('project.trash.list')", self.adapter)
        self.assertIn("call('project.trash.restore'", self.adapter)
        self.assertIn("call('project.trash.purge'", self.adapter)
        self.assertIn('"project.trash": self._project_trash', self.host)
        self.assertIn('"project.trash.restore": self._project_trash_restore', self.host)
        self.assertIn("def trash_project(", self.trash)
        self.assertIn("def restore_project(", self.trash)
        self.assertIn("def purge_trashed_project(", self.trash)

    def test_live_character_library_uses_the_shared_persistent_registry(self) -> None:
        self.assertIn("list_reusable_characters()", self.host)
        self.assertIn("list_reusable_deleted_characters()", self.host)
        self.assertIn("sync_reusable_characters(", self.host)
        self.assertIn('"character_library.deleted.list": self._character_library_deleted_list', self.host)
        self.assertIn('"character_library.restore": self._character_library_restore', self.host)
        self.assertIn("dialogue_sample", self.characters)
        self.assertIn("def soft_delete_character(", self.characters)
        self.assertIn("def restore_character(", self.characters)
        self.assertIn("characterRecoveryModal", self.adapter)
        self.assertIn("data-restore-character", self.adapter)
        self.assertIn("editCharacterDialogueSample", self.adapter)
        self.assertIn("character-library-compact", self.adapter)
        self.assertIn('"short": row.get("short") or row.get("short_name") or ""', self.host)

    def test_character_library_does_not_synthesize_demo_cast(self) -> None:
        self.assertIn("Existing saved casts are indexed automatically", self.adapter)
        self.assertIn("no sample characters are inserted", self.adapter)
        self.assertIn("def _character_library_bootstrap", self.host)


if __name__ == "__main__":
    unittest.main()
