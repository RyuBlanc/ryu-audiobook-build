"""Stage 5.3 restart-recovery and durable job-state regression contracts."""
from __future__ import annotations

import json
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path

from app.core.state import load_state, save_state
from app.ui import premium_v2_host as host


class DurableJobRecoveryHarness:
    """Exercise the production durable-job loader without constructing a Qt window."""

    _load_durable_jobs = host.PremiumV2Bridge._load_durable_jobs
    _reconcile_interrupted_generation_project = host.PremiumV2Bridge._reconcile_interrupted_generation_project
    _terminal_job_state = staticmethod(host.PremiumV2Bridge._terminal_job_state)
    _persist_json_rows = host.PremiumV2Bridge._persist_json_rows
    _persist_jobs = host.PremiumV2Bridge._persist_jobs
    _persist_history = host.PremiumV2Bridge._persist_history
    _record_history_job = host.PremiumV2Bridge._record_history_job
    _now = staticmethod(host.PremiumV2Bridge._now)

    def __init__(self, jobs_path: Path, history_path: Path) -> None:
        self._jobs: dict[str, dict] = {}
        self._history: dict[str, dict] = {}
        self._jobs_lock = threading.RLock()
        self._jobs_path = lambda: jobs_path
        self._history_path = lambda: history_path


class Stage53DurableJobRecoveryTests(unittest.TestCase):
    def test_restart_marks_paused_and_running_generation_jobs_failed_and_recoverable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs_path = root / "premium_v2_jobs.json"
            history_path = root / "premium_v2_history.json"
            rows = []
            projects = {}
            expected_identity: dict[str, dict[str, object]] = {}

            for index, prior_status in enumerate(("paused", "running"), start=1):
                job_id = f"generation-job-{index}"
                generation_mode = "narrator_only" if index == 1 else "character_cast"
                narrator_only = generation_mode == "narrator_only"
                character_voice_profile_count = 0 if narrator_only else 3
                expected_identity[job_id] = {
                    "generation_mode": generation_mode,
                    "narrator_only": narrator_only,
                    "character_voice_profile_count": character_voice_profile_count,
                }
                project_folder = root / f"project-{index}"
                project_folder.mkdir()
                save_state(
                    project_folder,
                    {
                        "status": "generating",
                        "generation_job_id": job_id,
                        "output_path": None,
                        "completed_chapters": [1],
                        "generation_mode": generation_mode,
                        "narrator_only_generation": narrator_only,
                        "character_voice_profile_count": character_voice_profile_count,
                    },
                )
                projects[job_id] = project_folder
                rows.append(
                    {
                        "job_id": job_id,
                        "id": job_id,
                        "type": "audiobook-generation",
                        "title": f"Generate Book {index}",
                        "project_title": f"Book {index}",
                        "project_folder": str(project_folder),
                        "state": prior_status,
                        "progress": 40,
                        "stage": "Rendering narration chunks",
                        "message": "Worker was active before restart",
                        "retry_count": 0,
                        "recoverable": False,
                        "result": {
                            "generation_mode": generation_mode,
                            "narrator_only": narrator_only,
                            "character_voice_profile_count": character_voice_profile_count,
                        },
                    }
                )

            jobs_path.write_text(json.dumps(rows), encoding="utf-8")
            bridge = DurableJobRecoveryHarness(jobs_path, history_path)

            bridge._load_durable_jobs()

            persisted_rows = json.loads(jobs_path.read_text(encoding="utf-8"))
            persisted_by_id = {row["job_id"]: row for row in persisted_rows}
            self.assertEqual(set(bridge._jobs), set(projects))
            self.assertEqual(set(bridge._history), set(projects))

            for job_id, project_folder in projects.items():
                with self.subTest(job_id=job_id):
                    expected = expected_identity[job_id]
                    recovered = bridge._jobs[job_id]
                    self.assertEqual(recovered["state"], "failed")
                    self.assertEqual(recovered["stage"], "Interrupted by application restart")
                    self.assertTrue(recovered["recoverable"])
                    self.assertEqual(recovered["error"]["code"], "interrupted")
                    self.assertEqual(persisted_by_id[job_id]["state"], "failed")
                    self.assertEqual(bridge._history[job_id]["state"], "failed")
                    self.assertEqual(bridge._history[job_id]["job_id"], job_id)
                    for durable_row in (recovered, persisted_by_id[job_id], bridge._history[job_id]):
                        self.assertEqual(durable_row["result"]["generation_mode"], expected["generation_mode"])
                        self.assertIs(durable_row["result"]["narrator_only"], expected["narrator_only"])
                        self.assertEqual(
                            durable_row["result"]["character_voice_profile_count"],
                            expected["character_voice_profile_count"],
                        )

                    project_state = load_state(project_folder)
                    self.assertEqual(project_state["status"], "failed")
                    self.assertEqual(project_state["generation_job_id"], job_id)
                    self.assertTrue(project_state["generation_recovery_required"])
                    self.assertEqual(project_state["generation_mode"], expected["generation_mode"])
                    self.assertIs(project_state["narrator_only_generation"], expected["narrator_only"])
                    self.assertEqual(
                        project_state["character_voice_profile_count"],
                        expected["character_voice_profile_count"],
                    )

    def test_old_interrupted_job_cannot_overwrite_a_newer_project_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            jobs_path = root / "premium_v2_jobs.json"
            history_path = root / "premium_v2_history.json"
            project_folder = root / "project"
            project_folder.mkdir()
            save_state(
                project_folder,
                {
                    "status": "generating",
                    "generation_job_id": "new-generation-job",
                    "generation_started_at": "2026-11-03T12:00:00+00:00",
                },
            )
            jobs_path.write_text(
                json.dumps(
                    [
                        {
                            "job_id": "old-generation-job",
                            "id": "old-generation-job",
                            "type": "audiobook-generation",
                            "project_title": "Book",
                            "project_folder": str(project_folder),
                            "state": "paused",
                            "progress": 25,
                            "recoverable": False,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            bridge = DurableJobRecoveryHarness(jobs_path, history_path)

            bridge._load_durable_jobs()

            self.assertEqual(bridge._jobs["old-generation-job"]["state"], "failed")
            project_state = load_state(project_folder)
            self.assertEqual(project_state["status"], "generating")
            self.assertEqual(project_state["generation_job_id"], "new-generation-job")
            self.assertNotIn("generation_recovery_required", project_state)


if __name__ == "__main__":
    unittest.main()


class GenerationFinishOwnershipHarness:
    """Call the real completion callback without constructing the Qt application."""

    _generation_finished = host.PremiumV2Bridge._generation_finished
    _now = staticmethod(host.PremiumV2Bridge._now)

    def __init__(self, job_id: str) -> None:
        self._jobs_lock = threading.RLock()
        self._generators = {job_id: object()}
        self._job_update = Mock()


class Stage53StaleGenerationCallbackTests(unittest.TestCase):
    def test_late_success_cannot_overwrite_a_newer_project_generation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_folder = root / "project"
            project_folder.mkdir()
            old_output = root / "older-job.m4b"
            old_output.write_bytes(b"old-job-output" * 100)
            new_output = root / "newer-job.m4b"
            state = {
                "status": "generating",
                "generation_job_id": "newer-generation-job",
                "generation_target_path": str(new_output),
                "output_path": None,
                "completed_chapters": [],
            }
            bridge = GenerationFinishOwnershipHarness("older-generation-job")
            project = SimpleNamespace(folder=project_folder)
            summary = SimpleNamespace(
                output_path=old_output,
                cancelled=False,
                packaging_failed=False,
                chapters_failed=[],
                chapters_completed=1,
                chapters_total=1,
                chapters_completed_numbers=[1],
                failure_details={},
            )

            with patch.object(host, "load_state", return_value=state), patch.object(host, "save_state") as save:
                bridge._generation_finished(
                    "older-generation-job", project, summary, old_output, "Old Narrator"
                )

            self.assertEqual(state["status"], "generating")
            self.assertEqual(state["generation_job_id"], "newer-generation-job")
            self.assertEqual(state["generation_target_path"], str(new_output))
            self.assertIsNone(state["output_path"])
            save.assert_not_called()
            update = bridge._job_update.call_args.kwargs
            self.assertEqual(update["state"], "completed")
            self.assertIsNone(update["output_path"])
            self.assertTrue(update["result"]["superseded"])
            self.assertNotIn("older-generation-job", bridge._generators)

    def test_project_switch_keeps_late_completion_bound_to_original_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_a_folder = root / "project-a"
            project_b_folder = root / "project-b"
            project_a_folder.mkdir()
            project_b_folder.mkdir()
            output_a = root / "book-a.m4b"
            output_a.write_bytes(b"project-a-output" * 100)
            save_state(
                project_a_folder,
                {
                    "status": "generating",
                    "generation_job_id": "project-a-job",
                    "output_path": None,
                },
            )
            save_state(
                project_b_folder,
                {
                    "status": "generating",
                    "generation_job_id": "project-b-job",
                    "output_path": None,
                },
            )

            project_a = SimpleNamespace(folder=project_a_folder)
            project_b = SimpleNamespace(folder=project_b_folder)
            bridge = GenerationFinishOwnershipHarness("project-a-job")
            # The UI has since switched to B; completion retains the captured A
            # project reference and must not consult or overwrite B's current state.
            bridge._active_project = Mock(return_value=project_b)
            summary = SimpleNamespace(
                output_path=output_a,
                cancelled=False,
                packaging_failed=False,
                chapters_failed=[],
                chapters_completed=1,
                chapters_total=1,
                chapters_completed_numbers=[1],
                failure_details={},
            )

            bridge._generation_finished(
                "project-a-job", project_a, summary, output_a, "Project A Narrator"
            )

            project_a_state = load_state(project_a_folder)
            project_b_state = load_state(project_b_folder)
            self.assertEqual(project_a_state["status"], "completed")
            self.assertEqual(project_a_state["generation_job_id"], "project-a-job")
            self.assertEqual(project_a_state["output_path"], str(output_a))
            self.assertEqual(project_b_state["status"], "generating")
            self.assertEqual(project_b_state["generation_job_id"], "project-b-job")
            self.assertIsNone(project_b_state["output_path"])
            update = bridge._job_update.call_args.kwargs
            self.assertEqual(update["state"], "completed")
            self.assertEqual(update["output_path"], str(output_a))


class GenerationRecoveryLaunchHarness:
    """Exercise Recover -> Production -> GenerationManager using the real bridge methods."""

    _job_recover = host.PremiumV2Bridge._job_recover
    _restart_generation_from_job = host.PremiumV2Bridge._restart_generation_from_job
    _production_generate_book = host.PremiumV2Bridge._production_generate_book
    _resolve_narrator_for_generation = host.PremiumV2Bridge._resolve_narrator_for_generation

    def _load_library_project(self, requested_folder):
        try:
            requested = Path(requested_folder).expanduser().resolve()
            expected = Path(self.project.folder).expanduser().resolve()
        except (OSError, RuntimeError, TypeError, ValueError):
            return None
        return self.project if requested == expected else None

    def __init__(self, project, original_job_id: str, narrator_profile) -> None:
        self.project = project
        self.original_job_id = original_job_id
        self.narrator_profile = narrator_profile
        self._jobs_lock = threading.RLock()
        self._jobs = {
            original_job_id: {
                "job_id": original_job_id,
                "id": original_job_id,
                "type": "audiobook-generation",
                "project_title": project.title,
                "project_folder": str(project.folder),
                "state": "failed",
                "progress": 42,
                "retry_count": 0,
                "recoverable": True,
                "error": {"code": "interrupted", "message": "Worker did not survive restart."},
                "result": {
                    "generation_mode": "narrator_only",
                    "narrator_only": True,
                    "character_voice_profile_count": 2,
                },
            }
        }
        self._history = {}
        self._generators = {}
        self._new_job_id = "recovered-generation-job"
        self._assert_no_active_model_lifecycle = Mock()
        self._assert_no_active_audio_synthesis = Mock()
        self.close_preview_provider_cache = Mock()
        self._generation_progress = Mock()
        self._generation_finished = Mock()
        self._now = Mock(return_value="2026-11-08T19:30:00+00:00")
        self.settings = SimpleNamespace(value=lambda _key, default=None: default)

    def _project_series_name(self, _project, state):
        return str(state.get("series") or "Saved Series")

    def _narrator_series_default_read(self, _project, _state, series):
        return {
            "series": series,
            "profile_name": self.narrator_profile.name,
            "effective_profile_name": self.narrator_profile.name,
            "source": "project_override",
            "profile_available": True,
            "saved": True,
        }

    def _find_profile(self, name):
        return self.narrator_profile if name == self.narrator_profile.name else None

    def _unassigned_character_default_read(self):
        # Recovered narrator-only jobs must not depend on a cast fallback.
        return {"profile_name": None, "profile_available": False, "profile": None}

    def _effective_generation_character_rows(self, _state, _series, *, strict=False, **_kwargs):
        # Character records may exist, but narrator-only eligibility
        # requires zero configured saved character voice profiles.
        return (
            [
                {"name": "Mira", "series": "Saved Series", "voice_profile": ""},
                {"name": "Arun", "series": "Saved Series", "voice_profile": ""},
            ],
            [],
        )

    def _new_job(self, job_type, title, description, project=None):
        self._jobs[self._new_job_id] = {
            "job_id": self._new_job_id,
            "id": self._new_job_id,
            "type": job_type,
            "title": title,
            "description": description,
            "project_title": project.title if project else "",
            "project_folder": str(project.folder) if project else "",
            "state": "queued",
            "progress": 0,
            "retry_count": 0,
            "result": None,
            "recoverable": False,
        }
        return self._new_job_id

    def _job_update(self, job_id, **changes):
        row = self._jobs[job_id]
        row.update(changes)
        return dict(row)


class Stage53GenerationRecoveryLaunchTests(unittest.TestCase):
    def test_recover_launches_new_job_with_saved_narrator_only_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_folder = root / "saved-project"
            project_folder.mkdir()
            cover = root / "cover.png"
            cover.write_bytes(b"cover fixture")
            output = root / "output" / "saved-book.m4b"
            original_job_id = "interrupted-narrator-only-job"
            chapter = SimpleNamespace(
                number=1,
                chapter_id="chapter-one",
                title="Opening",
                text="Mira said, “The journey begins.”",
                skip_for_generation=False,
                dialogue_assignments=[],
            )
            project = SimpleNamespace(
                folder=project_folder,
                title="Saved Book",
                chapters=[chapter],
            )
            narrator = SimpleNamespace(
                name="Persisted Narrator",
                voice_id="persisted-narrator-voice",
                provider="piper",
            )
            state = {
                "status": "failed",
                "generation_job_id": original_job_id,
                "generation_recovery_required": True,
                "generation_interrupted_at": "2026-11-08T19:00:00+00:00",
                "generation_mode": "narrator_only",
                "narrator_only_generation": True,
                "character_voice_profile_count": 2,
                "voice_profile": narrator.name,
                "voice_id": narrator.voice_id,
                "narrator_profile_source": "project_override",
                "author": "Saved Author",
                "publisher": "Saved Publisher",
                "series": "Saved Series",
                "series_volume": "2",
                "language": "en-GB",
                "year": "2026",
                "genre": "Fantasy",
                "cover_path": str(cover),
                "output_path": None,
                "audio_bitrate": 192,
                "narration_speed": 0.97,
                "pacing_profile": "relaxed",
                "pronunciation_enabled": True,
                "background_audio_mode": "off",
                "background_audio_enabled": False,
                "chapter_bgm_strategy": "same",
                "chapter_bgm_overrides": {},
                "characters": [
                    {"name": "Mira", "voice_profile": ""},
                    {"name": "Arun", "voice_profile": ""},
                ],
            }
            bridge = GenerationRecoveryLaunchHarness(project, original_job_id, narrator)
            manager = Mock()

            with (
                patch.object(host, "list_projects", side_effect=AssertionError(
                    "generation recovery must load its original saved project directly"
                )),
                patch.object(host, "load_state", return_value=state),
                patch.object(host, "save_state"),
                patch.object(host, "provider_from_profile", return_value=(object(), narrator.voice_id)),
                patch.object(host, "load_profiles", return_value=[]),
                patch.object(host, "_effective_pronunciation_dictionary", return_value=[]),
                patch.object(host, "GenerationManager", return_value=manager) as manager_factory,
                patch("app.audio.library.effective_background_audio_mode", return_value="off"),
                patch("app.audio.library.is_chapter_transition_sound_enabled", return_value=False),
                patch("app.audio.library.validate_saved_audio_paths"),
            ):
                recovered = bridge._job_recover({"job_id": original_job_id})

            self.assertEqual(recovered["recovery_of_job_id"], original_job_id)
            self.assertEqual(recovered["job_id"], bridge._new_job_id)
            self.assertEqual(recovered["generation_mode"], "narrator_only")
            self.assertIs(recovered["narrator_only"], True)

            new_job = bridge._jobs[bridge._new_job_id]
            self.assertEqual(new_job["state"], "running")
            self.assertEqual(new_job["recovery_of_job_id"], original_job_id)
            self.assertEqual(new_job["result"]["generation_mode"], "narrator_only")
            self.assertIs(new_job["result"]["narrator_only"], True)
            self.assertEqual(new_job["result"]["character_voice_profile_count"], 0)

            provider = manager_factory.call_args.args[0]
            self.assertIs(provider.profile, narrator)
            self.assertEqual(manager_factory.call_args.args[1], narrator.voice_id)
            self.assertNotEqual(provider.__class__.__name__, "CastAwareProvider")
            manager.start.assert_called_once()
            self.assertEqual(state["generation_job_id"], bridge._new_job_id)
            self.assertIs(state["narrator_only_generation"], True)
            self.assertEqual(state["generation_mode"], "narrator_only")
            self.assertNotIn("generation_recovery_required", state)
