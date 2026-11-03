"""Stage 5.3 GEN-02 tests for saved narrator/profile checkpoint compatibility."""
from __future__ import annotations

import tempfile
import unittest
import wave
from pathlib import Path

from app.chapters.detector import Chapter
from app.tts.generator import generate_chapter
from app.tts.profile_provider import ProfileBoundProvider
from app.tts.voice_profile import VoiceProfile


class RecordingLocalProvider:
    """Write actual WAV chunks while recording synthesis calls."""

    recommended_chunk_chars = 1400
    recommended_chunk_sentences = 1

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    def generation_signature(self) -> str:
        # Provider runtime is deliberately stable; the selected saved profile
        # must independently participate in the checkpoint signature.
        return "stage5-gen02-local-test-engine-v1"

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


class Stage53CheckpointCompatibilityTests(unittest.TestCase):
    def _profile(self, *, backend="automatic", voice_id="saved-voice-id") -> VoiceProfile:
        return VoiceProfile(
            name="Saved Narrator Profile",
            provider="piper",
            voice_id=voice_id,
            backend=backend,
            authorized=True,
        )

    def _chapter(self) -> Chapter:
        return Chapter(
            1,
            "Chapter One",
            "The first sentence begins the story. The second sentence continues it. "
            "The third sentence finishes this test chapter.",
        )

    def test_new_chapter_identity_does_not_adopt_same_number_and_title_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "working_audio"
            original = Chapter(1, "Chapter One", "Identical source text.", chapter_id="chapter-identity-a")
            original_provider = RecordingLocalProvider()
            original_result = generate_chapter(
                original, original_provider, "saved-voice-id", root,
                narration_speed=1.0, pacing_profile="off",
            )
            self.assertGreater(len(original_provider.calls), 0)

            replacement = Chapter(1, "Chapter One", "Identical source text.", chapter_id="chapter-identity-b")
            replacement_provider = RecordingLocalProvider()
            replacement_result = generate_chapter(
                replacement, replacement_provider, "saved-voice-id", root,
                narration_speed=1.0, pacing_profile="off",
            )

            self.assertNotEqual(original_result.output_path, replacement_result.output_path)
            self.assertNotEqual(original_result.output_path.name, replacement_result.output_path.name)
            self.assertGreater(
                len(replacement_provider.calls), 0,
                "a different stable chapter identity must not reuse another chapter's audio",
            )
            self.assertTrue((original_result.output_path / "narration.json").is_file())
            self.assertTrue((replacement_result.output_path / "narration.json").is_file())

    def test_unchanged_saved_profile_reuses_valid_checkpoint_wav_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "working_audio"
            chapter = self._chapter()
            profile = self._profile()
            first_provider = RecordingLocalProvider()

            first = generate_chapter(
                chapter,
                ProfileBoundProvider(first_provider, profile),
                profile.voice_id,
                root,
                narration_speed=1.0,
                pacing_profile="off",
            )
            self.assertGreater(first_provider.calls.__len__(), 0)
            self.assertGreater(first.chunks_total, 1)

            manifest_path = first.output_path / "manifest.json"
            first_manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
            self.assertTrue(first_manifest["generation_signature"])

            resumed_provider = RecordingLocalProvider()
            resumed = generate_chapter(
                chapter,
                ProfileBoundProvider(resumed_provider, self._profile()),
                profile.voice_id,
                root,
                narration_speed=1.0,
                pacing_profile="off",
            )

            self.assertEqual(resumed_provider.calls, [])
            self.assertEqual(resumed.chunks_total, first.chunks_total)
            self.assertEqual(resumed.chunks_completed, resumed.chunks_total)
            self.assertEqual(
                __import__("json").loads(manifest_path.read_text(encoding="utf-8"))["generation_signature"],
                first_manifest["generation_signature"],
            )

    def test_changed_saved_profile_settings_invalidate_and_regenerate_cached_chunks(self) -> None:
        variants = (
            ("backend", self._profile(backend="cpu")),
            ("voice identity", self._profile(voice_id="different-saved-voice-id")),
        )
        for label, changed_profile in variants:
            with self.subTest(changed_profile=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "working_audio"
                chapter = self._chapter()
                original_profile = self._profile()
                first_provider = RecordingLocalProvider()

                first = generate_chapter(
                    chapter,
                    ProfileBoundProvider(first_provider, original_profile),
                    original_profile.voice_id,
                    root,
                    narration_speed=1.0,
                    pacing_profile="off",
                )
                self.assertGreater(first_provider.calls.__len__(), 0)
                manifest_path = first.output_path / "manifest.json"
                original_signature = __import__("json").loads(
                    manifest_path.read_text(encoding="utf-8")
                )["generation_signature"]

                changed_provider = RecordingLocalProvider()
                regenerated = generate_chapter(
                    chapter,
                    ProfileBoundProvider(changed_provider, changed_profile),
                    changed_profile.voice_id,
                    root,
                    narration_speed=1.0,
                    pacing_profile="off",
                )

                self.assertGreater(
                    changed_provider.calls.__len__(),
                    0,
                    "incompatible saved profile must not reuse old narration audio",
                )
                self.assertEqual(regenerated.chunks_completed, regenerated.chunks_total)
                changed_signature = __import__("json").loads(
                    manifest_path.read_text(encoding="utf-8")
                )["generation_signature"]
                self.assertNotEqual(changed_signature, original_signature)
                for chunk in (regenerated.output_path / "chunks").glob("*.wav"):
                    with wave.open(str(chunk), "rb") as stream:
                        self.assertGreater(stream.getnframes(), 0)
                        self.assertGreater(stream.getframerate(), 0)


if __name__ == "__main__":
    unittest.main()
