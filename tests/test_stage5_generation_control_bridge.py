"""Stage 5.3 GEN-03 tests for real Production job bridge controls."""
from __future__ import annotations

import math
import tempfile
import threading
import unittest
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.tts.manager import GenerationManager
from app.ui import premium_v2_host as host


class LocalControlProvider:
    """Small real WAV provider for live GenerationManager control tests."""

    recommended_chunk_chars = 1400
    recommended_chunk_sentences = 2

    def __init__(self) -> None:
        self.calls: list[str] = []

    def synthesize(self, text, output_path, voice=None):
        self.calls.append(text)
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


class GenerationControlBridgeHarness:
    _job_pause = host.PremiumV2Bridge._job_pause
    _job_resume = host.PremiumV2Bridge._job_resume
    _job_cancel = host.PremiumV2Bridge._job_cancel
    _generation_progress = host.PremiumV2Bridge._generation_progress
    _now = staticmethod(host.PremiumV2Bridge._now)

    def __init__(self, job_id: str, manager: GenerationManager) -> None:
        self._jobs_lock = threading.RLock()
        self._generators = {job_id: manager}
        self._jobs = {
            job_id: {
                "job_id": job_id,
                "type": "audiobook-generation",
                "state": "running",
                "progress": 1,
            }
        }

    def _job_update(self, job_id: str, **changes):
        with self._jobs_lock:
            row = self._jobs[job_id]
            row.update(changes)
            return dict(row)


class _FixedDateTime(datetime):
    current = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls.current.replace(tzinfo=None)
        return cls.current.astimezone(tz)


class _ElapsedClockBridgeHarness:
    _job_update = host.PremiumV2Bridge._job_update

    def __init__(self, started_at: datetime) -> None:
        self._jobs_lock = threading.RLock()
        self._jobs = {
            "elapsed-clock-job": {
                "job_id": "elapsed-clock-job",
                "type": "audiobook-generation",
                "state": "running",
                "started_at": started_at.isoformat(),
                "elapsed_seconds": 0,
                "progress": 1,
            }
        }

    def _now(self) -> str:
        return _FixedDateTime.now(timezone.utc).isoformat(timespec="seconds")

    def _record_history_job(self, _row) -> None:
        pass

    def _persist_jobs(self) -> None:
        pass


class Stage53GenerationElapsedClockTests(unittest.TestCase):
    def test_job_elapsed_checkpoint_excludes_pauses_and_freezes_when_cancelled_paused(self) -> None:
        started = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
        _FixedDateTime.current = started
        bridge = _ElapsedClockBridgeHarness(started)

        with patch.object(host, "datetime", _FixedDateTime):
            _FixedDateTime.current = started + timedelta(seconds=10)
            paused = bridge._job_update("elapsed-clock-job", state="paused")
            self.assertEqual(paused["elapsed_seconds"], 10)
            self.assertEqual(paused["state"], "paused")
            self.assertTrue(paused["elapsed_frozen"])
            self.assertIsNotNone(paused["elapsed_paused_at"])

            _FixedDateTime.current = started + timedelta(minutes=7, seconds=10)
            resumed = bridge._job_update("elapsed-clock-job", state="running")
            self.assertEqual(resumed["elapsed_seconds"], 10)
            self.assertEqual(resumed["elapsed_paused_seconds"], 420.0)
            self.assertIsNone(resumed["elapsed_paused_at"])
            self.assertFalse(resumed["elapsed_frozen"])

            _FixedDateTime.current = started + timedelta(minutes=7, seconds=30)
            progress = bridge._job_update("elapsed-clock-job", progress=50)
            self.assertEqual(progress["elapsed_seconds"], 30)

            _FixedDateTime.current = started + timedelta(minutes=7, seconds=35)
            paused_again = bridge._job_update("elapsed-clock-job", state="paused")
            self.assertEqual(paused_again["elapsed_seconds"], 35)

            _FixedDateTime.current = started + timedelta(minutes=47, seconds=35)
            cancelling = bridge._job_update("elapsed-clock-job", state="cancel_requested")
            self.assertEqual(cancelling["elapsed_seconds"], 35)
            self.assertTrue(cancelling["elapsed_frozen"])
            self.assertIsNone(cancelling["elapsed_paused_at"])

            _FixedDateTime.current += timedelta(seconds=7)
            cancelled = bridge._job_update("elapsed-clock-job", state="cancelled")
            self.assertEqual(cancelled["elapsed_seconds"], 35)
            self.assertTrue(cancelled["elapsed_frozen"])


class Stage53GenerationControlBridgeTests(unittest.TestCase):
    def _start_paused_manager(self, root: Path):
        job_id = "stage53-live-control-job"
        provider = LocalControlProvider()
        paused = threading.Event()
        completed = threading.Event()
        pause_requested = threading.Event()
        summaries = []
        bridge_ref = {}
        manager_ref = {}

        def on_progress(chapter, total, done, detail):
            bridge_ref["bridge"]._generation_progress(
                job_id, chapter, total, done, detail
            )
            if detail.startswith("chapter-complete:") and not pause_requested.is_set():
                pause_requested.set()
                bridge_ref["bridge"]._job_pause({"job_id": job_id})
            if detail.startswith("paused:"):
                paused.set()

        def on_finished(summary):
            summaries.append(summary)
            completed.set()

        manager = GenerationManager(
            provider,
            "Saved Narrator",
            [
                Chapter(1, "First", "First chapter is generated."),
                Chapter(2, "Second", "Second chapter is generated."),
            ],
            root / "working_audio",
            on_progress=on_progress,
            on_finished=on_finished,
        )
        manager_ref["manager"] = manager
        bridge = GenerationControlBridgeHarness(job_id, manager)
        bridge_ref["bridge"] = bridge
        manager.start(output_path=None, title="Stage 5.3 Controls", author="Test Author")
        self.assertTrue(paused.wait(10), "job did not pause at a safe chapter boundary")
        return job_id, provider, manager, bridge, completed, summaries

    def test_bridge_pause_and_resume_control_real_generation_manager(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job_id, provider, manager, bridge, completed, summaries = self._start_paused_manager(
                Path(temporary)
            )
            self.assertEqual(bridge._jobs[job_id]["state"], "paused")
            self.assertTrue(manager.pause_event.is_set())

            response = bridge._job_resume({"job_id": job_id})

            self.assertEqual(response["state"], "running")
            self.assertFalse(manager.pause_event.is_set())
            self.assertTrue(completed.wait(10), "generation did not continue after bridge resume")
            manager._thread.join(timeout=10)

            self.assertFalse(manager._thread.is_alive())
            self.assertEqual(len(summaries), 1)
            self.assertFalse(summaries[0].cancelled)
            self.assertEqual(summaries[0].chapters_completed, 2)
            self.assertEqual(len(provider.calls), 2)

    def test_bridge_pause_and_resume_at_saved_chunk_boundary_inside_a_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job_id = "stage54-chunk-control-job"
            provider = LocalControlProvider()
            provider.recommended_chunk_sentences = 1
            paused = threading.Event()
            completed = threading.Event()
            pause_requested = threading.Event()
            summaries = []
            bridge_ref = {}

            def on_progress(chapter, total, done, detail):
                bridge_ref["bridge"]._generation_progress(job_id, chapter, total, done, detail)
                if detail.startswith("chunk:") and not pause_requested.is_set():
                    pause_requested.set()
                    bridge_ref["bridge"]._job_pause({"job_id": job_id})
                if detail.startswith("paused:"):
                    paused.set()

            def on_finished(summary):
                summaries.append(summary)
                completed.set()

            manager = GenerationManager(
                provider,
                "Saved Narrator",
                [Chapter(1, "Long Chapter", "First sentence. Second sentence. Third sentence.")],
                root / "working_audio",
                on_progress=on_progress,
                on_finished=on_finished,
            )
            bridge = GenerationControlBridgeHarness(job_id, manager)
            bridge_ref["bridge"] = bridge
            manager.start(output_path=None, title="Stage 5.4 Chunk Pause", author="Test Author")

            self.assertTrue(paused.wait(10), "job did not pause at a saved chunk boundary inside the chapter")
            self.assertEqual(bridge._jobs[job_id]["state"], "paused")
            self.assertEqual(len(provider.calls), 1, "pause should be reached before the remaining chapter chunks run")

            response = bridge._job_resume({"job_id": job_id})
            self.assertEqual(response["state"], "running")
            self.assertTrue(completed.wait(10), "generation did not resume after the chunk checkpoint")
            manager._thread.join(timeout=10)

            self.assertFalse(manager._thread.is_alive())
            self.assertEqual(len(summaries), 1)
            self.assertFalse(summaries[0].cancelled)
            self.assertEqual(summaries[0].chapters_completed, 1)
            self.assertGreater(len(provider.calls), 1)

    def test_bridge_cancel_stops_real_generation_while_paused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            job_id, provider, manager, bridge, completed, summaries = self._start_paused_manager(
                Path(temporary)
            )
            self.assertEqual(bridge._jobs[job_id]["state"], "paused")

            response = bridge._job_cancel({"job_id": job_id})

            self.assertEqual(response["state"], "cancel_requested")
            self.assertTrue(completed.wait(10), "generation did not stop after bridge cancellation")
            manager._thread.join(timeout=10)

            self.assertFalse(manager._thread.is_alive())
            self.assertEqual(len(summaries), 1)
            self.assertTrue(summaries[0].cancelled)
            self.assertEqual(summaries[0].chapters_completed, 1)
            self.assertEqual(provider.calls, ["First chapter is generated."])


if __name__ == "__main__":
    unittest.main()
