"""Stage 7.4.3 integration checks for real M4B chapter and metadata output.

These tests exercise FFmpeg packaging with actual local audio files. They do not
replace playback tests in a desktop audiobook player.
"""
from __future__ import annotations

import math
import struct
import subprocess
import tempfile
import unittest
import wave
import zlib
from pathlib import Path

import imageio_ffmpeg

from app.audio.assembler import assemble_m4b


def write_test_wav(path: Path, seconds: float = 0.8) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rate = 22050
    frames = int(rate * seconds)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        samples = bytearray()
        for index in range(frames):
            sample = int(6000 * math.sin(2 * math.pi * 440 * index / rate))
            samples.extend(struct.pack("<h", sample))
        stream.writeframes(bytes(samples))


def write_test_png(path: Path) -> None:
    """Write a tiny valid RGB PNG without relying on Pillow."""
    width = height = 2

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    scanlines = b"".join(
        b"\x00" + bytes((180, 30, 60, 240, 180, 30)) for _ in range(height)
    )
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(payload)


class Stage743OutputValidationTests(unittest.TestCase):
    def test_m4b_embeds_chapter_titles_metadata_and_cover(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chapter_dirs = []
            for number in (1, 2):
                chapter_dir = root / f"{number:03d}_Chapter_{number}"
                write_test_wav(chapter_dir / "chunks" / "00001.wav")
                chapter_dirs.append(chapter_dir)

            cover = root / "cover.png"
            write_test_png(cover)
            output = assemble_m4b(
                chapter_dirs=chapter_dirs,
                output_path=root / "validated-output.m4b",
                title="Stage 7.4.3 Test Book",
                author="Ryu Test Author",
                cover=cover,
                chapter_titles=["Opening Chapter", "Final Chapter"],
                metadata={
                    "title": "Stage 7.4.3 Test Book",
                    "author": "Ryu Test Author",
                    "narrator": "Local Test Voice",
                    "language": "en",
                    "genre": "Fantasy",
                },
                bitrate=128,
            )

            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)

            probe = subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(output)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            report = (probe.stderr or "") + "\n" + (probe.stdout or "")
            self.assertIn("Stage 7.4.3 Test Book", report)
            self.assertIn("Ryu Test Author", report)
            self.assertIn("Opening Chapter", report)
            self.assertIn("Final Chapter", report)
            self.assertIn("Chapter #0:0", report)
            self.assertIn("Chapter #0:1", report)
            self.assertRegex(report, r"Video: mjpeg.*attached pic|attached pic.*Video: mjpeg")

            # FFmpeg must be able to decode a sample from the final packaged file.
            decode = subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error",
                    "-i", str(output), "-map", "0:a:0", "-t", "0.25",
                    "-f", "null", "-",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            self.assertEqual(decode.returncode, 0, decode.stderr)


if __name__ == "__main__":
    unittest.main()
