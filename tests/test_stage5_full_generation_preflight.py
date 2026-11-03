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

    def __init__(self, project, profile, job_id="stage53-production-job") -> None:
        self.project = project
        self.profile = profile
        self.job_id = job_id
        self._assert_no_active_model_lifecycle = Mock()
        self._assert_no_active_audio_synthesis = Mock()
        self.close_preview_provider_cache = Mock()
        self._active_project = Mock(return_value=project)
        self._resolve_narrator_for_generation = Mock(
            return_value=(
                profile,
                {"source": "project_override", "profile_name": profile.name},
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
    def _run_production(self, root: Path, chapters: list[Chapter], payload=None):
        project_folder = root / "saved-project"
        project_folder.mkdir(parents=True, exist_ok=True)
        cover = root / "saved-cover.png"
        cover.write_bytes(b"PNG fixture")
        output = root / "output" / "saved-book.m4b"
        state = _complete_saved_state(project_folder, cover, output)
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
        bridge = ProductionGenerationHarness(project, profile)
        manager = Mock()

        with (
            patch.object(host, "load_state", return_value=state),
            patch.object(host, "save_state"),
            patch.object(host, "provider_from_profile", return_value=(object(), "saved-narrator-voice")),
            patch.object(host, "load_profiles", return_value=[]),
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
            self.assertIs(positional[0].profile, profile)
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
            self.assertEqual(state["empty_chapters_skipped"], 1)
            self.assertEqual(state["excluded_chapters_skipped"], 1)
            self.assertEqual(state["chapters_skipped_for_generation"], 2)
            manager.start.assert_called_once()
            self.assertEqual(manager.start.call_args.args[0], output)
            self.assertIsNone(state["output_path"])
            bridge._job_update.assert_called_once()

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
