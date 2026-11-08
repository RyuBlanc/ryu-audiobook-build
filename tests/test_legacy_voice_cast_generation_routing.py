from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.ui.premium_v2_host import PremiumV2Bridge


class LegacyVoiceCastGenerationRoutingTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [
            SimpleNamespace(name="Mira Character", voice_id="mira-engine", provider="piper"),
            SimpleNamespace(name="Ren Character", voice_id="ren-engine", provider="qwen-character"),
        ]
        self.bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)

    def test_legacy_voice_cast_entries_are_merged_into_effective_generation_cast(self):
        rows, issues = self.bridge._effective_generation_character_rows(
            {
                "characters": [{"name": "Mira", "series": "Series One"}],
                "voice_cast": {
                    "Mira": "Mira Character",
                    "Ren": "Ren Character",
                },
            },
            "Series One",
            available_profiles=self.profiles,
        )
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(issues, [])
        self.assertEqual(by_name["Mira"]["voice_profile"], "Mira Character")
        self.assertEqual(by_name["Ren"]["voice_profile"], "Ren Character")
        self.assertTrue(by_name["Ren"]["legacy_voice_cast"])

    def test_character_studio_assignment_and_matching_legacy_assignment_do_not_duplicate_or_conflict(self):
        rows, issues = self.bridge._effective_generation_character_rows(
            {
                "characters": [{"name": "Mira", "series": "Series One", "voice_profile": "Mira Character"}],
                "voice_cast": {"Mira": "Mira Character"},
            },
            "Series One",
            available_profiles=self.profiles,
        )
        self.assertEqual(issues, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["voice_profile"], "Mira Character")

    def test_conflicting_legacy_assignment_is_reported_and_strict_generation_rejects_it(self):
        state = {
            "characters": [{"name": "Mira", "series": "Series One", "voice_profile": "Mira Character"}],
            "voice_cast": {"Mira": "Ren Character"},
        }
        rows, issues = self.bridge._effective_generation_character_rows(
            state, "Series One", available_profiles=self.profiles, strict=False
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(issues), 1)
        with self.assertRaisesRegex(ValueError, "conflicting Character Studio"):
            self.bridge._effective_generation_character_rows(
                state, "Series One", available_profiles=self.profiles, strict=True
            )

    def test_same_character_name_in_multiple_series_is_never_mapped_by_first_match(self):
        state = {
            "characters": [
                {"name": "Mira", "series": "Series One"},
                {"name": "Mira", "series": "Series Two"},
            ],
            "voice_cast": {"Mira": "Mira Character"},
        }
        rows, issues = self.bridge._effective_generation_character_rows(
            state, "Series One", available_profiles=self.profiles, strict=False
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(issues), 1)
        self.assertTrue(all(not row.get("voice_profile") for row in rows))
        with self.assertRaisesRegex(ValueError, "multiple characters"):
            self.bridge._effective_generation_character_rows(
                state, "Series One", available_profiles=self.profiles, strict=True
            )

    def test_explicit_series_on_legacy_cast_dict_resolves_same_name_safely(self):
        profiles = [SimpleNamespace(name="Mira One", voice_id="m1"), SimpleNamespace(name="Mira Two", voice_id="m2")]
        rows, issues = self.bridge._effective_generation_character_rows(
            {
                "characters": [
                    {"name": "Mira", "series": "Series One"},
                    {"name": "Mira", "series": "Series Two"},
                ],
                "voice_cast": {"Mira": {"profile_name": "Mira Two", "series": "Series Two"}},
            },
            "Series One",
            available_profiles=profiles,
        )
        self.assertEqual(issues, [])
        self.assertEqual(rows[0].get("voice_profile", ""), "")
        self.assertEqual(rows[1]["voice_profile"], "Mira Two")


if __name__ == "__main__":
    unittest.main()
