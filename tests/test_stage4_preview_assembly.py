"""Stage 4 preview isolation, cancellation, cleanup, and mix parity regressions."""
from __future__ import annotations

import tempfile
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.tts.preview import PreviewCancelledError, build_voice_preview
from app.tts.manager import GenerationManager
from app.ui import full_book_preview


def _write_wav(path: Path, seconds: float = 0.25) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * int(8000 * seconds))


class _Host:
    def __init__(self):
        self._preview_cancel_events = {}
        self._jobs_lock = threading.RLock()
        self.updates = []
    def _job_update(self, job_id, **kwargs):
        self.updates.append((job_id, kwargs))
        return kwargs


class PreviewAssemblyTests(unittest.TestCase):
    def _chapter_fixture(self, root: Path):
        source = root / "working_audio" / "001_Opening"
        _write_wav(source / "chunks" / "00001.wav")
        (source / "narration.json").write_text('{"narration_text":"A chapter.","title":"Opening"}', encoding="utf-8")
        (source / "chunk_manifest.json").write_text('{"chunks":[{"file":"00001.wav","text":"A chapter."}]}', encoding="utf-8")
        return source

    def test_full_book_preview_stages_chapters_and_passes_saved_fades(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = self._chapter_fixture(root)
            original = {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()}
            output = root / "preview.m4b"; host = _Host()
            state = {"background_audio_mode":"off", "background_audio_fade_in":4.5,
                     "background_audio_fade_out":7.0, "narration_speed":0.9,
                     "background_audio_volume":0.0, "ambience_audio_volume":0.0}
            def fake_assemble(chapter_dirs, output_path, *args, **kwargs):
                self.assertNotEqual(Path(chapter_dirs[0]).resolve(), source.resolve())
                self.assertTrue((Path(chapter_dirs[0]) / "chunks" / "00001.wav").is_file())
                # Simulate assembler side effects that must stay in staging.
                (Path(chapter_dirs[0]) / "chapter.m4a").write_bytes(b"assembled chapter")
                (Path(chapter_dirs[0]) / "concat.txt").write_text("temporary", encoding="utf-8")
                self.assertEqual(kwargs["background_audio_fade_in"], 4.5)
                self.assertEqual(kwargs["background_audio_fade_out"], 7.0)
                self.assertEqual(kwargs["narration_speed"], 0.9)
                Path(output_path).write_bytes(b"completed preview")
                return Path(output_path)
            with patch("app.audio.assembler.assemble_m4b", side_effect=fake_assemble), \
                 patch("app.audio.assembler._duration_ms", return_value=12_500):
                full_book_preview._render_full_book_preview(
                    host, "job", SimpleNamespace(folder=root), [source], ["Opening"],
                    output, "Title", "", {"title":"Title"}, 256, state, threading.Event())
            self.assertTrue(output.is_file())
            self.assertEqual(original, {p.relative_to(source).as_posix(): p.read_bytes() for p in source.rglob("*") if p.is_file()})
            self.assertFalse((source / "chapter.m4a").exists())
            self.assertFalse(any("ryu-preview-chapters-" in str(p) for p in root.rglob("*")))
            completed = next(row for _job, row in host.updates if row.get("state") == "completed")
            self.assertEqual(completed["result"]["duration_seconds"], 12.5)

    def test_full_book_preview_finds_saved_chapter_audio_by_stable_id_after_reorder(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio_root = root / "working_audio"
            stale_number_folder = audio_root / "001_Opening"
            moved_chapter_folder = audio_root / "003_Opening"
            for folder, chapter_id, number in (
                (stale_number_folder, "another-chapter", 1),
                (moved_chapter_folder, "stable-opening", 3),
            ):
                _write_wav(folder / "chunks" / "00001.wav")
                (folder / "narration.json").write_text(
                    __import__("json").dumps({
                        "chapter": number, "chapter_id": chapter_id,
                        "title": "Opening", "narration_text": "Opening narration.",
                    }),
                    encoding="utf-8",
                )
            chapter = SimpleNamespace(
                number=1, chapter_id="stable-opening", title="Opening",
                text="Opening narration.", skip_for_generation=False,
            )
            project = SimpleNamespace(folder=root, title="Book", chapters=[chapter])
            host = _Host()
            host._active_project = lambda: project
            host._new_job = lambda *args: "stable-preview"
            host._now = lambda: "2026-11-02T18:00:00+05:30"
            captured = {}

            class _Thread:
                def __init__(self, *, target, args, daemon, name):
                    captured.update(target=target, args=args, daemon=daemon, name=name)
                def start(self):
                    captured["started"] = True

            state = {"background_audio_mode": "off", "background_audio_enabled": False}
            with (
                patch("app.core.state.load_state", return_value=state),
                patch("app.core.paths.app_root", return_value=root / "app"),
                patch("threading.Thread", _Thread),
            ):
                result = full_book_preview.start_full_book_preview(host)

            self.assertTrue(captured["started"])
            self.assertEqual(result["state"], "running")
            self.assertEqual(captured["args"][3], [moved_chapter_folder])
            self.assertNotEqual(captured["args"][3], [stale_number_folder])

    def test_legacy_checkpoint_without_manifest_requires_matching_number_and_title(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            wrong = root / "working_audio" / "001_OtherChapter"
            _write_wav(wrong / "chunks" / "00001.wav")
            selected = SimpleNamespace(
                number=1, title="Opening", chapter_id="new-opening-id",
            )
            self.assertIsNone(full_book_preview._saved_chapter_audio_dir(
                root / "working_audio", selected
            ))

            right = root / "working_audio" / "001_Opening"
            _write_wav(right / "chunks" / "00001.wav")
            self.assertEqual(
                full_book_preview._saved_chapter_audio_dir(root / "working_audio", selected),
                right,
            )

    def test_full_book_preview_cancellation_discards_partial_output_and_staging(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = self._chapter_fixture(root)
            output = root / "preview.m4b"; host = _Host(); event = threading.Event()
            def fake_assemble(chapter_dirs, output_path, *args, **kwargs):
                Path(output_path).write_bytes(b"partial")
                event.set()
                kwargs["progress"](1, 1, "chapter-audio")
                return Path(output_path)
            with patch("app.audio.assembler.assemble_m4b", side_effect=fake_assemble):
                full_book_preview._render_full_book_preview(
                    host, "job", SimpleNamespace(folder=root), [source], ["Opening"],
                    output, "Title", "", {"title":"Title"}, 256, {}, event)
            self.assertFalse(output.exists())
            cancelled = next(row for _job, row in host.updates if row.get("state") == "cancelled")
            self.assertIn("cancelled", cancelled["stage"].lower())
            self.assertEqual(host._preview_cancel_events, {})
            self.assertFalse((source / "chapter.m4a").exists())

    def test_ffmpeg_failure_cleans_preview_output_and_retry_can_succeed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = self._chapter_fixture(root)
            output = root / "preview.m4b"; host = _Host(); state = {}
            with patch("app.audio.assembler.assemble_m4b", side_effect=RuntimeError("FFmpeg encoder failed")):
                full_book_preview._render_full_book_preview(
                    host, "failed", SimpleNamespace(folder=root), [source], ["Opening"],
                    output, "Title", "", {"title":"Title"}, 256, state, threading.Event())
            self.assertFalse(output.exists())
            self.assertEqual(next(row for job, row in host.updates if job=="failed").get("state"), "failed")
            def retry(chapter_dirs, output_path, *args, **kwargs):
                (Path(chapter_dirs[0]) / "chapter.m4a").write_bytes(b"staging only")
                Path(output_path).write_bytes(b"valid preview")
                return Path(output_path)
            with patch("app.audio.assembler.assemble_m4b", side_effect=retry), \
                 patch("app.audio.assembler._duration_ms", return_value=3_000):
                full_book_preview._render_full_book_preview(
                    host, "retry", SimpleNamespace(folder=root), [source], ["Opening"],
                    output, "Title", "", {"title":"Title"}, 256, state, threading.Event())
            self.assertTrue(output.is_file())
            self.assertFalse((source / "chapter.m4a").exists())
            self.assertEqual(next(row for job, row in host.updates if job=="retry").get("state"), "completed")

    def test_full_book_preview_uses_production_eligible_chapters_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            opening = self._chapter_fixture(root)
            ending = root / "working_audio" / "004_Final"
            _write_wav(ending / "chunks" / "00001.wav")
            (ending / "narration.json").write_text(
                '{"narration_text":"Final chapter.","title":"Final"}', encoding="utf-8"
            )
            (ending / "chunk_manifest.json").write_text(
                '{"chunks":[{"file":"00001.wav","text":"Final chapter."}]}', encoding="utf-8"
            )
            chapters = [
                SimpleNamespace(number=1, title="Opening", text="Opening narration", skip_for_generation=False),
                SimpleNamespace(number=2, title="Skipped chapter", text="Skipped narration", skip_for_generation=True),
                SimpleNamespace(number=3, title="Empty chapter", text="  ", skip_for_generation=False),
                SimpleNamespace(number=4, title="Final", text="Final narration", skip_for_generation=False),
            ]
            project = SimpleNamespace(folder=root, title="Book", chapters=chapters)
            host = _Host()
            host._active_project = lambda: project
            host._new_job = lambda *args: "eligible-preview"
            host._now = lambda: "2026-10-30T00:00:00+00:00"
            captured = {}

            class _Thread:
                def __init__(self, *, target, args, daemon, name):
                    captured.update(target=target, args=args, daemon=daemon, name=name)
                def start(self):
                    captured["started"] = True

            state = {"background_audio_mode": "off", "background_audio_enabled": False, "audio_bitrate": 256}
            with patch("app.core.state.load_state", return_value=state), \
                 patch("app.core.paths.app_root", return_value=root / "app"), \
                 patch("threading.Thread", _Thread):
                result = full_book_preview.start_full_book_preview(host)

            self.assertTrue(captured["started"])
            self.assertEqual(result["chapter_count"], 2)
            self.assertEqual([path.name for path in captured["args"][3]], ["001_Opening", "004_Final"])
            self.assertEqual(captured["args"][4], ["Opening", "Final"])
            self.assertEqual(result["reuses_saved_narration"], True)

    def test_voice_preview_cancellation_stops_before_normalization_and_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); output = root / "preview.wav"; event = threading.Event()
            class Provider:
                def synthesize(self, text, path, voice=None):
                    _write_wav(Path(path))
                    event.set()
            with patch("app.tts.preview._normalize") as normalize:
                with self.assertRaises(PreviewCancelledError):
                    build_voice_preview(
                        "This is a sentence. Another sentence.", Provider(), "voice", output,
                        narration_speed=1.0, pacing_profile="off", cancel_check=event.is_set)
            normalize.assert_not_called()
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob("ryu-preview-*")), [])


    def test_voice_preview_worker_removes_partial_sound_mix_on_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); preview_root = root / "Previews"; preview_root.mkdir()
            host = _Host()
            host._jobs_lock = threading.RLock()
            host._render_sound_design_preview = lambda source, job_id, state: (
                (preview_root / f"sound_mix_preview_{job_id}.m4a").write_bytes(b"partial"),
                (_ for _ in ()).throw(RuntimeError("FFmpeg mix failed")),
            )[1]
            profile = SimpleNamespace(name="Narrator", provider="local", voice_id="voice")
            def fake_build(_text, _provider, _voice, output, **kwargs):
                _write_wav(output, 0.3)
                return SimpleNamespace(output_path=output, voices_used=("voice",), segments=1,
                                       applied_rule_counts={})
            with patch("app.ui.premium_v2_host.app_root", return_value=root), \
                 patch("app.ui.premium_v2_host.provider_from_profile", return_value=(object(), "voice")), \
                 patch("app.ui.premium_v2_host.load_profiles", return_value=[]), \
                 patch("app.ui.premium_v2_host.build_voice_preview", side_effect=fake_build):
                from app.ui.premium_v2_host import PremiumV2Bridge
                PremiumV2Bridge._preview_worker(
                    host, "job", profile, "A preview sentence.", 10,
                    {"_include_sound_design_preview": True}, threading.Event())
            self.assertFalse((preview_root / "preview_job.wav").exists())
            self.assertFalse((preview_root / "sound_mix_preview_job.m4a").exists())
            failed = next(row for _job, row in host.updates if row.get("state") == "failed")
            self.assertIn("FFmpeg mix failed", failed["message"])


    def test_successful_export_keeps_reusable_chunks_for_mix_preview_and_sound_only_reassembly(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            audio_root = root / "working_audio"
            output = root / "final-book.m4b"
            chapters = [
                SimpleNamespace(number=1, title="MiraChapter", text="Mira spoke clearly."),
                SimpleNamespace(number=2, title="OtherChapter", text="A river crossed the valley."),
            ]
            old_track = root / "book-theme-old.wav"
            new_track = root / "book-theme-new.wav"
            synthesized = []
            assemblies = []

            class Provider:
                def synthesize(self, text, path, voice=None):
                    chapter_dir = Path(path).parent.parent.name
                    synthesized.append((chapter_dir, text))
                    _write_wav(Path(path), 0.25)

            def render(dictionary, music_path):
                manager = GenerationManager(
                    Provider(), "Narrator", chapters, audio_root,
                    pronunciation_dictionary=dictionary,
                    narration_speed=1.0, pacing_profile="off",
                    background_audio_path=music_path,
                    background_audio_volume=0.2,
                    chapter_bgm_strategy="same",
                )
                manager._run_body(output, "Test Book", "Author", None, {"title": "Test Book"})

            def fake_assemble(chapter_dirs, output_path, *args, **kwargs):
                assemblies.append({
                    "chapters": [Path(item).name for item in chapter_dirs],
                    "background_audio_path": kwargs.get("background_audio_path"),
                    "chapter_bgm_strategy": kwargs.get("chapter_bgm_strategy"),
                })
                destination = Path(output_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(b"M4B" * 1024)
                return destination

            first_dictionary = [
                {"written_form": "Mira", "spoken_form": "Mee-rah", "enabled": True}
            ]
            changed_dictionary = [
                {"written_form": "Mira", "spoken_form": "My-rah", "enabled": True}
            ]
            with patch("app.tts.manager.assemble_m4b", side_effect=fake_assemble):
                render(first_dictionary, old_track)

                first_chunk = audio_root / "001_MiraChapter" / "chunks" / "00001.wav"
                second_chunk = audio_root / "002_OtherChapter" / "chunks" / "00001.wav"
                self.assertTrue(first_chunk.is_file())
                self.assertTrue(second_chunk.is_file())
                self.assertTrue((audio_root / "001_MiraChapter" / "chunk_manifest.json").is_file())
                self.assertEqual(len(synthesized), 2)

                # A pronunciation change only invalidates the chapter containing
                # the changed written term; unrelated chapter audio remains reusable.
                # A changed sound-design selection is applied by a fresh M4B assembly.
                render(changed_dictionary, new_track)

            self.assertEqual(len(synthesized), 3)
            self.assertEqual([row[0] for row in synthesized[2:]], ["001_MiraChapter"])
            self.assertEqual(len(assemblies), 2)
            self.assertEqual(assemblies[0]["background_audio_path"], old_track)
            self.assertEqual(assemblies[1]["background_audio_path"], new_track)
            self.assertEqual(assemblies[1]["chapter_bgm_strategy"], "same")
            self.assertTrue(first_chunk.is_file())
            self.assertTrue(second_chunk.is_file())
            self.assertTrue(output.is_file())


    def test_sound_design_preview_reports_measured_duration_and_removes_intermediate_narration(self):
        from app.ui import premium_v2_host

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            preview_root = root / "Previews"
            preview_root.mkdir(parents=True)
            opening_cue = root / "opening-cue.wav"
            opening_cue.write_bytes(b"cue asset")
            updates_host = _Host()
            updates_host._jobs_lock = threading.RLock()
            updates_host._preview_cancel_events = {}

            def fake_build(_text, _provider, _voice, output_path, **kwargs):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"narration intermediate" * 100)
                return SimpleNamespace(
                    output_path=output_path,
                    voices_used=("selected-voice",),
                    segments=1,
                    applied_rule_counts={"Mira": 1},
                )

            def fake_concat(_first, _second, output_path, _bitrate):
                Path(output_path).write_bytes(b"opening plus narration" * 100)

            def fake_run(command):
                Path(str(command[-1])).write_bytes(b"rendered sound mix" * 200)

            updates_host._render_sound_design_preview = (
                lambda source, job_id, state:
                premium_v2_host.PremiumV2Bridge._render_sound_design_preview(
                    updates_host, source, job_id, state
                )
            )
            profile = SimpleNamespace(name="Saved Narrator", provider="piper", voice_id="selected-voice")
            state = {
                "_include_sound_design_preview": True,
                "background_audio_mode": "manual",
                "background_audio_enabled": True,
                "chapter_transition_sound": True,
                "opening_cue_path": str(opening_cue),
                "background_audio_volume": 0.0,
            }

            with patch.object(premium_v2_host, "provider_from_profile", return_value=(object(), "selected-voice")), \
                 patch.object(premium_v2_host, "load_profiles", return_value=[]), \
                 patch.object(premium_v2_host, "app_root", return_value=root), \
                 patch.object(premium_v2_host, "build_voice_preview", side_effect=fake_build), \
                 patch.object(premium_v2_host, "_read_pronunciation_store", return_value=[]), \
                 patch("app.audio.library.validate_saved_audio_paths"), \
                 patch("app.audio.assembler._concat_audio_files", side_effect=fake_concat), \
                 patch("app.audio.assembler._run", side_effect=fake_run), \
                 patch("app.audio.assembler._duration_ms", side_effect=[10_000, 10_700, 10_700]):
                premium_v2_host.PremiumV2Bridge._preview_worker(
                    updates_host, "mix-cleanup", profile, "Mira spoke.", 10, state, threading.Event()
                )

            completed = next(
                row for _job, row in updates_host.updates if row.get("state") == "completed"
            )
            self.assertEqual(completed["result"]["actual_duration_seconds"], 10.7)
            self.assertEqual(completed["result"]["output_path"],
                             str(preview_root / "sound_mix_preview_mix-cleanup.m4a"))
            self.assertTrue((preview_root / "sound_mix_preview_mix-cleanup.m4a").is_file())
            self.assertFalse((preview_root / "preview_mix-cleanup.wav").exists())
            self.assertFalse((preview_root / "sound-preview-opening-mix-cleanup.m4a").exists())

if __name__ == "__main__":
    unittest.main()
