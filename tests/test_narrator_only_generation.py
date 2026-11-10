from __future__ import annotations

import unittest
from pathlib import Path
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
        self._now = Mock(return_value="2026-11-09T01:20:00+00:00")

    def _effective_generation_character_rows(self, state, default_series, **kwargs):
        return host.PremiumV2Bridge._effective_generation_character_rows(
            self, state, default_series, available_profiles=self._saved_profiles, **kwargs
        )


class NarratorOnlyGenerationTests(unittest.TestCase):
    def test_zero_profiles_auto_enable_narrator_only_without_speaker_review(self):
        project = SimpleNamespace(title="Narrator-only book")
        state = {"characters": []}
        harness = NarratorResolverHarness(SimpleNamespace(name="Saved Narrator"))
        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            side_effect=AssertionError("Automatic narrator-only mode must not demand speaker review"),
        ):
            profile, selection = harness._resolve_narrator_for_generation(
                project, state,
                [Chapter(1, "Opening", '“Hello there,” she said.')],
            )
        self.assertEqual(profile.name, "Saved Narrator")
        self.assertTrue(selection["narrator_only"])
        self.assertEqual(selection["generation_mode"], "narrator_only")
        self.assertTrue(state["narrator_only_generation"])

    def test_cast_aware_default_allows_narration_only_text_without_speaker_review(self):
        project = SimpleNamespace(title="Cast-aware book")
        profile, selection = NarratorResolverHarness(
            SimpleNamespace(name="Saved Narrator")
        )._resolve_narrator_for_generation(
            project, {"characters": []}, [Chapter(1, "Opening", "The journey began.")],
        )
        self.assertEqual(profile.name, "Saved Narrator")
        self.assertTrue(selection["narrator_only"])
        self.assertEqual(selection["generation_mode"], "narrator_only")
        self.assertEqual(selection["dialogue_routing"], "narrator_for_all_passages")

    def test_saved_user_opt_out_keeps_cast_aware_speaker_review(self):
        project = SimpleNamespace(title="Narrator-only book")
        chapters = [Chapter(1, "Opening", '“Hello there,” she said.')]
        state = {
            "characters": [],
            "narrator_only_generation": False,
            "narrator_only_generation_user_opt_out": True,
        }
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
                NarratorResolverHarness(
                    SimpleNamespace(name="Saved Narrator")
                )._resolve_narrator_for_generation(project, state, chapters)

    def test_zero_profiles_with_226_unassigned_characters_still_auto_uses_narrator(self):
        project = SimpleNamespace(title="Narrator-only book")
        chapters = [Chapter(1, "Opening", '“Hello there,” she said.')]
        characters = [{"name": f"Candidate {n}", "voice_profile": ""} for n in range(226)]

        harness = NarratorResolverHarness(SimpleNamespace(name="Saved Narrator"))
        with patch(
            "app.chapters.speaker_segmentation.segment_chapter_speakers",
            side_effect=AssertionError("Unassigned character records are not voice profiles"),
        ):
            _profile, selection = harness._resolve_narrator_for_generation(
                project, {"characters": characters}, chapters
            )
        self.assertTrue(selection["narrator_only"])
        self.assertEqual(selection["character_voice_profile_count"], 0)

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
            with self.assertRaisesRegex(ValueError, "still need speaker review") as raised:
                harness._resolve_narrator_for_generation(
                    project, state, [Chapter(1, "Opening", "“Hello there,” she said.")]
                )

        self.assertIn("Narrator-Only Generation was switched off", str(raised.exception))
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

    def test_narrator_only_save_rejects_a_project_with_a_valid_character_voice_profile(self):
        narrator = SimpleNamespace(name="Saved Narrator")
        character_voice = SimpleNamespace(name="Mira Voice")
        project = SimpleNamespace(folder=Path.cwd())
        state = {
            "characters": [{"name": "Mira", "voice_profile": "Mira Voice"}],
            "narrator_only_generation": False,
        }
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _project_series_name=lambda _project, _state: "Test Series",
            _narrator_series_default_read=lambda _project, _state, _series: {
                "effective_profile_name": narrator.name,
                "profile_available": True,
            },
            _effective_generation_character_rows=lambda _state, _series, strict=False: (
                list(_state.get("characters") or []), []
            ),
            _now=lambda: "2026-11-09T01:20:00+00:00",
        )
        with (
            patch.object(host, "load_state", return_value=state),
            patch.object(host, "load_profiles", return_value=[narrator, character_voice]),
            patch.object(host, "save_state") as save_state,
        ):
            with self.assertRaisesRegex(ValueError, "zero configured character voice profiles"):
                host.PremiumV2Bridge._production_narrator_only_save(
                    bridge, {"enabled": True}
                )
        save_state.assert_not_called()
        self.assertFalse(state["narrator_only_generation"])

    def test_narrator_only_save_ignores_stale_character_profile_references(self):
        narrator = SimpleNamespace(name="Saved Narrator")
        project = SimpleNamespace(folder=__import__("pathlib").Path.cwd())
        state = {
            "characters": [{"name": "Mira", "voice_profile": "Deleted Voice Profile"}],
            "narrator_only_generation": False,
        }
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _project_series_name=lambda _project, _state: "Test Series",
            _narrator_series_default_read=lambda _project, _state, _series: {
                "effective_profile_name": narrator.name,
                "profile_available": True,
            },
            _effective_generation_character_rows=lambda _state, _series, strict=False: (
                list(_state.get("characters") or []), ["stale profile reference"]
            ),
            _now=lambda: "2026-11-09T01:20:00+00:00",
        )
        with (
            patch.object(host, "load_state", return_value=state),
            patch.object(host, "load_profiles", return_value=[narrator]),
            patch.object(host, "save_state") as save_state,
        ):
            result = host.PremiumV2Bridge._production_narrator_only_save(
                bridge, {"enabled": True}
            )
        self.assertTrue(result["saved"])
        self.assertTrue(result["enabled"])
        self.assertTrue(state["narrator_only_generation"])
        save_state.assert_called_once()

    def test_production_readiness_explains_zero_profile_narrator_only_mode(self):
        adapter = (
            Path(__file__).resolve().parents[1]
            / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "0 configured character voice profiles · character voice assignment not required; saved narrator reads all passages",
            adapter,
        )
        self.assertIn(
            "Automatically use the saved narrator for every passage, including dialogue, when this book has zero configured character voice profiles and an available narrator.",
            adapter,
        )
        self.assertIn(
            "adding a character voice profile returns production to multi-character routing.",
            adapter,
        )
        self.assertIn(
            "const narratorOnly = narratorOnlyRequested && configuredCharacterVoiceCount === 0",
            adapter,
        )
        self.assertIn(
            "if (narratorOnly && configuredCharacterVoiceCount > 0)",
            adapter,
        )
        self.assertIn(
            "Turn it off to use multi-character speaker review.",
            adapter,
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


    def test_narrator_only_control_is_a_switch_with_hover_help_and_truthful_eligibility(self):
        adapter = (
            Path(__file__).resolve().parents[1]
            / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("const row = document.createElement('div');", adapter.index("if (!narratorOnlyControl)"))
        end = adapter.index("row.append(input,copy);", start) + len("row.append(input,copy);")
        control = adapter[start:end]
        self.assertIn("input.className = 'ryu-switch-input'", control)
        self.assertIn("input.setAttribute('role','switch')", control)
        self.assertIn("input.disabled = project?.narrator_only_eligible !== true", control)
        self.assertIn("infoWrap.className = 'ryu-info-wrap'", control)
        self.assertIn("info.className = 'ryu-info-trigger'", control)
        self.assertIn("tooltip.className = 'ryu-info-tooltip'", control)
        self.assertIn("voiceCount > 0", control)
        self.assertIn("configured character voice profile(s) found", control)
        self.assertIn("save an available narrator profile first", control)

    def test_narrator_only_eligibility_requires_valid_narrator_and_zero_valid_cast_profiles(self):
        host_source = (
            Path(__file__).resolve().parents[1]
            / "app" / "ui" / "premium_v2_host.py"
        ).read_text(encoding="utf-8")
        summary_start = host_source.index("def _project_summary(")
        summary_end = host_source.index("\n    def ", summary_start + 8)
        summary = host_source[summary_start:summary_end]
        self.assertIn("narrator_only_eligible = narrator_ready and configured_character_voice_profile_count == 0", summary)
        self.assertIn('"configured_character_voice_profile_count": configured_character_voice_profile_count', summary)
        save_start = host_source.index("def _production_narrator_only_save(")
        save_end = host_source.index("\n    def ", save_start + 8)
        save = host_source[save_start:save_end]
        self.assertIn("if enabled and not narrator_available:", save)
        self.assertIn("if enabled and configured_profiles:", save)
        self.assertIn("zero configured", save)

    def test_narrator_only_toggle_uses_live_project_identity_after_project_switch(self):
        adapter = (
            Path(__file__).resolve().parents[1]
            / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index(
            "input.addEventListener('change', () => {",
            adapter.index("input.id = 'narratorOnlyGeneration'"),
        )
        end = adapter.index("const copy = document.createElement('span');", start)
        handler = adapter[start:end]

        # The control is reused across project navigation. Its handler must not
        # retain the project object from the render that originally created it.
        self.assertIn("window.ryuPremiumActiveProject", handler)
        self.assertIn("call('project.get_active'", handler)
        self.assertIn("expected_project_folder:String(active.folder || '')", handler)
        self.assertNotIn("project?.folder", handler)


if __name__ == "__main__":
    unittest.main()
