"""Stage 8.2.10 regressions for trustworthy chapter-cache recovery."""
import json
import tempfile
import unittest
import wave
from pathlib import Path

from app.audio.assembler import sorted_chunks
from app.chapters.detector import Chapter
from app.tts.generator import generate_chapter


def _write_wav(path: Path, seconds: float = 0.05) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    frames = max(1, int(rate * seconds))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(b"\x00\x00" * frames)


class DummyProvider:
    recommended_chunk_chars = 1400
    recommended_chunk_sentences = 1

    def __init__(self):
        self.calls = 0

    def synthesize(self, text, output_path, voice=None):
        self.calls += 1
        _write_wav(output_path)
        return output_path


class Stage8210ResumeChunkIntegrityTests(unittest.TestCase):
    def test_changed_text_prunes_stale_chunks_and_assembled_chapter_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "working_audio"
            provider = DummyProvider()
            original = Chapter(1, "Chapter One", "First sentence. Second sentence. Third sentence.")
            first = generate_chapter(original, provider, "Narrator", root,
                                     narration_speed=1.0, pacing_profile="off")
            self.assertGreater(first.chunks_total, 1)

            cached_audio = first.output_path / "chapter.m4a"
            cache_settings = first.output_path / ".audio-settings"
            cached_audio.write_bytes(b"old assembled chapter")
            cache_settings.write_text("256k|speed=1.000", encoding="utf-8")

            revised = Chapter(1, "Chapter One", "Only one sentence remains.")
            second = generate_chapter(revised, provider, "Narrator", root,
                                      narration_speed=1.0, pacing_profile="off")

            self.assertEqual(second.chunks_total, 1)
            self.assertEqual(
                [path.name for path in (second.output_path / "chunks").glob("*.wav")],
                ["00001.wav"],
            )
            self.assertFalse(cached_audio.exists())
            self.assertFalse(cache_settings.exists())
            manifest = json.loads((second.output_path / "chunk_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual([chunk["file"] for chunk in manifest["chunks"]], ["00001.wav"])

    def test_corrupt_completed_wav_is_regenerated_on_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "working_audio"
            provider = DummyProvider()
            chapter = Chapter(1, "Chapter One", "First sentence. Second sentence. Third sentence.")
            first = generate_chapter(chapter, provider, "Narrator", root,
                                     narration_speed=1.0, pacing_profile="off")
            first_chunks = sorted((first.output_path / "chunks").glob("*.wav"))
            self.assertGreater(len(first_chunks), 1)
            first_chunks[0].write_bytes(b"not a valid WAV")
            cached_audio = first.output_path / "chapter.m4a"
            cache_settings = first.output_path / ".audio-settings"
            cached_audio.write_bytes(b"stale chapter audio")
            cache_settings.write_text("256k|speed=1.000", encoding="utf-8")
            calls_before_retry = provider.calls

            resumed = generate_chapter(chapter, provider, "Narrator", root,
                                        narration_speed=1.0, pacing_profile="off")

            self.assertEqual(provider.calls, calls_before_retry + 1)
            self.assertEqual(resumed.chunks_completed, resumed.chunks_total)
            self.assertFalse(cached_audio.exists())
            self.assertFalse(cache_settings.exists())
            with wave.open(str(first_chunks[0]), "rb") as wav_file:
                self.assertGreater(wav_file.getnframes(), 0)
                self.assertGreater(wav_file.getframerate(), 0)

    def test_assembler_uses_only_manifest_chunks_not_orphaned_wavs(self):
        with tempfile.TemporaryDirectory() as temp:
            chapter_dir = Path(temp) / "001_Chapter_One"
            chunks_dir = chapter_dir / "chunks"
            expected = chunks_dir / "00001.wav"
            orphaned = chunks_dir / "00002.wav"
            _write_wav(expected)
            _write_wav(orphaned)
            (chapter_dir / "chunk_manifest.json").write_text(
                json.dumps({"chunks": [{"index": 1, "file": "00001.wav", "text": "current narration"}]}),
                encoding="utf-8",
            )

            self.assertEqual(sorted_chunks(chapter_dir), [expected])

    def test_assembler_refuses_to_package_a_missing_manifest_chunk(self):
        with tempfile.TemporaryDirectory() as temp:
            chapter_dir = Path(temp) / "001_Chapter_One"
            _write_wav(chapter_dir / "chunks" / "00001.wav")
            (chapter_dir / "chunk_manifest.json").write_text(
                json.dumps({"chunks": [
                    {"index": 1, "file": "00001.wav", "text": "first"},
                    {"index": 2, "file": "00002.wav", "text": "missing second"},
                ]}),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(FileNotFoundError, "00002.wav"):
                sorted_chunks(chapter_dir)


if __name__ == "__main__":
    unittest.main()
