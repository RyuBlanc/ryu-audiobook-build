import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ui.premium_v2_host import PremiumV2Bridge


class Stage3NarratorManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Path(self.temp.name)
        self.bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
        self.project = SimpleNamespace(
            title="Book One",
            folder=Path(self.temp.name) / "project",
        )
        self.state = {}

    def _write_series_default(self, name="Series Voice"):
        digest = hashlib.sha256("the series".encode("utf-8")).hexdigest()[:16]
        path = self.settings / "series-narrators" / f"the-series-{digest}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema_version": 1,
            "series": "The Series",
            "profile_name": name,
            "provider": "piper",
            "voice_id": name.lower().replace(" ", "-"),
            "updated_at": "2026-11-01T00:00:00Z",
        }), encoding="utf-8")
        return path

    def _profile(self, name):
        return SimpleNamespace(name=name)

    def test_inherited_project_uses_current_series_default_not_stale_snapshot(self):
        self._write_series_default("Series Voice V2")
        self.state = {
            "series": "The Series",
            "voice_profile": "Series Voice V1",
            "narrator_profile_source": "series_default",
        }
        self.bridge._find_profile = lambda name: self._profile(name) if name == "Series Voice V2" else None
        with patch("app.core.paths.settings_root", return_value=self.settings):
            result = self.bridge._narrator_series_default_read(None, self.state, "The Series")
        self.assertEqual(result["effective_profile_name"], "Series Voice V2")
        self.assertIsNone(result["project_profile_name"])
        self.assertEqual(result["source"], "series_default")
        self.assertTrue(result["profile_available"])

    def test_explicit_project_override_wins_over_series_default(self):
        self._write_series_default("Series Voice")
        self.state = {
            "series": "The Series",
            "voice_profile": "Book Voice",
            "narrator_profile_source": "project_override",
        }
        self.bridge._find_profile = lambda name: self._profile(name)
        with patch("app.core.paths.settings_root", return_value=self.settings):
            result = self.bridge._narrator_series_default_read(None, self.state, "The Series")
        self.assertEqual(result["effective_profile_name"], "Book Voice")
        self.assertEqual(result["project_profile_name"], "Book Voice")
        self.assertEqual(result["source"], "project_override")

    def test_legacy_project_profile_remains_an_override(self):
        self._write_series_default("Series Voice")
        self.state = {"series": "The Series", "voice_profile": "Legacy Book Voice"}
        self.bridge._find_profile = lambda name: self._profile(name)
        with patch("app.core.paths.settings_root", return_value=self.settings):
            result = self.bridge._narrator_series_default_read(None, self.state, "The Series")
        self.assertEqual(result["effective_profile_name"], "Legacy Book Voice")
        self.assertEqual(result["source"], "project_override")

    def test_missing_default_does_not_fall_back_to_inherited_snapshot(self):
        self.state = {
            "series": "The Series",
            "voice_profile": "Deleted Old Series Voice",
            "narrator_profile_source": "series_default",
        }
        self.bridge._find_profile = lambda _name: None
        with patch("app.core.paths.settings_root", return_value=self.settings):
            result = self.bridge._narrator_series_default_read(None, self.state, "The Series")
        self.assertIsNone(result["effective_profile_name"])
        self.assertEqual(result["source"], "none")
        self.assertFalse(result["profile_available"])

    def test_reset_restores_series_inheritance_and_clears_project_snapshot(self):
        self._write_series_default("Series Voice")
        self.state = {
            "series": "The Series",
            "voice_profile": "Book Override",
            "voice_id": "book-id",
            "backend": "piper",
            "narrator": "Book Override",
            "narrator_profile_source": "project_override",
        }
        self.bridge._active_project = lambda: self.project
        self.bridge._find_profile = lambda name: self._profile(name) if name == "Series Voice" else None
        with patch("app.ui.premium_v2_host.load_state", return_value=self.state):
            with patch("app.ui.premium_v2_host.save_state") as save:
                with patch("app.core.paths.settings_root", return_value=self.settings):
                    result = self.bridge._narrator_project_reset({"series": "The Series"})
        self.assertNotIn("voice_profile", self.state)
        self.assertNotIn("voice_id", self.state)
        self.assertEqual(self.state["narrator_profile_source"], "series_default")
        self.assertEqual(self.state["narrator"], "Series Voice")
        self.assertEqual(result["profile_name"], "Series Voice")
        self.assertEqual(result["source"], "series_default")
        save.assert_called_once_with(self.project.folder, self.state)


if __name__ == "__main__":
    unittest.main()
