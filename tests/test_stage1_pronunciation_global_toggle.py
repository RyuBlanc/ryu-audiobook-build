"""Regression coverage for the project-wide pronunciation On/Off contract."""

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.ui.premium_v2_host import PremiumV2Host, _effective_pronunciation_dictionary


class Stage1GlobalPronunciationToggleTests(unittest.TestCase):
    def test_global_off_suppresses_all_rules_even_when_individual_entries_are_enabled(self):
        state = {
            "pronunciation_enabled": False,
            "pronunciation_dictionary": [
                {"written_form": "Rimuru", "spoken_form": "Ree-moo-roo", "enabled": True},
                {"written_form": "Tempest", "spoken_form": "Tem-pest", "enabled": True},
            ],
        }
        with patch("app.ui.premium_v2_host._read_pronunciation_store", return_value=[]):
            self.assertEqual([], _effective_pronunciation_dictionary(state))

    def test_global_on_keeps_only_individually_enabled_entries(self):
        state = {
            "pronunciation_enabled": True,
            "pronunciation_dictionary": [
                {"written_form": "Rimuru", "spoken_form": "Ree-moo-roo", "enabled": True},
                {"written_form": "Tempest", "spoken_form": "Tem-pest", "enabled": False},
            ],
        }
        with patch("app.ui.premium_v2_host._read_pronunciation_store", return_value=[]):
            rows = _effective_pronunciation_dictionary(state)
        self.assertEqual(["Rimuru"], [row["written_form"] for row in rows])

    def test_legacy_projects_default_to_pronunciation_on(self):
        state = {"pronunciation_dictionary": [
            {"written_form": "Rimuru", "spoken_form": "Ree-moo-roo", "enabled": True}
        ]}
        with patch("app.ui.premium_v2_host._read_pronunciation_store", return_value=[]):
            rows = _effective_pronunciation_dictionary(state)
        self.assertEqual(["Rimuru"], [row["written_form"] for row in rows])

    def test_global_toggle_persists_on_the_active_project(self):
        project_folder = Path("/virtual/test-project")
        project = SimpleNamespace(folder=project_folder)
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _now=lambda: "2026-10-30T00:00:00Z",
        )
        with patch("app.ui.premium_v2_host.load_state", return_value={"title": "Test"}) as load_state, \
             patch("app.ui.premium_v2_host.save_state") as save_state:
            result = PremiumV2Host._pronunciation_enabled_set(bridge, {"enabled": False})
        self.assertTrue(result["saved"])
        self.assertFalse(result["enabled"])
        self.assertEqual("2026-10-30T00:00:00Z", result["updated_at"])
        save_state.assert_called_once_with(project_folder, {
            "title": "Test",
            "pronunciation_enabled": False,
            "pronunciation_enabled_saved_at": "2026-10-30T00:00:00Z",
            "modified_at": "2026-10-30T00:00:00Z",
        })
        load_state.assert_called_once_with(project_folder)

    def test_toggle_rejects_non_boolean_payloads(self):
        bridge = SimpleNamespace(
            _active_project=lambda: SimpleNamespace(folder=Path("/virtual/test-project")),
            _now=lambda: "2026-10-30T00:00:00Z",
        )
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            PremiumV2Host._pronunciation_enabled_set(bridge, {"enabled": "false"})

    def test_both_screens_use_the_same_saved_project_setting(self):
        html = Path("assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        adapter = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        studio = html[html.index('<section class="page" id="pronunciation">'):html.index('<section class="page" id="sound">')]
        generate = html[html.index('<section class="page" id="generate">'):html.index('<section class="page" id="player">')]
        self.assertIn('data-pronunciation-enabled="true"', studio)
        self.assertIn('data-pronunciation-enabled="false"', studio)
        self.assertIn('data-pronunciation-enabled="true"', generate)
        self.assertIn('data-pronunciation-enabled="false"', generate)
        self.assertIn('"pronunciation.enabled.get": self._pronunciation_enabled_get', host)
        self.assertIn('"pronunciation.enabled.set": self._pronunciation_enabled_set', host)
        self.assertIn("call('pronunciation.enabled.set', {enabled})", adapter)
        self.assertIn("document.querySelectorAll('#pronunciation [data-pronunciation-enabled], #generate [data-pronunciation-enabled]')", adapter)


if __name__ == "__main__":
    unittest.main()
