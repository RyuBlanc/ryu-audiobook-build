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

from app.audio.assembler import assemble_m4b, _probe_audio_bitrate_kbps


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
                write_test_wav(chapter_dir / "chunks" / "00001.wav", seconds=8.0)
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
                    "publisher": "Ryu Test Press",
                    "series": "Dragon Archive",
                    "series_number": "3",
                    "language": "en",
                    "year": "2026",
                    "genre": "Fantasy",
                    "description": "Two chapter M4B metadata validation fixture",
                },
                bitrate=128,
            )

            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)
            # Production acceptance includes a measured encoded stream bitrate,
            # not merely the requested encoder setting.
            self.assertGreaterEqual(_probe_audio_bitrate_kbps(output), 128)

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
            self.assertRegex(report, r"Stream #\d+:\d+(?:\[[^\]]+\])?\(eng\): Audio:")
            from mutagen.mp4 import MP4
            tags = MP4(str(output)).tags or {}
            self.assertEqual(tags["----:com.apple.iTunes:narrator"][0].decode("utf-8"), "Local Test Voice")
            self.assertEqual(tags["----:com.apple.iTunes:publisher"][0].decode("utf-8"), "Ryu Test Press")
            self.assertEqual(tags["----:com.apple.iTunes:series"][0].decode("utf-8"), "Dragon Archive")
            self.assertEqual(tags["----:com.apple.iTunes:series_number"][0].decode("utf-8"), "3")
            self.assertEqual(tags["©day"][0], "2026")
            self.assertEqual(tags["©gen"][0], "Fantasy")
            self.assertEqual(tags["desc"][0], "Two chapter M4B metadata validation fixture")
            self.assertIn("Opening Chapter", report)
            self.assertIn("Final Chapter", report)
            self.assertIn("Chapter #0:0", report)
            self.assertIn("Chapter #0:1", report)
            report_lines = report.splitlines()
            stream_lines = [
                (index, line.strip())
                for index, line in enumerate(report_lines)
                if "stream #" in line.casefold()
            ]
            cover_stream_index = next(
                (
                    index for index, line in stream_lines
                    if "video:" in line.casefold() and "mjpeg" in line.casefold()
                ),
                None,
            )
            self.assertIsNotNone(cover_stream_index, report)
            next_stream_index = next(
                (index for index, _line in stream_lines if index > cover_stream_index),
                len(report_lines),
            )
            cover_stream_block = report_lines[cover_stream_index:next_stream_index]
            for key, expected in (("title", "Cover"), ("comment", "Cover Art"), ("mimetype", "image/jpeg")):
                actual = next(
                    (
                        line.split(":", 1)[1].strip()
                        for line in cover_stream_block
                        if ":" in line and line.split(":", 1)[0].strip().casefold() == key
                    ),
                    "",
                )
                self.assertEqual(actual.casefold(), expected.casefold(), cover_stream_block)
            chapter_ranges = re.findall(
                r"Chapter #\d+:\d+:\s*start\s+([0-9.]+),\s*end\s+([0-9.]+)",
                report,
            )
            self.assertEqual(len(chapter_ranges), 2, report)
            parsed_ranges = [(float(start), float(end)) for start, end in chapter_ranges]
            self.assertAlmostEqual(parsed_ranges[0][0], 0.0, delta=0.15)
            self.assertGreater(parsed_ranges[0][1], parsed_ranges[0][0])
            self.assertAlmostEqual(parsed_ranges[1][0], parsed_ranges[0][1], delta=1.5)
            self.assertGreater(parsed_ranges[1][1], parsed_ranges[1][0])

            # FFmpeg must be able to decode the complete primary audio stream from the final packaged file.
            decode = subprocess.run(
                [
                    imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error",
                    "-i", str(output), "-map", "0:a:0",
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
