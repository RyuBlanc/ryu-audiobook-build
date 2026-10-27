"""Regression tests for saved Production Studio metadata completeness."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtGui import QImage
from app.ui.premium_v2_host import PremiumV2Bridge, _production_cover_is_readable


class _MetadataGateHarness:
    def __init__(self, profiles):
        self.profiles = profiles

    def _find_profile(self, name):
        return self.profiles.get(str(name or "").casefold())


class ProductionMetadataGateTests(unittest.TestCase):
    @staticmethod
    def write_valid_cover(path: Path) -> None:
        image = QImage(2, 2, QImage.Format.Format_RGB32)
        image.fill(0xFFB21F3F)
        if not image.save(str(path)):
            raise AssertionError(f"Could not write valid image fixture: {path}")

    def complete_state(self, cover_path):
        return {
            "book_title": "The Saved Book",
            "author": "Author Name",
            "publisher": "Publisher Name",
            "series": "Series Name",
            "series_volume": "2",
            "language": "English",
            "year": "2026",
            "genre": "Fantasy",
            "voice_profile": "Narrator Voice",
            "cover_path": str(cover_path),
        }

    def test_complete_saved_metadata_and_real_narrator_pass_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            cover = Path(temp) / "cover.jpg"
            self.write_valid_cover(cover)
            state = self.complete_state(cover)
            harness = _MetadataGateHarness({"narrator voice": SimpleNamespace(name="Narrator Voice")})
            self.assertEqual(PremiumV2Bridge._production_metadata_missing(harness, state), [])

    def test_missing_saved_fields_are_reported_in_register_order(self):
        with tempfile.TemporaryDirectory() as temp:
            state = self.complete_state(Path(temp) / "missing.png")
            state["book_title"] = ""
            state["publisher"] = ""
            state["series_volume"] = ""
            state["voice_profile"] = "Deleted Narrator"
            harness = _MetadataGateHarness({})
            self.assertEqual(
                PremiumV2Bridge._production_metadata_missing(harness, state),
                ["Book title", "Narrator", "Publisher", "Series Volume", "Cover Image"],
            )

    def test_legacy_series_number_is_recognized_as_saved_series_volume(self):
        with tempfile.TemporaryDirectory() as temp:
            cover = Path(temp) / "cover.png"
            self.write_valid_cover(cover)
            state = self.complete_state(cover)
            state.pop("series_volume")
            state["series_number"] = "3"
            harness = _MetadataGateHarness({"narrator voice": SimpleNamespace(name="Narrator Voice")})
            self.assertEqual(PremiumV2Bridge._production_metadata_missing(harness, state), [])

    def test_corrupt_file_with_supported_extension_is_not_a_valid_cover(self):
        with tempfile.TemporaryDirectory() as temp:
            corrupt_cover = Path(temp) / "corrupt.jpg"
            corrupt_cover.write_bytes(b"not a readable image")
            self.assertFalse(_production_cover_is_readable(corrupt_cover))
            state = self.complete_state(corrupt_cover)
            harness = _MetadataGateHarness({"narrator voice": SimpleNamespace(name="Narrator Voice")})
            self.assertEqual(
                PremiumV2Bridge._production_metadata_missing(harness, state),
                ["Cover Image"],
            )

    def test_saving_empty_cover_clears_a_corrupt_legacy_cover_path(self):
        with tempfile.TemporaryDirectory() as temp:
            corrupt_cover = Path(temp) / "corrupt.jpg"
            corrupt_cover.write_bytes(b"not a readable image")
            state = self.complete_state(corrupt_cover)
            state_store = dict(state)
            project = SimpleNamespace(folder=Path(temp), title="The Saved Book")

            class SaveHarness(_MetadataGateHarness):
                def _active_project(self):
                    return project

                def _production_metadata_get(self, _payload):
                    return {}

            harness = SaveHarness({"narrator voice": SimpleNamespace(name="Narrator Voice")})

            def fake_load_state(_folder):
                return dict(state_store)

            def fake_save_state(_folder, replacement):
                state_store.clear()
                state_store.update(replacement)

            payload = {
                "book_title": "The Saved Book",
                "author": "Author Name",
                "publisher": "Publisher Name",
                "series": "Series Name",
                "series_volume": "2",
                "language": "English",
                "year": "2026",
                "genre": "Fantasy",
                "cover_path": "",
            }
            with (
                patch("app.ui.premium_v2_host.load_state", side_effect=fake_load_state),
                patch("app.ui.premium_v2_host.save_state", side_effect=fake_save_state),
            ):
                result = PremiumV2Bridge._production_metadata_save(harness, payload)

            self.assertTrue(result["saved"])
            self.assertNotIn("cover_path", state_store)
            self.assertEqual(
                PremiumV2Bridge._production_metadata_missing(harness, state_store),
                ["Cover Image"],
            )

    def test_cover_must_exist_and_use_a_supported_image_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid_cover = Path(temp) / "cover.txt"
            invalid_cover.write_text("not an image")
            state = self.complete_state(invalid_cover)
            harness = _MetadataGateHarness({"narrator voice": SimpleNamespace(name="Narrator Voice")})
            self.assertEqual(PremiumV2Bridge._production_metadata_missing(harness, state), ["Cover Image"])


if __name__ == "__main__":
    unittest.main()
