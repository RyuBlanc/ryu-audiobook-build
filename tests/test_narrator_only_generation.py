from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
from app.ui import premium_v2_host as host


class NarratorResolverHarness:
    _character_series_for_voice_assignment = staticmethod(
        host.PremiumV2Bridge._character_series_for_voice_assignment
    )

    def _resolve_narrator_for_generation(self, project, state, chapters):
        # Keep the test profile catalogue consistent with the resolver's
        # independent profile lookup and the effective-cast normalization.
        with patch(
            "app.ui.premium_v2_host.load_profiles",
            return_value=list(self._saved_profiles),
        ):
            return host.PremiumV2Bridge._resolve_narrator_for_generation(
                self, project, state, chapters
            )

    def __init__(self, profile):
        self._project_series_name = Mock(return_value="Test Series")
        self._narrator_series_default_read = Mock(return_value={
            "effective_profile_name": "Saved Narrator",
            "profile_name": "Saved Narrator",
            "source": "project_override",
            "profile_available": True,
        })
        self._find_profile = Mock(return_value=profile)
        self._saved_profiles = [profile] if profile is not None else []

    def _effective_generation_character_rows(self, state, default_series, **kwargs):
        return host.PremiumV2Bridge._effective_generation_character_rows(
            self, state, default_series, available_profiles=self._saved_profiles, **kwargs
        )


class NarratorOnlyGenerationTests(unittest.TestCase):
    def test_narrator_only_is_off_by_default_and_cast_review_remains_required(self):
        project = SimpleNamespace(title="Cast-aware book")
        harness = NarratorResolverHarness(SimpleNamespace(name="Saved Narrator"))
        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            return_value=[SimpleNamespace(
                needs_review=True,
                kind="needs_speaker_review",
                text="“Hello there,”",
                chapter_number=1,
            )],
        ):
            with self.assertRaisesRegex(ValueError, "still need speaker review"):
                harness._resolve_narrator_for_generation(
                    project, {"characters": []},
                    [Chapter(1, "Opening", '“Hello there,” she said.')],
                )

    def test_cast_aware_default_allows_narration_only_text_without_speaker_review(self):
        project = SimpleNamespace(title="Cast-aware book")
        profile, selection = NarratorResolverHarness(
            SimpleNamespace(name="Saved Narrator")
        )._resolve_narrator_for_generation(
            project, {"characters": []}, [Chapter(1, "Opening", "The journey began.")],
        )
        self.assertEqual(profile.name, "Saved Narrator")
        self.assertFalse(selection["narrator_only"])
        self.assertEqual(selection["generation_mode"], "character_cast")
        self.assertEqual(selection["dialogue_routing"], "saved_character_assignments")

    def test_narrator_only_is_explicit_book_opt_in_and_routes_all_passages(self):
        project = SimpleNamespace(title="Narrator-only book")
        chapters = [Chapter(1, "Opening", '“Hello there,” she said.')]
        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            side_effect=AssertionError("Narrator-only mode must not demand character review"),
        ):
            profile, selection = NarratorResolverHarness(
                SimpleNamespace(name="Saved Narrator")
            )._resolve_narrator_for_generation(
                project, {"characters": [], "narrator_only_generation": True}, chapters
            )
        self.assertEqual(profile.name, "Saved Narrator")
        self.assertTrue(selection["narrator_only"])
        self.assertEqual(selection["generation_mode"], "narrator_only")
        self.assertEqual(selection["dialogue_routing"], "narrator_for_all_passages")

    def test_zero_profiles_with_226_unassigned_characters_is_cast_aware_by_default(self):
        project = SimpleNamespace(title="Narrator-only book")
        chapters = [Chapter(1, "Opening", '“Hello there,” she said.')]
        characters = [{"name": f"Candidate {n}", "voice_profile": ""} for n in range(226)]

        harness = NarratorResolverHarness(SimpleNamespace(name="Saved Narrator"))
        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            return_value=[SimpleNamespace(
                needs_review=True,
                kind="needs_speaker_review",
                text="“Hello there,”",
                chapter_number=1,
            )],
        ):
            with self.assertRaisesRegex(ValueError, "still need speaker review"):
                harness._resolve_narrator_for_generation(project, {"characters": characters}, chapters)

    def test_character_profile_added_after_narrator_only_resets_mode_and_restores_speaker_review(self):
        project = SimpleNamespace(title="Narrator-only book")
        state = {
            "characters": [{"name": "Mira", "voice_profile": "Mira Voice"}],
            "narrator_only_generation": True,
        }
        harness = NarratorResolverHarness(SimpleNamespace(name="Saved Narrator"))
        harness._saved_profiles.append(SimpleNamespace(name="Mira Voice", voice_id="mira-voice"))
        unresolved = SimpleNamespace(
            needs_review=True,
            kind="needs_speaker_review",
            text="“Hello there,”",
            chapter_number=1,
        )
        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            return_value=[unresolved],
        ):
            with self.assertRaisesRegex(ValueError, "still need speaker review"):
                harness._resolve_narrator_for_generation(
                    project, state, [Chapter(1, "Opening", "“Hello there,” she said.")]
                )

        self.assertFalse(state["narrator_only_generation"])

    def test_narrator_only_ignores_unavailable_character_profile_references(self):
        project = SimpleNamespace(title="Narrator-only book")
        state = {
            "characters": [{"name": "Mira", "voice_profile": "Deleted Voice Profile"}],
            "narrator_only_generation": True,
        }
        harness = NarratorResolverHarness(SimpleNamespace(name="Saved Narrator"))
        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            side_effect=AssertionError("Narrator-only mode must not demand character review"),
        ):
            _profile, selection = harness._resolve_narrator_for_generation(
                project, state, [Chapter(1, "Opening", "“Hello there,” she said.")]
            )

        self.assertTrue(selection["narrator_only"])
        self.assertEqual(selection["character_voice_profile_count"], 0)
        self.assertEqual(selection["dialogue_routing"], "narrator_for_all_passages")
        self.assertTrue(state["narrator_only_generation"])

    def test_configured_character_profile_keeps_unresolved_dialogue_gate(self):
        project = SimpleNamespace(title="Cast book")
        chapters = [Chapter(1, "Opening", '“Hello there,” she said.')]
        characters = [{"name": "Mira", "voice_profile": "Mira Voice"}]
        unresolved = SimpleNamespace(
            needs_review=True, kind="needs_speaker_review",
            text="“Hello there,”", chapter_number=1,
        )

        harness = NarratorResolverHarness(SimpleNamespace(name="Saved Narrator"))
        harness._saved_profiles.append(SimpleNamespace(name="Mira Voice", voice_id="mira-voice"))
        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            return_value=[unresolved],
        ):
            with self.assertRaisesRegex(ValueError, "still need speaker review"):
                harness._resolve_narrator_for_generation(
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
