"""Stage 5.3 Production-path tests for saved inputs and eligible chapter scope."""
from __future__ import annotations

import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
from app.ui import premium_v2_host as host


class ProductionGenerationHarness:
    """Call the actual Premium V2 production handler without constructing a Qt window."""

    _production_generate_book = host.PremiumV2Bridge._production_generate_book
    _effective_generation_character_rows = host.PremiumV2Bridge._effective_generation_character_rows
    _character_series_for_voice_assignment = staticmethod(
        host.PremiumV2Bridge._character_series_for_voice_assignment
    )

    def __init__(self, project, profile, job_id="stage53-production-job", narrator_only=False) -> None:
        self.project = project
        self.profile = profile
        self.job_id = job_id
        self._assert_no_active_model_lifecycle = Mock()
        self._assert_no_active_audio_synthesis = Mock()
        self.close_preview_provider_cache = Mock()
        self._active_project = Mock(return_value=project)
        self.narrator_only = narrator_only
        self.unassigned_profile = SimpleNamespace(
            name="Global Unassigned Character", provider="piper", voice_id="unassigned-character"
        )
        self._resolve_narrator_for_generation = Mock(
            return_value=(
                profile,
                {
                    "source": "project_override",
                    "profile_name": profile.name,
                    "generation_mode": "narrator_only" if narrator_only else "character_cast",
                    "narrator_only": narrator_only,
                    # Narrator-only mode is eligible only when no valid
                    # character voice profiles are configured for this book.
                    "character_voice_profile_count": 0,
                    "effective_character_rows": [],
                    "unassigned_character_profile_name": self.unassigned_profile.name,
                    "unassigned_character_profile_required": not narrator_only,
                },
            )
        )
        self._project_series_name = Mock(return_value="Saved Series")
        self._new_job = Mock(return_value=job_id)
        self._now = Mock(return_value="2026-11-03T14:00:00+00:00")
        self._generation_progress = Mock()
        self._generation_finished = Mock()
        self._job_update = Mock()
        self._jobs_lock = threading.RLock()
        self._generators = {}
        self.settings = SimpleNamespace(value=lambda _key, default=None: default)


def _complete_saved_state(project_folder: Path, cover: Path, output: Path) -> dict:
    return {
        "author": "Saved Author",
        "publisher": "Saved Publisher",
        "series": "Saved Series",
        "series_volume": "2",
        "language": "en-GB",
        "year": "2026",
        "genre": "Fantasy",
        "cover_path": str(cover),
        "output_path": str(output),
        "audio_bitrate": 192,
        "narration_speed": 0.97,
        "pacing_profile": "relaxed",
        "pronunciation_enabled": True,
        "background_audio_mode": "off",
        "background_audio_enabled": False,
        "chapter_bgm_strategy": "same",
        "chapter_bgm_overrides": {},
        "characters": [],
    }


class Stage53ProductionPreflightTests(unittest.TestCase):
    def _run_production(self, root: Path, chapters: list[Chapter], payload=None, *, narrator_only=False):
        project_folder = root / "saved-project"
        project_folder.mkdir(parents=True, exist_ok=True)
        cover = root / "saved-cover.png"
        cover.write_bytes(b"PNG fixture")
        output = root / "output" / "saved-book.m4b"
        state = _complete_saved_state(project_folder, cover, output)
        state["narrator_only_generation"] = narrator_only
        project = SimpleNamespace(
            folder=project_folder,
            title="Saved Book",
            chapters=chapters,
        )
        # This saved profile is authoritative. A transient UI selection in the
        # request payload must not replace it.
        profile = SimpleNamespace(
            name="Saved Narrator Profile",
            voice_id="saved-narrator-voice",
            provider="piper",
        )
        bridge = ProductionGenerationHarness(project, profile, narrator_only=narrator_only)
        manager = Mock()

        with (
            patch.object(host, "load_state", return_value=state),
            patch.object(host, "save_state"),
            patch.object(host, "provider_from_profile", return_value=(object(), "saved-narrator-voice")),
            patch.object(host, "load_profiles", return_value=[bridge.unassigned_profile]),
            patch.object(host, "_effective_pronunciation_dictionary", return_value=[
                {"written_form": "Mira", "spoken_form": "Mee-rah", "enabled": True}
            ]),
            patch.object(host, "GenerationManager", return_value=manager) as manager_factory,
            patch("app.audio.library.effective_background_audio_mode", return_value="off"),
            patch("app.audio.library.validate_saved_audio_paths"),
        ):
            result = bridge._production_generate_book(dict(payload or {}, output_path=str(output)))

        return bridge, manager, manager_factory, result, state, output, profile

    def test_mixed_project_passes_only_nonempty_nonexcluded_chapters_in_saved_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapters = [
                Chapter(1, "Opening", "The story begins."),
                Chapter(2, "Empty chapter", "  \n\t"),
                Chapter(3, "Excluded appendix", "This saved chapter is explicitly excluded.", skip_for_generation=True),
                Chapter(4, "Final chapter", "The story concludes."),
            ]

            bridge, manager, manager_factory, result, state, output, profile = self._run_production(
                root,
                chapters,
                payload={"profile_name": "Transient UI Voice"},
            )

            self.assertEqual(bridge._new_job.call_args.args[0], "audiobook-generation")
            self.assertEqual(result["state"], "running")
            self.assertEqual(result["chapter_count"], 2)
            self.assertEqual(result["empty_chapters_skipped"], 1)
            self.assertEqual(result["excluded_chapters_skipped"], 1)
            self.assertEqual(result["chapters_skipped_for_generation"], 2)

            positional = manager_factory.call_args.args
            selected_chapters = positional[2]
            self.assertEqual([chapter.number for chapter in selected_chapters], [1, 4])
            self.assertIs(selected_chapters[0], chapters[0])
            self.assertIs(selected_chapters[1], chapters[3])

            # The saved narrator/profile and metadata win over any transient
            # profile supplied by the frontend.
            self.assertEqual(positional[1], "saved-narrator-voice")
            self.assertIs(positional[0].narrator_provider.profile, profile)
            kwargs = manager_factory.call_args.kwargs
            self.assertEqual(kwargs["bitrate"], 192)
            self.assertEqual(kwargs["narration_speed"], 0.97)
            self.assertEqual(kwargs["pacing_profile"], "relaxed")
            self.assertEqual(
                kwargs["pronunciation_dictionary"],
                [{"written_form": "Mira", "spoken_form": "Mee-rah", "enabled": True}],
            )
            self.assertEqual(kwargs["metadata"]["author"], "Saved Author")
            self.assertEqual(kwargs["metadata"]["narrator"], "Saved Narrator Profile")
            self.assertEqual(kwargs["metadata"]["series_number"], "2")
            self.assertEqual(kwargs["background_audio_mode"], "off")

            self.assertEqual(state["status"], "generating")
            self.assertEqual(state["generation_job_id"], "stage53-production-job")
            self.assertFalse(state["narrator_only_generation"])
            self.assertEqual(state["generation_mode"], "character_cast")
            job_result = bridge._job_update.call_args.kwargs["result"]
            self.assertFalse(job_result["narrator_only"])
            self.assertEqual(job_result["generation_mode"], "character_cast")
            self.assertFalse(result["narrator_only"])
            self.assertEqual(result["generation_mode"], "character_cast")
            self.assertEqual(state["empty_chapters_skipped"], 1)
            self.assertEqual(state["excluded_chapters_skipped"], 1)
            self.assertEqual(state["chapters_skipped_for_generation"], 2)
            manager.start.assert_called_once()
            self.assertEqual(manager.start.call_args.args[0].resolve(), output.resolve())
            self.assertIsNone(state["output_path"])
            bridge._job_update.assert_called_once()

    def test_narrator_only_full_generation_bypasses_all_character_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapters = [Chapter(1, "Opening", "Mira said, “Hello.”")]
            bridge, manager, manager_factory, result, state, output, profile = self._run_production(
                root,
                chapters,
                narrator_only=True,
            )

            positional = manager_factory.call_args.args
            self.assertIs(positional[0].profile, profile)
            self.assertEqual(positional[1], profile.voice_id)
            self.assertNotEqual(positional[0].__class__.__name__, "CastAwareProvider")
            self.assertTrue(state["narrator_only_generation"])
            self.assertEqual(state["generation_mode"], "narrator_only")
            self.assertEqual(state["character_voice_profile_count"], 0)
            job_result = bridge._job_update.call_args.kwargs["result"]
            self.assertTrue(job_result["narrator_only"])
            self.assertEqual(job_result["generation_mode"], "narrator_only")
            self.assertEqual(job_result["character_voice_profile_count"], 0)
            self.assertTrue(result["narrator_only"])
            self.assertEqual(result["generation_mode"], "narrator_only")
            self.assertEqual(result["character_voice_profile_count"], 0)
            bridge._resolve_narrator_for_generation.assert_called_once()

    def _run_terminal_callback(self, root: Path, *, narrator_only: bool, failed: bool = False,
                               superseded: bool = False):
        project_folder = root / "saved-project"
        project_folder.mkdir(parents=True, exist_ok=True)
        output = root / "saved-book.m4b"
        output.write_bytes(b"validated M4B fixture")
        job_id = "terminal-generation-job"
        state = {
            "generation_job_id": "newer-generation-job" if superseded else job_id,
            # A newer project owner may have a different mode. The callback
            # must keep the original job's immutable mode from its job record.
            "narrator_only_generation": False if superseded else narrator_only,
            "generation_mode": "character_cast" if superseded or not narrator_only else "narrator_only",
            "character_voice_profile_count": 0 if superseded else 2,
            "empty_chapters_skipped": 1,
            "excluded_chapters_skipped": 1,
            "chapters_skipped_for_generation": 2,
        }
        start_result = {
            "output_path": str(output),
            "chapter_count": 2,
            "generation_mode": "narrator_only" if narrator_only else "character_cast",
            "narrator_only": narrator_only,
            "character_voice_profile_count": 2,
        }
        summary = SimpleNamespace(
            output_path=str(output),
            cancelled=False,
            packaging_failed=failed,
            chapters_failed=[2] if failed else [],
            chapters_completed=1 if failed else 2,
            chapters_total=2,
            chapters_completed_numbers=[1] if failed else [1, 2],
            packaging_error="Fixture packaging failure" if failed else "",
            failure_details={},
        )
        bridge = SimpleNamespace(
            _jobs_lock=threading.RLock(),
            _jobs={job_id: {"progress": 96, "result": start_result}},
            _generators={job_id: object()},
            _job_update=Mock(),
            _now=Mock(return_value="2026-11-08T19:00:00+00:00"),
        )
        with (
            patch.object(host, "load_state", return_value=state),
            patch.object(host, "save_state"),
            patch.object(host, "is_iso_bmff_file", return_value=False),
        ):
            host.PremiumV2Bridge._generation_finished(
                bridge, job_id, SimpleNamespace(folder=project_folder),
                summary, output, "Saved Narrator Profile",
            )
        return bridge, state, summary

    def test_terminal_success_retains_narrator_only_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge, state, _summary = self._run_terminal_callback(
                Path(temporary), narrator_only=True,
            )
            result = bridge._job_update.call_args.kwargs["result"]
            self.assertEqual(result["generation_mode"], "narrator_only")
            self.assertIs(result["narrator_only"], True)
            self.assertEqual(result["character_voice_profile_count"], 2)
            self.assertEqual(state["generation_mode"], "narrator_only")
            self.assertIs(state["narrator_only_generation"], True)
            self.assertEqual(result["chapters_completed"], 2)

    def test_terminal_failure_retains_character_cast_identity_and_chapter_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge, state, _summary = self._run_terminal_callback(
                Path(temporary), narrator_only=False, failed=True,
            )
            changes = bridge._job_update.call_args.kwargs
            result = changes["result"]
            self.assertEqual(changes["state"], "failed")
            self.assertEqual(result["generation_mode"], "character_cast")
            self.assertIs(result["narrator_only"], False)
            self.assertEqual(result["character_voice_profile_count"], 2)
            self.assertEqual(result["chapters_completed"], 1)
            self.assertEqual(result["chapters_failed"], [2])
            self.assertEqual(state["generation_mode"], "character_cast")

    def test_superseded_callback_uses_its_own_job_mode_not_new_project_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bridge, state, _summary = self._run_terminal_callback(
                Path(temporary), narrator_only=True, superseded=True,
            )
            result = bridge._job_update.call_args.kwargs["result"]
            self.assertIs(result["superseded"], True)
            self.assertEqual(result["superseded_by_job_id"], "newer-generation-job")
            self.assertEqual(result["generation_mode"], "narrator_only")
            self.assertIs(result["narrator_only"], True)
            self.assertEqual(result["character_voice_profile_count"], 2)
            self.assertIs(state["narrator_only_generation"], False)

    def test_all_empty_or_all_excluded_projects_are_rejected_before_job_creation(self) -> None:
        scenarios = (
            (
                "all empty",
                [Chapter(1, "Opening", ""), Chapter(2, "Ending", "  \n ")],
            ),
            (
                "all excluded",
                [
                    Chapter(1, "Opening", "Saved but excluded.", skip_for_generation=True),
                    Chapter(2, "Ending", "Also excluded.", skip_for_generation=True),
                ],
            ),
            ("no chapters", []),
        )
        for label, chapters in scenarios:
            with self.subTest(scenario=label), tempfile.TemporaryDirectory() as temporary:
                project = SimpleNamespace(
                    folder=Path(temporary) / "saved-project",
                    title="No Eligible Book",
                    chapters=chapters,
                )
                bridge = ProductionGenerationHarness(
                    project,
                    SimpleNamespace(name="Saved Narrator Profile"),
                )
                bridge._new_job = Mock(side_effect=AssertionError("No job should be created"))
                with patch.object(host, "GenerationManager") as manager_factory:
                    with self.assertRaisesRegex(
                        ValueError,
                        "No chapters are eligible for generation",
                    ):
                        bridge._production_generate_book({})
                manager_factory.assert_not_called()
                bridge._new_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class GenerationProgressDispatchHarness:
    _generation_progress = host.PremiumV2Bridge._generation_progress

    def __init__(self):
        self._job_update = Mock()


class Stage53GenerationProgressDispatchTests(unittest.TestCase):
    def test_generation_progress_maps_plan_chunks_and_m4b_stages_monotonically(self):
        bridge = GenerationProgressDispatchHarness()
        events = (
            ((0, 2, 0, "plan:4:0:4"), "Preparing generation plan", 0),
            ((1, 2, 0, "chunk-start:1/4"), "Loading voice model", 0),
            ((1, 2, 1, "chunk:1/2:1/4"), "Rendering narration chunks", 25),
            ((2, 2, 4, "m4b-packaging"), "Assembling final M4B", 100),
            ((2, 2, 4, "m4b-package:2/4:Encoding final chapters"), "Encoding and validating final M4B", 100),
            ((2, 2, 4, "m4b-complete"), "Audiobook duration measured · M4B ready", 100),
        )
        observed = []
        for args, expected_stage, expected_progress in events:
            bridge._generation_progress("progress-job", *args)
            changes = bridge._job_update.call_args.kwargs
            self.assertEqual(changes["state"], "running")
            self.assertEqual(changes["stage"], expected_stage)
            self.assertEqual(changes["progress"], expected_progress)
            self.assertEqual(changes["current_chapter"], args[0])
            self.assertEqual(changes["chapters_total"], args[1])
            if args[3] == "m4b-packaging":
                self.assertEqual(changes["packaging_progress_percent"], 0)
            elif args[3].startswith("m4b-package:"):
                self.assertEqual(changes["packaging_progress_percent"], 50)
                self.assertEqual(changes["packaging_completed_steps"], 2)
                self.assertEqual(changes["packaging_total_steps"], 4)
            observed.append(changes["progress"])

        self.assertEqual(observed, sorted(observed))
        self.assertEqual(observed[-1], 100)

    def test_paused_generation_progress_keeps_last_saved_progress_percentage(self):
        bridge = GenerationProgressDispatchHarness()
        bridge._generation_progress("progress-job", 2, 5, 8, "chunk:2/5:8/12")
        before = dict(bridge._job_update.call_args.kwargs)
        bridge._generation_progress(
            "progress-job", 2, 5, 0,
            "paused:Generation paused at a saved chunk/batch checkpoint. Resume to continue.",
        )
        paused = bridge._job_update.call_args.kwargs
        self.assertEqual(paused["state"], "paused")
        self.assertEqual(paused["stage"], "Paused at chapter checkpoint")
        self.assertNotIn("progress", paused)
        self.assertIn("saved chunk/batch checkpoint", paused["message"])
        self.assertGreater(before["progress"], 0)
