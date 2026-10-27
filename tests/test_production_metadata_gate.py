"""Regression tests for saved Production Studio metadata completeness."""
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from app.ui.premium_v2_host import PremiumV2Bridge


class _MetadataGateHarness:
    def __init__(self, profiles):
        self.profiles = profiles

    def _find_profile(self, name):
        return self.profiles.get(str(name or "").casefold())


class ProductionMetadataGateTests(unittest.TestCase):
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
            cover.write_bytes(b"image fixture")
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
                ["Book title", "Publisher", "Series Volume", "Narrator", "Cover Image"],
            )

    def test_legacy_series_number_is_recognized_as_saved_series_volume(self):
        with tempfile.TemporaryDirectory() as temp:
            cover = Path(temp) / "cover.png"
            cover.write_bytes(b"image fixture")
            state = self.complete_state(cover)
            state.pop("series_volume")
            state["series_number"] = "3"
            harness = _MetadataGateHarness({"narrator voice": SimpleNamespace(name="Narrator Voice")})
            self.assertEqual(PremiumV2Bridge._production_metadata_missing(harness, state), [])

    def test_cover_must_exist_and_use_a_supported_image_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            invalid_cover = Path(temp) / "cover.txt"
            invalid_cover.write_text("not an image")
            state = self.complete_state(invalid_cover)
            harness = _MetadataGateHarness({"narrator voice": SimpleNamespace(name="Narrator Voice")})
            self.assertEqual(PremiumV2Bridge._production_metadata_missing(harness, state), ["Cover Image"])


if __name__ == "__main__":
    unittest.main()
