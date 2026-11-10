"""Browser-compatible playback derivative tests for finished M4B audiobooks."""
from __future__ import annotations

import math
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import Mock, patch

import imageio_ffmpeg
from PIL import Image

import app.audio.assembler as assembler
from app.audio.assembler import _duration_ms, assemble_m4b
from app.audio.playback import is_iso_bmff_file, prepare_audiobook_playback_source
from app.ui import premium_v2_host as host


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

    def test_final_cover_bearing_m4b_validates_chapters_tags_and_embedded_cover(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapter = root / "001_Opening"
            _write_wav(chapter / "chunks" / "00001.wav", seconds=0.8)
            cover = root / "cover.png"
            Image.new("RGB", (320, 320), (96, 24, 48)).save(cover, format="PNG")
            metadata = {
                "title": "Validated Final Book",
                "author": "Test Author",
                "narrator": "Test Narrator",
                "publisher": "Test Publisher",
                "series": "Validation Series",
                "series_number": "2",
                "language": "en",
                "year": "2026",
                "genre": "Audiobook",
            }

            # A real cover-bearing production output exercises the strict
            # metadata/chapter/attached-picture validation path. The existing
            # preview fixture is intentionally coverless and does not do this.
            output = assemble_m4b(
                chapter_dirs=[chapter],
                output_path=root / "validated-final.m4b",
                title=metadata["title"],
                author=metadata["author"],
                cover=cover,
                chapter_titles=["Opening"],
                metadata=metadata,
                bitrate=128,
            )

            self.assertTrue(is_iso_bmff_file(output))
            self.assertGreater(output.stat().st_size, 1024)
            report = assembler._ffmpeg_probe_report(output)
            self.assertIn("Chapter #", report)
            self.assertIn("Opening", report)
            self.assertIn("attached pic", report.casefold())

            # Read-back validation must fail closed for a mismatched chapter
            # title or metadata tag rather than silently accepting the file.
            with self.assertRaisesRegex(RuntimeError, "chapter 1 title is missing or incorrect"):
                assembler._validate_m4b_container(
                    output,
                    chapter_titles=["Incorrect Chapter"],
                    metadata=metadata,
                    cover=cover,
                )
            wrong_metadata = dict(metadata)
            wrong_metadata["title"] = "Different Book"
            with self.assertRaisesRegex(RuntimeError, "metadata tag 'title' is missing or incorrect"):
                assembler._validate_m4b_container(
                    output,
                    chapter_titles=["Opening"],
                    metadata=wrong_metadata,
                    cover=cover,
                )

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


class PlayerBridgeHarness:
    """Exercise the actual player backend bridge without constructing a Qt window."""

    _player_get_active = host.PremiumV2Bridge._player_get_active
    _player_position_save = host.PremiumV2Bridge._player_position_save

    def __init__(self, project):
        self.project = project
        self._project_summary = Mock(return_value={"readiness": {"ready": True}})
        preferences = {
            "player/playback_rate": 1.25,
            "player/playback_volume": 0.65,
        }
        self.settings = SimpleNamespace(
            sync=Mock(),
            value=lambda key, default=None: preferences.get(key, default),
        )


class AudiobookPlayerBridgeTests(unittest.TestCase):
    def _project(self, root: Path, output: Path):
        root.mkdir(parents=True, exist_ok=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        if not output.exists():
            output.write_bytes(b"finished audiobook fixture" * 8)
        chapter = SimpleNamespace(number=1, title="Opening")
        return SimpleNamespace(
            folder=root,
            title="Saved Player Book",
            chapters=[chapter],
        )

    def test_player_get_active_returns_playable_source_and_safe_preferences(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            output = root / "finished.mp3"
            project = self._project(root, output)
            state = {
                "output_path": str(output),
                "author": "Saved Author",
                "narrator": "Saved Narrator",
                "playback_position_seconds": 42.347,
            }
            bridge = PlayerBridgeHarness(project)

            with (
                patch.object(host, "list_projects", return_value=[project]),
                patch.object(host, "load_state", return_value=state),
                patch.object(host, "_read_audio_chapter_metadata", return_value=[]),
                patch.object(host, "is_iso_bmff_file", return_value=False),
            ):
                result = bridge._player_get_active({"folder": str(root)})

            self.assertEqual(result["title"], "Saved Player Book")
            self.assertEqual(result["author"], "Saved Author")
            self.assertEqual(result["narrator"], "Saved Narrator")
            self.assertEqual(result["output_path"], str(output.resolve()))
            self.assertEqual(result["file_url"], output.resolve().as_uri())
            self.assertEqual(result["playback_format"], "mp3")
            self.assertEqual(result["playback_position_seconds"], 42.347)
            self.assertEqual(result["playback_rate"], 1.25)
            self.assertEqual(result["playback_volume"], 0.65)
            self.assertEqual(result["chapters"], [{"number": 1, "title": "Opening"}])
            bridge.settings.sync.assert_called_once()

    def test_player_get_active_rebuilds_stale_playback_cache_without_touching_m4b(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            output = root / "finished.m4b"
            project = self._project(root, output)
            original_bytes = output.read_bytes()
            cached_playback = Path(temporary) / "cache" / "finished.mp3"
            cached_playback.parent.mkdir(parents=True)
            cached_playback.write_bytes(b"browser playback derivative" * 8)
            state = {
                "output_path": str(output),
                "playback_position_seconds": 18.0,
                "playback_output_path": str(cached_playback),
                "playback_source_path": str(output.resolve()),
                # A mismatched source size must invalidate the old playback cache.
                "playback_source_size": 1,
                "playback_source_mtime_ns": output.stat().st_mtime_ns,
            }
            embedded_chapters = [
                {"number": 1, "title": "Opening", "start_seconds": 0.0, "end_seconds": 12.5},
                {"number": 2, "title": "After the Storm", "start_seconds": 12.5, "end_seconds": 25.0},
            ]
            rebuilt = Path(temporary) / "cache" / "rebuilt.mp3"
            rebuilt.write_bytes(b"rebuilt browser playback derivative" * 8)
            bridge = PlayerBridgeHarness(project)

            with (
                patch.object(host, "list_projects", return_value=[project]),
                patch.object(host, "load_state", return_value=state),
                patch.object(host, "save_state") as save,
                patch.object(host, "_read_audio_chapter_metadata", return_value=embedded_chapters),
                patch.object(host, "is_iso_bmff_file", return_value=True),
                patch.object(host, "prepare_audiobook_playback_source", return_value=rebuilt) as prepare,
            ):
                result = bridge._player_get_active({"folder": str(root)})

            prepare.assert_called_once_with(output)
            save.assert_called_once_with(root, state)
            self.assertEqual(output.read_bytes(), original_bytes)
            self.assertEqual(state["playback_output_path"], str(rebuilt.resolve()))
            self.assertEqual(state["playback_source_path"], str(output.resolve()))
            self.assertEqual(state["playback_source_size"], output.stat().st_size)
            self.assertEqual(state["playback_source_mtime_ns"], output.stat().st_mtime_ns)
            self.assertEqual(result["file_url"], rebuilt.resolve().as_uri())
            self.assertEqual(result["source_file_url"], output.resolve().as_uri())
            self.assertEqual(result["playback_format"], "mp3")
            self.assertEqual(result["chapters"], embedded_chapters)

    def test_player_position_save_is_project_scoped_and_validates_finite_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            output = root / "finished.mp3"
            project = self._project(root, output)
            state = {"modified_at": "unchanged"}
            bridge = PlayerBridgeHarness(project)

            with (
                patch.object(host, "list_projects", return_value=[project]),
                patch.object(host, "load_state", return_value=state),
                patch.object(host, "save_state") as save,
            ):
                result = bridge._player_position_save({
                    "folder": str(root),
                    "position_seconds": 123.456,
                })

            self.assertEqual(result["position_seconds"], 123.46)
            self.assertEqual(state["playback_position_seconds"], 123.46)
            self.assertEqual(state["modified_at"], "unchanged")
            save.assert_called_once_with(root, state)

    def test_player_position_save_rejects_invalid_values_without_writing(self):
        invalid_values = (-1, float("nan"), float("inf"), True, 7 * 24 * 60 * 60 + 1)
        for value in invalid_values:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "project"
                output = root / "finished.mp3"
                project = self._project(root, output)
                bridge = PlayerBridgeHarness(project)
                with (
                    patch.object(host, "list_projects", return_value=[project]),
                    patch.object(host, "load_state", return_value={}),
                    patch.object(host, "save_state") as save,
                ):
                    with self.assertRaises(ValueError):
                        bridge._player_position_save({
                            "folder": str(root),
                            "position_seconds": value,
                        })
                save.assert_not_called()


class GenerationManagerFullBookIntegrationTests(unittest.TestCase):
    def test_generation_manager_creates_validated_multichapter_m4b_end_to_end(self):
        from app.chapters.detector import Chapter
        from app.tts.manager import GenerationManager

        class DeterministicProvider:
            def __init__(self):
                self.calls = []

            def synthesize(self, text, output_path, voice=None):
                self.calls.append((text, voice))
                _write_wav(Path(output_path), seconds=0.30)
                return output_path

            def close(self):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "finished" / "integration-book.m4b"
            cover = root / "cover.png"
            Image.new("RGB", (320, 320), (96, 24, 48)).save(cover, format="PNG")
            chapters = [
                Chapter(1, "Opening", "The first chapter begins. The road is quiet."),
                Chapter(2, "The Crossing", "The travellers reach the river. The bridge is old."),
            ]
            metadata = {
                "title": "Generation Manager Integration Book",
                "author": "Integration Test Author",
                "narrator": "Integration Narrator",
                "publisher": "Integration Publishing",
                "series": "Integration Series",
                "series_number": "1",
                "language": "en",
                "year": "2026",
                "genre": "Fantasy",
                "description": "End-to-end generation and final M4B validation fixture.",
            }
            provider = DeterministicProvider()
            summaries = []
            manager = GenerationManager(
                provider,
                "integration-narrator-voice",
                chapters,
                root / "working_audio",
                on_finished=summaries.append,
                narration_speed=1.0,
                pacing_profile="off",
                metadata=metadata,
                bitrate=128,
            )

            manager.start(
                output,
                metadata["title"],
                metadata["author"],
                cover,
                metadata=metadata,
            )
            manager._thread.join(timeout=30)

            self.assertFalse(manager._thread.is_alive(), "full-book generation worker did not finish")
            self.assertEqual(len(summaries), 1)
            summary = summaries[0]
            self.assertFalse(summary.cancelled)
            self.assertFalse(summary.packaging_failed)
            self.assertEqual(summary.chapters_total, 2)
            self.assertEqual(summary.chapters_completed, 2)
            self.assertEqual(summary.chapters_completed_numbers, [1, 2])
            self.assertEqual(summary.chapters_failed, [])
            self.assertEqual(Path(summary.output_path).resolve(), output.resolve())
            self.assertEqual(len(provider.calls), 2)

            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)
            self.assertTrue(is_iso_bmff_file(output))
            report = assembler._ffmpeg_probe_report(output)
            self.assertIn("Chapter #", report)
            self.assertIn("Opening", report)
            self.assertIn("The Crossing", report)
            self.assertIn("attached pic", report.casefold())
            assembler._validate_m4b_container(
                output,
                chapter_titles=["Opening", "The Crossing"],
                metadata=metadata,
                cover=cover,
            )
