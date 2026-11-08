import unittest
from pathlib import Path

from app.chapters.characters import (
    is_likely_character_name, character_detection_exclusion_keys,
    is_user_confirmed_character_record,
)
from app.tts.pronunciation_suggester import (
    is_common_english_phrase, is_likely_character_name_candidate,
)


class CharacterNameQualityTests(unittest.TestCase):
    def test_common_capitalized_prose_and_description_phrases_are_not_cast_members(self):
        for value in (
            "SILVER HAIRED", "Silver-Haired", "Letting", "Hearing Tobio's",
            "Astonished Tobio", "The School",
        ):
            with self.subTest(value=value):
                self.assertFalse(is_likely_character_name(value))

    def test_valid_names_and_explicit_user_or_speaker_evidence_are_preserved(self):
        self.assertTrue(is_likely_character_name("Ikuse Tobio"))
        self.assertTrue(is_likely_character_name("Tobio"))
        self.assertTrue(is_likely_character_name("Ono Anna"))
        self.assertFalse(is_likely_character_name("Hearing", explicit=True))
        self.assertFalse(is_likely_character_name("Silver-Haired", explicit=True))
        self.assertFalse(is_likely_character_name("Astonished Tobio", explicit=True))
        self.assertFalse(is_likely_character_name("Silver-Haired", trusted=True))
        self.assertTrue(is_likely_character_name("Will Smith", explicit=True))
        self.assertTrue(is_likely_character_name("Captain Mira", explicit=True))


    def test_persisted_detection_exclusions_are_series_scoped_and_assignment_can_restore(self):
        exclusions = [
            {"name": "Silver-Haired", "aliases": ["The Silver Knight"], "series": "Series A"},
            {"name": "The School", "aliases": [], "series": "Series B"},
            {"name": "Mira", "aliases": ["Miri"], "series": "Series A"},
        ]
        excluded = character_detection_exclusion_keys(exclusions, "Series A")
        self.assertEqual(excluded, {"silver-haired", "the silver knight", "mira", "miri"})
        self.assertEqual(character_detection_exclusion_keys(exclusions, "Series B"), {"the school"})
        # A saved manual dialogue assignment is stronger evidence than a prior
        # dismissal and deliberately makes that identity eligible again.
        restored = character_detection_exclusion_keys(exclusions, "Series A", protected_names={"Miri"})
        self.assertEqual(restored, {"silver-haired", "the silver knight", "mira"})
        other_series_assignment = character_detection_exclusion_keys(
            exclusions, "Series A", protected_names=[{"name": "Mira", "series": "Series B"}]
        )
        self.assertEqual(other_series_assignment, excluded)

    def test_detection_exclusions_reject_malformed_entries_and_do_not_cross_series(self):
        exclusions = [
            None,
            {"name": "", "series": "Series A"},
            {"name": "Tobio", "series": "Series A"},
            {"name": "Ren", "series": "Series B"},
            {"name": "Mira", "series": ""},
        ]
        self.assertEqual(character_detection_exclusion_keys(exclusions, "Series A"), {"tobio"})
    def test_ordinary_english_words_never_become_ai_characters_or_pronunciation_names(self):
        for value in ("Oh", "The", "Any", "Ah", "Uh", "Hmm", "Wait", "Okay", "Fine", "Please", "Actually"):
            with self.subTest(value=value):
                self.assertFalse(is_likely_character_name(value, explicit=True))
                self.assertFalse(is_likely_character_name(value, trusted=True))
                self.assertTrue(is_common_english_phrase(value))
                self.assertFalse(is_likely_character_name_candidate(value))
        self.assertFalse(is_likely_character_name("Any Other", explicit=True))
        self.assertFalse(is_likely_character_name_candidate("Oh 美咲"))
        self.assertFalse(is_likely_character_name_candidate("The 学生"))
        self.assertTrue(is_likely_character_name_candidate("美咲"))
        self.assertTrue(is_likely_character_name("Will Smith", explicit=True))
        self.assertTrue(is_likely_character_name("Hope", trusted=True))
        self.assertTrue(is_likely_character_name_candidate("Hyoudou Issei"))

    def test_saved_false_detection_aliases_are_removed_during_cast_merge(self):
        from app.chapters.characters import Character, merge_character_analysis_record

        merged = merge_character_analysis_record(
            Character(
                name="Mira",
                role="Possible Character",
                aliases=["Ren", "Oh", "The", "Any"],
            ),
            {
                "name": "Mira",
                "aliases": ["Miri", "Actually", "Hmm", "Tobio"],
                "voice_profile": "Voice A",
            },
        )
        self.assertEqual(set(merged["aliases"]), {"Ren", "Miri", "Tobio"})

    def test_ai_aliases_are_not_promoted_to_trusted_and_assignment_restores_are_series_scoped(self):
        host_source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("explicit=str(alias).strip().casefold() in explicit_names", host_source)
        self.assertIn("assignment_series.casefold() != series_name.casefold()", host_source)
        self.assertIn("Cannot delete/dismiss", host_source)


    def test_generated_series_scope_is_not_user_confirmation(self):
        self.assertFalse(is_user_confirmed_character_record({
            "name": "Magic", "series": "Series A", "scope": "Series · Series A",
        }))
        self.assertTrue(is_user_confirmed_character_record({"name": "Magic", "user_created": True}))
        self.assertTrue(is_user_confirmed_character_record({"name": "Mira", "manual_aliases": True}))

    def test_character_studio_read_cleans_legacy_false_names_and_aliases(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from app.ui.premium_v2_host import PremiumV2Bridge

        project = SimpleNamespace(folder=Path("test-character-cleanup"), chapters=[])
        state = {
            "series_name": "Series A",
            "characters": [
                {"name": "Mira", "series": "Series A", "scope": "Series · Series A",
                 "voice_profile": "Saved Voice", "aliases": ["Captain Mira", "Oh", "The", "Any"]},
                {"name": "Magic", "series": "Series A", "scope": "Series · Series A", "aliases": []},
                {"name": "Any", "series": "Series A", "scope": "Series · Series A", "aliases": []},
                {"name": "Hope", "series": "Series A", "user_created": True, "aliases": []},
            ],
        }
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _project_series_name=lambda _project, _state: "Series A",
            _now=lambda: "2026-11-08T00:00:00",
        )
        with (
            patch("app.ui.premium_v2_host.load_state", return_value=state),
            patch("app.ui.premium_v2_host.save_state") as save,
            patch("app.ui.premium_v2_host.prune_invalid_character_records"),
        ):
            rows = PremiumV2Bridge._character_list(bridge, {})

        self.assertEqual({row["name"] for row in rows}, {"Mira", "Hope"})
        mira = next(row for row in rows if row["name"] == "Mira")
        self.assertEqual(mira["aliases"], ["Captain Mira"])
        save.assert_called_once()

if __name__ == "__main__":
    unittest.main()
