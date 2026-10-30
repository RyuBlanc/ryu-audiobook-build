"""Stage 8.2.8 sound-design full-book mix preview acceptance checks."""
from __future__ import annotations

import unittest
from pathlib import Path


class Stage828SoundDesignPreviewTests(unittest.TestCase):
    def test_full_book_mix_preview_is_registered_as_a_background_job(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        worker = Path("app/ui/full_book_preview.py").read_text(encoding="utf-8")
        self.assertIn('"sound.preview_book": self._sound_preview_book', source)
        self.assertIn('"sound.preview_book": True', source)
        self.assertIn('def _sound_preview_book(self, _payload: dict[str, Any])', source)
        self.assertIn("start_full_book_preview(self)", source)
        self.assertIn("def start_full_book_preview(host)", worker)
        self.assertIn('host._new_job(\n        "sound-design-book-preview"', worker)
        self.assertIn('name="RyuFullBookSoundPreview"', worker)

    def test_full_book_mix_preview_reuses_saved_narration_and_validates_all_chapters(self):
        source = Path("app/ui/full_book_preview.py").read_text(encoding="utf-8")
        self.assertIn('audio_root = project.folder / "working_audio"', source)
        self.assertIn('A full-book mix preview needs saved narration audio for every chapter.', source)
        self.assertIn('reuses_saved_narration', source)
        # The assembler mutates chapter directories, so preview must use disposable staged copies.
        self.assertIn("staged_dirs, output, title, author, cover, chapter_titles", source)
        self.assertIn("shutil.copytree(source_dir, target_dir)", source)
        self.assertIn('with tempfile.TemporaryDirectory(prefix="ryu-preview-chapters-") as staging:', source)

    def test_full_book_preview_uses_the_production_sound_design_assignments(self):
        source = Path("app/ui/full_book_preview.py").read_text(encoding="utf-8")
        for setting in (
            "background_audio_mode=", "background_audio_path=", "background_audio_volume=",
            "ambience_audio_path=", "ambience_audio_volume=", "chapter_transition_sound=",
            "opening_cue_path=", "page_turn_cue_path=",
            "ending_cue_path=", "chapter_bgm_overrides=", "chapter_bgm_strategy=",
        ):
            self.assertIn(setting, source)

    def test_sound_design_preview_button_requests_full_book_mix_not_short_voice_preview(self):
        source = Path("assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        branch = source[source.index("soundButton.id === 'soundPreviewBook'"):]
        branch = branch[:branch.index("\n          }\n        } catch", 0)]
        self.assertIn("call('sound.preview_book')", branch)
        self.assertIn("full-book mix preview", branch.lower())
        self.assertNotIn("call('production.preview'", branch)


    def test_scene_transition_is_not_a_fixed_cue_assignment(self):
        assembler = Path("app/audio/assembler.py").read_text(encoding="utf-8")
        host = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        preview = Path("app/ui/full_book_preview.py").read_text(encoding="utf-8")

        self.assertNotIn("if index > 1 and scene_transition_cue_path", assembler)
        library = Path("app/audio/library.py").read_text(encoding="utf-8")
        start = library.index("def validate_saved_audio_paths(")
        end = library.index("def resolve_cue_track(", start)
        self.assertNotIn("scene_transition_cue_path", library[start:end])
        self.assertIn("scene_transition_cue_path: Path | str | None = None", assembler)
        self.assertIn('if slot not in {"opening", "chapter", "closing"}:', host)
        self.assertNotIn("scene_transition_cue_path=Path(state[", host)
        self.assertNotIn("scene_transition_cue_path=Path(str(state[", preview)

    def test_chapter_bgm_mixer_preserves_timeline_and_applies_offset_and_fades(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from app.audio import assembler

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            narration = root / "chapter.m4a"
            track = root / "music.wav"
            output = root / "mixed.m4a"
            narration.write_bytes(b"narration")
            track.write_bytes(b"music")

            def fake_run(args):
                Path(args[-1]).write_bytes(b"x" * 2048)

            with patch.object(assembler, "_duration_ms", side_effect=[20_000, 20_000]), \
                 patch.object(assembler, "_run", side_effect=fake_run) as run:
                result = assembler._mix_chapter_bgm(
                    narration, track, output, 0.2, fade_in=1.5, fade_out=2.5,
                    start_offset_ms=10_000, bitrate="192k",
                )

            self.assertEqual(result, output)
            self.assertTrue(output.is_file())
            args = run.call_args.args[0]
            filters = args[args.index("-filter_complex") + 1]
            self.assertIn("adelay=10000|10000", filters)
            self.assertIn("afade=t=in:st=10.000:d=1.500", filters)
            self.assertIn("afade=t=out:st=17.500:d=2.500", filters)
            self.assertIn("duration=first", filters)
            self.assertEqual(args[args.index("-t") + 1], "20.000")


    def test_after_first_paragraph_waits_for_every_audio_chunk_of_a_long_paragraph(self):
        import json
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from app.audio import assembler

        with TemporaryDirectory() as temporary:
            chapter_dir = Path(temporary)
            chunk_dir = chapter_dir / "chunks"
            chunk_dir.mkdir()
            first, second, boundary, next_chunk = (
                chunk_dir / "00001.wav", chunk_dir / "00002.wav",
                chunk_dir / "00003.wav", chunk_dir / "00004.wav"
            )
            for path in (first, second, boundary, next_chunk):
                path.write_bytes(b"chunk")
            (chapter_dir / "narration.json").write_text(
                json.dumps({"narration_text": "A long first paragraph with several sentences. " * 12 +
                            "\n\nA second paragraph starts here."}),
                encoding="utf-8",
            )
            (chapter_dir / "chunk_manifest.json").write_text(json.dumps({"chunks": [
                {"file": first.name, "text": "A long first paragraph with several sentences."},
                {"file": second.name, "text": "The first paragraph continues with more sentences."},
                {"file": boundary.name, "text": "The first paragraph ends here.\n\n"},
                {"file": next_chunk.name, "text": "A second paragraph starts here."},
            ]}), encoding="utf-8")
            with patch.object(assembler, "_duration_ms", side_effect=[1200, 900, 1400]):
                offset = assembler._chapter_first_paragraph_offset_ms(chapter_dir)
            self.assertEqual(offset, 3500)


    def test_legacy_multi_paragraph_audio_without_saved_boundary_is_not_guessed(self):
        import json
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from app.audio import assembler

        with TemporaryDirectory() as temporary:
            chapter_dir = Path(temporary)
            chunk_dir = chapter_dir / "chunks"
            chunk_dir.mkdir()
            chunk = chunk_dir / "00001.wav"
            chunk.write_bytes(b"chunk")
            (chapter_dir / "narration.json").write_text(
                json.dumps({"narration_text":"First paragraph.\n\nSecond paragraph."}),
                encoding="utf-8",
            )
            (chapter_dir / "chunk_manifest.json").write_text(json.dumps({"chunks":[
                {"file":chunk.name,"text":"First paragraph. Second paragraph."}
            ]}), encoding="utf-8")
            with patch.object(assembler, "_duration_ms") as probe:
                self.assertIsNone(assembler._chapter_first_paragraph_offset_ms(chapter_dir))
            probe.assert_not_called()


    def test_generation_plan_preserves_paragraph_boundary_when_chapter_bgm_requests_it(self):
        import json
        from tempfile import TemporaryDirectory
        from types import SimpleNamespace
        from app.tts.generator import prepare_chapter_plan

        class PlanningProvider:
            recommended_chunk_chars = 1400
            recommended_chunk_sentences = 8
            split_on_expression_change = False

            def split_for_cast(self, text, voice, dialogue_assignments=None):
                return [(text, voice)]

        chapter_text = (
            "The first paragraph contains its opening sentence. "
            "It contains its closing sentence.\n\n"
            "The second paragraph must be in a different TTS chunk."
        )
        chapter = SimpleNamespace(number=1, title="Paragraph boundary", text=chapter_text, dialogue_assignments=[])
        with TemporaryDirectory() as temporary:
            plan = prepare_chapter_plan(
                chapter, PlanningProvider(), "narrator", Path(temporary),
                preserve_paragraph_boundaries=True,
            )
            chunks = list(plan.chunks_with_voices)
            self.assertEqual(len(chunks), 2)
            self.assertTrue(chunks[0][0].endswith("\n\n"))
            self.assertTrue(chunks[1][0].startswith("The second paragraph"))
            manifest = json.loads((plan.chapter_dir / "chunk_manifest.json").read_text(encoding="utf-8"))
            self.assertTrue(manifest["chunks"][0]["text"].endswith("\n\n"))

    def test_chapter_bgm_boundary_policy_is_limited_to_custom_chapter_based_assignments(self):
        from types import SimpleNamespace
        from app.tts.manager import GenerationManager

        chapter = SimpleNamespace(number=1)
        custom = GenerationManager(
            provider=object(), voice="narrator", chapters=[chapter], project_audio_root=Path("."),
            chapter_bgm_strategy="custom",
            chapter_bgm_overrides={"1": {"rule":"custom", "start_offset":"after_first_paragraph"}},
        )
        immediate = GenerationManager(
            provider=object(), voice="narrator", chapters=[chapter], project_audio_root=Path("."),
            chapter_bgm_strategy="custom",
            chapter_bgm_overrides={"1": {"rule":"custom", "start_offset":"immediate"}},
        )
        same = GenerationManager(
            provider=object(), voice="narrator", chapters=[chapter], project_audio_root=Path("."),
            chapter_bgm_strategy="same",
            chapter_bgm_overrides={"1": {"rule":"custom", "start_offset":"after_first_paragraph"}},
        )
        self.assertTrue(custom._chapter_requires_paragraph_boundary(chapter))
        self.assertFalse(immediate._chapter_requires_paragraph_boundary(chapter))
        self.assertFalse(same._chapter_requires_paragraph_boundary(chapter))

    def test_after_first_paragraph_rejects_old_merged_chunk_instead_of_guessing(self):
        import json
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from app.audio import assembler

        with TemporaryDirectory() as temporary:
            chapter_dir = Path(temporary)
            chunk_dir = chapter_dir / "chunks"
            chunk_dir.mkdir()
            chunk = chunk_dir / "00001.wav"
            chunk.write_bytes(b"chunk")
            (chapter_dir / "narration.json").write_text(
                json.dumps({"narration_text":"First paragraph.\n\nSecond paragraph."}),
                encoding="utf-8",
            )
            (chapter_dir / "chunk_manifest.json").write_text(json.dumps({"chunks":[
                {"file":chunk.name,"text":"First paragraph.\n\nSecond paragraph."}
            ]}), encoding="utf-8")
            with patch.object(assembler, "_duration_ms") as probe:
                self.assertIsNone(assembler._chapter_first_paragraph_offset_ms(chapter_dir))
            probe.assert_not_called()

    def test_zero_volume_chapter_bgm_does_not_reencode_narration(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from app.audio import assembler

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            narration = root / "chapter.m4a"
            track = root / "music.wav"
            output = root / "mixed.m4a"
            narration.write_bytes(b"narration")
            track.write_bytes(b"music")
            with patch.object(assembler, "_run") as run:
                result = assembler._mix_chapter_bgm(narration, track, output, 0.0)
            self.assertEqual(result, narration)
            run.assert_not_called()
            self.assertFalse(output.exists())


    def test_chapter_bgm_override_uses_original_chapter_number_after_skips(self):
        import json
        from tempfile import TemporaryDirectory
        from app.audio.assembler import _chapter_number_for_bgm

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            chapter = root / "004_Chapter_Four"
            chapter.mkdir()
            (chapter / "narration.json").write_text(
                json.dumps({"chapter": 4}), encoding="utf-8"
            )
            self.assertEqual(_chapter_number_for_bgm(chapter, 2), 4)

            fallback_chapter = root / "007_Chapter_Seven"
            fallback_chapter.mkdir()
            self.assertEqual(_chapter_number_for_bgm(fallback_chapter, 3), 7)

    def test_full_book_preview_reports_measured_duration(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from app.ui import full_book_preview

        class Host:
            def __init__(self):
                self.updates = []

            def _job_update(self, job_id, **changes):
                self.updates.append((job_id, changes))

        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "preview.m4b"
            host = Host()

            def render(*args, **kwargs):
                target = Path(args[1])
                target.write_bytes(b"validated preview")
                return target

            with patch("app.audio.assembler.assemble_m4b", side_effect=render), \
                 patch("app.audio.assembler._duration_ms", return_value=12_345):
                full_book_preview._render_full_book_preview(
                    host, "job-1", object(), [], [], output, "Title", "", {}, 256, {}
                )

            final_update = host.updates[-1][1]
            self.assertEqual(final_update["state"], "completed")
            self.assertEqual(final_update["result"]["duration_seconds"], 12.345)
            self.assertTrue(output.is_file())

    def test_failed_full_book_preview_removes_partial_output(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from app.ui import full_book_preview

        class Host:
            def __init__(self):
                self.updates = []

            def _job_update(self, job_id, **changes):
                self.updates.append((job_id, changes))

        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "preview.m4b"
            host = Host()

            def failed_render(*args, **kwargs):
                Path(args[1]).write_bytes(b"partial")
                raise RuntimeError("FFmpeg failed during finalization")

            with patch("app.audio.assembler.assemble_m4b", side_effect=failed_render):
                full_book_preview._render_full_book_preview(
                    host, "job-2", object(), [], [], output, "Title", "", {}, 256, {}
                )

            self.assertFalse(output.exists())
            self.assertEqual(host.updates[-1][1]["state"], "failed")
            self.assertIn("FFmpeg failed", host.updates[-1][1]["message"])



    def test_missing_saved_sound_assets_fail_before_preview_or_generation(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from app.audio.library import validate_saved_audio_paths

        with TemporaryDirectory() as temporary:
            missing = Path(temporary) / "deleted-music.wav"
            with self.assertRaisesRegex(FileNotFoundError, "Saved book background music is missing"):
                validate_saved_audio_paths({"background_audio_path": str(missing)})
            with self.assertRaisesRegex(FileNotFoundError, "Saved custom BGM for chapter 4 is missing"):
                validate_saved_audio_paths({"chapter_bgm_overrides": {"4": {"rule": "custom", "path": str(missing)}}})
            with self.assertRaisesRegex(ValueError, "uses custom BGM but no track is saved"):
                validate_saved_audio_paths({"chapter_bgm_overrides": {"4": {"rule": "custom"}}})

    def test_explicit_missing_cue_does_not_silently_fall_back_to_another_track(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from app.audio.library import resolve_cue_track

        with TemporaryDirectory() as temporary:
            missing = Path(temporary) / "deleted-opening-cue.wav"
            with self.assertRaisesRegex(FileNotFoundError, "Selected audiobook cue no longer exists"):
                resolve_cue_track("opening", selected_path=missing)


    def test_unassigned_fixed_cue_slot_never_falls_back_to_library_defaults(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from app.audio import assembler

        with TemporaryDirectory() as temporary:
            with patch("app.audio.library.resolve_cue_track") as resolve:
                result = assembler._resolve_cue_audio(
                    Path(temporary), "page", "library", 0, "mystery", None
                )
            self.assertIsNone(result)
            resolve.assert_not_called()

    def test_active_fixed_cues_are_probed_and_rejected_above_five_seconds(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from app.audio.library import validate_saved_audio_paths

        with TemporaryDirectory() as temporary:
            cue = Path(temporary) / "opening.wav"
            cue.write_bytes(b"cue")
            with patch("app.audio.library.probe_audio_duration_seconds", return_value=5.1):
                with self.assertRaisesRegex(ValueError, "Fixed cue clips must be 5 seconds or shorter"):
                    validate_saved_audio_paths({
                        "background_audio_mode": "manual",
                        "background_audio_enabled": True,
                        "opening_cue_path": str(cue),
                    })

    def test_voice_only_ignores_retained_inactive_audio_and_legacy_scene_path(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from app.audio.library import validate_saved_audio_paths

        with TemporaryDirectory() as temporary:
            missing = Path(temporary) / "deleted-audio.wav"
            validate_saved_audio_paths({
                "background_audio_mode": "off",
                "background_audio_enabled": False,
                "background_audio_path": str(missing),
                "background_audio_preferred_path": str(missing),
                "opening_cue_path": str(missing),
                "page_turn_cue_path": str(missing),
                "ending_cue_path": str(missing),
                "scene_transition_cue_path": str(missing),
                "chapter_bgm_strategy": "custom",
                "chapter_bgm_overrides": {"2": {"rule": "custom", "path": str(missing)}},
            })

    def test_preflight_checks_only_the_active_bgm_strategy(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from unittest.mock import patch
        from app.audio.library import validate_saved_audio_paths

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            book_track = root / "book.wav"
            chapter_track = root / "chapter.wav"
            book_track.write_bytes(b"book")
            chapter_track.write_bytes(b"chapter")
            missing_chapter = root / "deleted-chapter.wav"
            missing_book = root / "deleted-book.wav"
            with patch("app.audio.library.probe_audio_duration_seconds", return_value=30.0) as probe:
                validate_saved_audio_paths({
                    "background_audio_mode": "manual",
                    "background_audio_enabled": True,
                    "chapter_bgm_strategy": "same",
                    "background_audio_path": str(book_track),
                    "chapter_bgm_overrides": {"4": {"rule": "custom", "path": str(missing_chapter)}},
                })
                self.assertEqual([call.args[0] for call in probe.call_args_list], [book_track])
                probe.reset_mock()
                validate_saved_audio_paths({
                    "background_audio_mode": "manual",
                    "background_audio_enabled": True,
                    "chapter_bgm_strategy": "custom",
                    "background_audio_path": "",
                    "background_audio_preferred_path": str(missing_book),
                    "chapter_bgm_overrides": {"4": {"rule": "custom", "path": str(chapter_track)}},
                })
                self.assertEqual([call.args[0] for call in probe.call_args_list], [chapter_track])

    def test_chapter_bgm_end_behaviors_have_distinct_fade_policies(self):
        from app.audio.assembler import _chapter_bgm_fade_out

        self.assertEqual(_chapter_bgm_fade_out("fade_before_end", 4.0), 4.0)
        self.assertEqual(_chapter_bgm_fade_out("continue_to_transition", 4.0), 0.75)
        self.assertEqual(_chapter_bgm_fade_out("stop_immediately", 4.0), 0.0)
        self.assertEqual(_chapter_bgm_fade_out("fade_before_end", 99.0), 30.0)
        with self.assertRaisesRegex(ValueError, "Unsupported chapter BGM end behavior"):
            _chapter_bgm_fade_out("unknown", 3.0)

    def test_chapter_bgm_selection_activates_mixer_without_book_default(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = source.index("    def _sound_chapter_bgm_save(")
        end = source.index("    def _sound_cues_get(", start)
        handler = source[start:end]
        self.assertIn('state["background_audio_mode"] = "manual"', handler)
        assembler = Path("app/audio/assembler.py").read_text(encoding="utf-8")
        self.assertIn("chapter_bgm_strategy: str | None = None", assembler)
        self.assertIn('effective_bgm_strategy == "chapter-based"', assembler)
        self.assertIn('and effective_audio_mode == "manual"', assembler)
        self.assertIn(
            "chapter_bgm_strategy=chapter_bgm_strategy,",
            source,
        )



if __name__ == "__main__":
    unittest.main()
