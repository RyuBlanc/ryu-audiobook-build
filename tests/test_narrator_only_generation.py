from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
from app.ui import premium_v2_host as host


class NarratorResolverHarness:
    _resolve_narrator_for_generation = host.PremiumV2Bridge._resolve_narrator_for_generation

    def __init__(self, profile):
        self._project_series_name = Mock(return_value="Test Series")
        self._narrator_series_default_read = Mock(return_value={
            "effective_profile_name": "Saved Narrator",
            "profile_name": "Saved Narrator",
            "source": "project_override",
            "profile_available": True,
        })
        self._find_profile = Mock(return_value=profile)


class NarratorOnlyGenerationTests(unittest.TestCase):
    def test_no_character_profiles_allows_unassigned_dialogue_with_saved_narrator(self):
        project = SimpleNamespace(title="Narrator-only book")
        chapters = [Chapter(1, "Opening", '“Hello there,” she said.')]

        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            side_effect=AssertionError("Narrator-only mode must not demand character review"),
        ):
            profile, selection = NarratorResolverHarness(
                SimpleNamespace(name="Saved Narrator")
            )._resolve_narrator_for_generation(project, {"characters": []}, chapters)

        self.assertEqual(profile.name, "Saved Narrator")
        self.assertEqual(selection["generation_mode"], "narrator_only")
        self.assertTrue(selection["narrator_only"])
        self.assertEqual(selection["character_voice_profile_count"], 0)
        self.assertEqual(selection["dialogue_routing"], "narrator_for_all_passages")

    def test_zero_profiles_with_226_unassigned_characters_is_narrator_only(self):
        project = SimpleNamespace(title="Narrator-only book")
        chapters = [Chapter(1, "Opening", '“Hello there,” she said.')]
        characters = [{"name": f"Candidate {n}", "voice_profile": ""} for n in range(226)]

        profile, selection = NarratorResolverHarness(
            SimpleNamespace(name="Saved Narrator")
        )._resolve_narrator_for_generation(project, {"characters": characters}, chapters)

        self.assertEqual(profile.name, "Saved Narrator")
        self.assertTrue(selection["narrator_only"])
        self.assertEqual(selection["character_voice_profile_count"], 0)

    def test_configured_character_profile_keeps_unresolved_dialogue_gate(self):
        project = SimpleNamespace(title="Cast book")
        chapters = [Chapter(1, "Opening", '“Hello there,” she said.')]
        characters = [{"name": "Mira", "voice_profile": "Mira Voice"}]
        unresolved = SimpleNamespace(
            needs_review=True, kind="needs_speaker_review",
            text="“Hello there,”", chapter_number=1,
        )

        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            return_value=[unresolved],
        ):
            with self.assertRaisesRegex(ValueError, "still need speaker review"):
                NarratorResolverHarness(
                    SimpleNamespace(name="Saved Narrator")
                )._resolve_narrator_for_generation(
                    project, {"characters": characters}, chapters
                )

    def test_narrator_is_still_required_in_narrator_only_mode(self):
        project = SimpleNamespace(title="Narrator-only book")
        harness = NarratorResolverHarness(None)
        harness._narrator_series_default_read.return_value = {
            "effective_profile_name": "",
            "profile_name": "",
            "source": "none",
            "profile_available": False,
        }
        with self.assertRaisesRegex(ValueError, "no narrator voice"):
            harness._resolve_narrator_for_generation(
                project, {"characters": []}, [Chapter(1, "One", "Text")]
            )


if __name__ == "__main__":
    unittest.main()
