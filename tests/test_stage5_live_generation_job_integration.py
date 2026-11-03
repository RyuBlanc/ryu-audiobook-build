"""Stage 5.3 local-provider integration of Production, GenerationManager and durable jobs."""
from __future__ import annotations

import tempfile
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
from app.core.state import load_state, save_state
from app.tts.voice_profile import VoiceProfile
from app.ui import premium_v2_host as host


class RecordingLocalProvider:
    """Deterministic provider that writes real WAV chunks without model downloads."""

    recommended_chunk_chars = 1400
    recommended_chunk_sentences = 2

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def synthesize(self, text, output_path, voice=None):
        self.calls.append((text, voice))
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(22050)
            stream.writeframes(b"\x00\x00" * 4410)
        return target

    def close(self) -> None:
        pass


class LiveProductionGenerationHarness:
    """Production bridge callbacks with real persistent job/history implementations."""

    _production_generate_book = host.PremiumV2Bridge._production_generate_book
    _generation_progress = host.PremiumV2Bridge._generation_progress
    _new_job = host.PremiumV2Bridge._new_job
    _job_update = host.PremiumV2Bridge._job_update
    _persist_json_rows = host.PremiumV2Bridge._persist_json_rows
    _persist_jobs = host.PremiumV2Bridge._persist_jobs
    _persist_history = host.PremiumV2Bridge._persist_history
    _record_history_job = host.PremiumV2Bridge._record_history_job
    _job_list = host.PremiumV2Bridge._job_list
    _history_list = host.PremiumV2Bridge._history_list
    _terminal_job_state = staticmethod(host.PremiumV2Bridge._terminal_job_state)
    _now = staticmethod(host.PremiumV2Bridge._now)

    def __init__(self, project, profile, settings_root: Path) -> None:
        self.project = project
        self._jobs: dict[str, dict] = {}
        self._history: dict[str, dict] = {}
        self._jobs_lock = threading.RLock()
        self._jobs_path = lambda: settings_root / "premium_v2_jobs.json"
        self._history_path = lambda: settings_root / "premium_v2_history.json"
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
        self._generators = {}
        self.settings = SimpleNamespace(value=lambda _key, default=None: default)
        self.finished_event = threading.Event()

    def _generation_finished(self, *args) -> None:
        host.PremiumV2Bridge._generation_finished(self, *args)
        self.finished_event.set()


class Stage53LiveGenerationIntegrationTests(unittest.TestCase):
    def test_production_runs_real_chunk_generation_and_unifies_completed_job_and_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_folder = root / "project"
            project_folder.mkdir()
            settings_root = root / "settings"
            cover = root / "cover.png"
            cover.write_bytes(b"valid cover fixture")
            output = root / "output" / "Saved Book.m4b"

            chapter = Chapter(1, "Opening", "The saved story begins.")
            project = SimpleNamespace(
                folder=project_folder,
                title="Saved Book",
                chapters=[chapter],
            )
            profile = VoiceProfile(
                name="Saved Narrator",
                provider="piper",
                voice_id="saved-narrator-voice",
                authorized=True,
            )
            state = {
                "author": "Saved Author",
                "publisher": "Saved Publisher",
                "series": "Saved Series",
                "series_volume": "3",
                "language": "en-GB",
                "year": "2026",
                "genre": "Fantasy",
                "cover_path": str(cover),
                "output_path": str(output),
                "audio_bitrate": 192,
                "narration_speed": 1.0,
                "pacing_profile": "off",
                "background_audio_mode": "off",
                "background_audio_enabled": False,
                "chapter_bgm_strategy": "same",
                "chapter_bgm_overrides": {},
                "characters": [],
            }
            save_state(project_folder, state)
            local_provider = RecordingLocalProvider()
            bridge = LiveProductionGenerationHarness(project, profile, settings_root)

            def assemble_local_fixture(_chapter_dirs, output_path, *_args, **_kwargs):
                target = Path(output_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                # GEN-05's actual M4B tags/chapters/decodability are validated
                # separately in Stage 5.4. Here the real GenerationManager must
                # complete WAV synthesis and hand off a non-empty assembly result.
                target.write_bytes(b"stage-5.3-assembled-output" * 128)
                return target

            with (
                patch.object(host, "provider_from_profile", return_value=(local_provider, profile.voice_id)),
                patch.object(host, "load_profiles", return_value=[]),
                patch.object(host, "_effective_pronunciation_dictionary", return_value=[]),
                patch("app.audio.library.effective_background_audio_mode", return_value="off"),
                patch("app.audio.library.validate_saved_audio_paths"),
                patch("app.tts.manager.validate_cover", return_value=cover),
                patch("app.tts.manager.assemble_m4b", side_effect=assemble_local_fixture),
            ):
                result = bridge._production_generate_book(
                    {"output_path": str(output), "profile_name": "Transient UI Narrator"}
                )
                self.assertEqual(result["state"], "running")
                self.assertTrue(
                    bridge.finished_event.wait(15),
                    "the actual GenerationManager did not reach its completion callback",
                )

            self.assertEqual(result["voice_profile"], "Saved Narrator")
            self.assertEqual(local_provider.calls, [("The saved story begins.", "saved-narrator-voice")])
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)

            saved_project_state = load_state(project_folder)
            self.assertEqual(saved_project_state["status"], "completed")
            self.assertEqual(saved_project_state["generation_job_id"], result["job_id"])
            self.assertEqual(saved_project_state["output_path"], str(output.resolve()))
            self.assertEqual(saved_project_state["completed_chapters"], [1])

            queue_rows = bridge._job_list({"include_hidden": False})
            history_rows = bridge._history_list({})
            queue_job = next(row for row in queue_rows if row["job_id"] == result["job_id"])
            history_job = next(row for row in history_rows if row["job_id"] == result["job_id"])
            self.assertEqual(queue_job["state"], "completed")
            self.assertEqual(history_job["state"], "completed")
            self.assertEqual(queue_job["job_id"], history_job["job_id"])
            self.assertEqual(queue_job["output_path"], str(output.resolve()))
            self.assertEqual(history_job["output_path"], str(output.resolve()))

            # Retry the completed project as a new job. The Production bridge
            # must issue a distinct job ID while the real chunk generator reuses
            # the compatible saved narrator/audio checkpoint without synthesizing
            # the same narration again.
            bridge.finished_event.clear()
            local_provider.calls.clear()
            retry_result = bridge._production_generate_book(
                {"output_path": str(output), "profile_name": "Another Transient Voice"}
            )
            self.assertNotEqual(retry_result["job_id"], result["job_id"])
            self.assertTrue(
                bridge.finished_event.wait(15),
                "the retry GenerationManager did not reach its completion callback",
            )
            self.assertEqual(local_provider.calls, [])
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)

            retried_project_state = load_state(project_folder)
            self.assertEqual(retried_project_state["status"], "completed")
            self.assertEqual(retried_project_state["generation_job_id"], retry_result["job_id"])
            self.assertEqual(retried_project_state["output_path"], str(output.resolve()))

            retry_queue_job = next(
                row for row in bridge._job_list({"include_hidden": False})
                if row["job_id"] == retry_result["job_id"]
            )
            retry_history_job = next(
                row for row in bridge._history_list({})
                if row["job_id"] == retry_result["job_id"]
            )
            self.assertEqual(retry_queue_job["state"], "completed")
            self.assertEqual(retry_history_job["state"], "completed")
            self.assertEqual(retry_queue_job["job_id"], retry_history_job["job_id"])
            self.assertEqual(retry_queue_job["output_path"], str(output.resolve()))
            self.assertEqual(retry_history_job["output_path"], str(output.resolve()))

            persisted_jobs = json_rows = __import__("json").loads(
                (settings_root / "premium_v2_jobs.json").read_text(encoding="utf-8")
            )
            persisted_history = __import__("json").loads(
                (settings_root / "premium_v2_history.json").read_text(encoding="utf-8")
            )
            self.assertIn(result["job_id"], {row["job_id"] for row in persisted_jobs})
            self.assertIn(result["job_id"], {row["job_id"] for row in persisted_history})


if __name__ == "__main__":
    unittest.main()
