"""Stage 5.4 checkpoint payload integrity and resume inspection tests."""
from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from app.chapters.detector import Chapter
from app.tts.generator import generate_chapter, is_valid_wav_chunk
from app.tts.resume import inspect_generation_state


class RecordingCheckpointProvider:
    recommended_chunk_chars = 1400
    recommended_chunk_sentences = 1

    def __init__(self) -> None:
        self.calls: list[str] = []

    def generation_signature(self) -> str:
        return "stage54-checkpoint-integrity-provider-v1"

    def synthesize(self, text, output_path, voice=None):
        self.calls.append(str(text))
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(22050)
            stream.writeframes(b"\\x00\\x00" * 4410)
        return target

    def close(self) -> None:
        pass


class Stage54CheckpointPayloadIntegrityTests(unittest.TestCase):
    def _chapter(self) -> Chapter:
        return Chapter(1, "Chapter One", "This is a stable checkpoint sentence.")

    def test_truncated_wav_with_valid_header_is_regenerated_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "working_audio"
            chapter = self._chapter()
            first_provider = RecordingCheckpointProvider()
            first = generate_chapter(
                chapter, first_provider, "Saved Narrator", root,
                narration_speed=1.0, pacing_profile="off",
            )
            self.assertEqual(len(first_provider.calls), 1)
            chunk = first.output_path / "chunks" / "00001.wav"
            self.assertTrue(is_valid_wav_chunk(chunk))

            payload = chunk.read_bytes()
            chunk.write_bytes(payload[:2048])
            self.assertGreater(chunk.stat().st_size, 1024)
            self.assertFalse(is_valid_wav_chunk(chunk))

            retry_provider = RecordingCheckpointProvider()
            retried = generate_chapter(
                chapter, retry_provider, "Saved Narrator", root,
                narration_speed=1.0, pacing_profile="off",
            )
            self.assertEqual(retry_provider.calls, ["This is a stable checkpoint sentence."])
            self.assertEqual(retried.chunks_completed, retried.chunks_total)
            self.assertTrue(is_valid_wav_chunk(retried.output_path / "chunks" / "00001.wav"))

    def test_resume_inspector_does_not_mark_truncated_checkpoint_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "working_audio"
            chapter = self._chapter()
            provider = RecordingCheckpointProvider()
            generated = generate_chapter(
                chapter, provider, "Saved Narrator", root,
                narration_speed=1.0, pacing_profile="off",
            )
            chunk = generated.output_path / "chunks" / "00001.wav"
            chunk.write_bytes(chunk.read_bytes()[:2048])

            state = inspect_generation_state(root, [chapter])

            self.assertNotIn(1, state.completed_chapters)
            self.assertIn(1, state.partial_chapters)
            self.assertTrue(state.resume_available)


if __name__ == "__main__":
    unittest.main()
