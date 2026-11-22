from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"
ADAPTER = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"


class CharacterLibraryBulkUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.host = HOST.read_text(encoding="utf-8")
        cls.adapter = ADAPTER.read_text(encoding="utf-8")

    def test_bulk_library_and_recovery_commands_are_real_and_advertised(self):
        for command, handler in {
            "character_library.delete_many": "_character_library_delete_many",
            "character_library.deleted.purge_many": "_character_library_deleted_purge_many",
            "character_library.deleted.clear_all": "_character_library_deleted_clear_all",
        }.items():
            self.assertIn(f'"{command}": self.{handler}', self.host)
            self.assertIn(f'"{command}": True', self.host)
        self.assertIn('if "ids" not in payload', self.host)

    def test_library_has_multi_select_move_to_recovery_and_selection_count(self):
        self.assertIn("Select All Visible", self.adapter)
        self.assertIn("Move Selected to Recovery", self.adapter)
        self.assertIn("character_library.delete_many", self.adapter)
        self.assertIn("data-select-library", self.adapter)
        self.assertIn("characterLibrarySelection.clear()", self.adapter)

    def test_recovery_bin_supports_select_clear_selected_and_clear_all(self):
        self.assertIn("data-select-all-deleted-characters", self.adapter)
        self.assertIn("data-purge-selected-characters", self.adapter)
        self.assertIn("data-purge-all-characters", self.adapter)
        self.assertIn("character_library.deleted.purge_many", self.adapter)
        self.assertIn("character_library.deleted.clear_all", self.adapter)
        self.assertIn("This cannot be undone.", self.adapter)

    def test_cards_and_compact_rows_have_fixed_slots_and_soft_assignment_surface(self):
        for token in (
            ".library-character-assignment{",
            "background:rgba(185,198,219,.055)",
            "grid-template-rows:48px 42px 58px 48px 42px 34px",
            ".character-library-compact>.library-character-card",
            "grid-template-columns:175px 150px 190px",
            "grid-template-rows:minmax(0,1fr)",
            "text-overflow:ellipsis",
            "white-space:nowrap",
        ):
            self.assertIn(token, self.adapter)
        self.assertIn("library-character-assignment-label", self.adapter)
        self.assertIn("ASSIGNED VOICE", self.adapter)
        self.assertIn("library-character-sample", self.adapter)


if __name__ == "__main__":
    unittest.main()
