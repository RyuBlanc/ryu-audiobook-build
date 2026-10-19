"""Stage 8.2.3 acceptance tests for generation pause/resume/cancel controls.

These exercise the real GenerationManager with a deterministic local provider;
they do not claim to replace interactive Windows UI acceptance.
"""
from __future__ import annotations

import math
import tempfile
import threading
import unittest
import wave
from pathlib import Path

from app.chapters.detector import Chapter
from app.tts.manager import GenerationManager


def _write_short_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    frames = int(rate * 0.08)
    samples = bytearray()
    for index in range(frames):
        sample = int(5000 * math.sin(2 * math.pi * 440 * index / rate))
        samples.extend(sample.to_bytes(2, "little", signed=True))
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes(bytes(samples))


class LocalTestProvider:
    """Tiny deterministic provider; no network or model download is involved."""

    recommended_chunk_chars = 1400
    recommended_chunk_sentences = 2

    def synthesize(self, text, output_path, voice=None):
        _write_short_wav(Path(output_path))

    def close(self):
        pass


class Stage823GenerationControlTests(unittest.TestCase):
    def _manager_paused_after_first_chapter(self, root: Path):
        paused = threading.Event()
        summaries = []
        manager_ref = {}

        def on_progress(_chapter, _total, _chunk, detail):
            if detail.startswith("chapter-complete:") and not paused.is_set():
                manager_ref["manager"].pause()
            if detail.startswith("paused:"):
                paused.set()

        manager = GenerationManager(
            LocalTestProvider(),
            "Local test voice",
            [Chapter(1, "First", "First chapter is ready."),
             Chapter(2, "Second", "Second chapter is ready.")],
            root / "working_audio",
            on_progress=on_progress,
            on_finished=summaries.append,
        )
        manager_ref["manager"] = manager
        manager.start()
        self.assertTrue(paused.wait(10), "generation did not reach a pause checkpoint")
        return manager, summaries

    def test_generation_resumes_from_pause_checkpoint_and_finishes(self):
        with tempfile.TemporaryDirectory() as temp:
            manager, summaries = self._manager_paused_after_first_chapter(Path(temp))
            manager.resume()
            manager._thread.join(timeout=10)

            self.assertFalse(manager._thread.is_alive(), "generation did not finish after resume")
            self.assertEqual(len(summaries), 1)
            self.assertFalse(summaries[0].cancelled)
            self.assertEqual(summaries[0].chapters_completed, 2)
            self.assertEqual(summaries[0].chapters_failed, [])

    def test_cancel_while_paused_finishes_as_cancelled_without_next_chapter(self):
        with tempfile.TemporaryDirectory() as temp:
            manager, summaries = self._manager_paused_after_first_chapter(Path(temp))
            manager.cancel()
            manager._thread.join(timeout=10)

            self.assertFalse(manager._thread.is_alive(), "generation did not stop after cancel")
            self.assertEqual(len(summaries), 1)
            self.assertTrue(summaries[0].cancelled)
            self.assertEqual(summaries[0].chapters_completed, 1)
            self.assertEqual(summaries[0].chapters_failed, [])


if __name__ == "__main__":
    unittest.main()
