"""Browser-compatible playback derivative tests for finished M4B audiobooks."""
from __future__ import annotations

import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave

import imageio_ffmpeg

from app.audio.assembler import _duration_ms, assemble_m4b
from app.audio.playback import is_iso_bmff_file, prepare_audiobook_playback_source


def _write_wav(path: Path, seconds: float = 2.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        samples = bytearray()
        for index in range(frames):
            value = int(5000 * math.sin(2 * math.pi * 330 * index / rate))
            samples.extend(struct.pack("<h", value))
        stream.writeframes(bytes(samples))


class AudiobookPlaybackSourceTests(unittest.TestCase):
    def _make_book(self, root: Path) -> Path:
        chapter = root / "001_Opening"
        _write_wav(chapter / "chunks" / "00001.wav")
        output = root / "Finished Book.m4b"
        assemble_m4b(
            chapter_dirs=[chapter],
            output_path=output,
            title="Playback Compatibility Fixture",
            author="Ryu Test",
            chapter_titles=["Opening"],
            metadata={
                "title": "Playback Compatibility Fixture",
                "author": "Ryu Test",
                "narrator": "Test Narrator",
                "language": "en",
                "genre": "Audiobook",
            },
            bitrate=128,
        )
        return output

    def test_real_m4b_gets_cached_mp3_for_html_audio_without_changing_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = self._make_book(root)
            self.assertTrue(is_iso_bmff_file(source))
            source_bytes = source.read_bytes()
            cache = root / "cache"

            playback = prepare_audiobook_playback_source(source, cache_root=cache)
            self.assertEqual(playback.suffix, ".mp3")
            self.assertTrue(playback.is_file())
            self.assertGreater(playback.stat().st_size, 1024)
            self.assertNotEqual(playback.resolve(), source.resolve())
            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertLessEqual(abs(_duration_ms(playback) - _duration_ms(source)), 1500)

            decoded = subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                    "-i", str(playback), "-map", "0:a:0", "-f", "null", "-",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(decoded.returncode, 0, decoded.stderr)

            cached = prepare_audiobook_playback_source(source, cache_root=cache)
            self.assertEqual(cached, playback)
            self.assertEqual(len(list(cache.glob("audiobook_playback_*.mp3"))), 1)

    def test_browser_supported_sources_are_not_reencoded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mp3 = root / "existing.mp3"
            mp3.write_bytes(b"existing MP3 fixture")
            self.assertEqual(
                prepare_audiobook_playback_source(mp3, cache_root=root / "cache"),
                mp3.resolve(),
            )

    def test_non_mp4_m4b_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            invalid = root / "invalid.m4b"
            invalid.write_bytes(b"not an ISO base media file")
            self.assertFalse(is_iso_bmff_file(invalid))
            with self.assertRaisesRegex(ValueError, "valid MP4/M4B"):
                prepare_audiobook_playback_source(invalid, cache_root=root / "cache")


if __name__ == "__main__":
    unittest.main()
