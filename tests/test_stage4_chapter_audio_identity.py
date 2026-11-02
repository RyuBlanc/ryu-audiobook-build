"""Stage 4 Step 4.2/4.7 — stable chapter identity protects audio assignments."""
from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.audio import assembler
from app.chapters.detector import Chapter
from app.chapters.editor import ChapterEditor
from app.core.project import Project
from app.ui import premium_v2_host as host


class StableChapterAudioIdentityTests(unittest.TestCase):
    def test_legacy_project_load_migrates_and_persists_stable_chapter_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "project.json").write_text(
                json.dumps({"title": "Identity Test", "source_file": None}),
                encoding="utf-8",
            )
            (folder / "chapters.json").write_text(
                json.dumps([
                    {"number": 1, "title": "Opening", "text": "First chapter."},
                    {"number": 2, "title": "Journey", "text": "Second chapter."},
                ]),
                encoding="utf-8",
            )
            legacy_overrides = {
                "1": {"rule": "custom", "path": "opening-theme.wav", "volume": 0.2},
                "2": {"rule": "none", "volume": 0.0},
            }
            (folder / "state.json").write_text(
                json.dumps({"chapter_bgm_overrides": legacy_overrides}),
                encoding="utf-8",
            )
            first_load = Project.load(folder)
            first_ids = [chapter.chapter_id for chapter in first_load.chapters]
            migrated_state = json.loads((folder / "state.json").read_text(encoding="utf-8"))
            migrated_overrides = migrated_state["chapter_bgm_overrides"]
            self.assertEqual(migrated_overrides[first_ids[0]], legacy_overrides["1"])
            self.assertEqual(migrated_overrides[first_ids[1]], legacy_overrides["2"])
            self.assertEqual(migrated_overrides["1"], legacy_overrides["1"])
            self.assertEqual(migrated_overrides["2"], legacy_overrides["2"])
            self.assertTrue(all(first_ids))
            self.assertEqual(len(set(first_ids)), 2)
            saved = json.loads((folder / "chapters.json").read_text(encoding="utf-8"))
            self.assertEqual([row["chapter_id"] for row in saved], first_ids)
            second_load = Project.load(folder)
            self.assertEqual([chapter.chapter_id for chapter in second_load.chapters], first_ids)
            self.assertEqual([chapter.number for chapter in second_load.chapters], [1, 2])

    def test_chapter_editor_reorder_and_split_preserve_and_create_ids(self):
        chapters = [
            Chapter(1, "Opening", "First paragraph.\n\nSecond paragraph."),
            Chapter(2, "Journey", "The journey begins."),
        ]
        first_id, second_id = chapters[0].chapter_id, chapters[1].chapter_id
        editor = ChapterEditor(chapters)
        editor.move(0, 1)
        self.assertEqual([chapter.chapter_id for chapter in editor.chapters], [second_id, first_id])
        editor.split(1, 1, "Second Part")
        self.assertEqual(editor.chapters[1].chapter_id, first_id)
        self.assertNotEqual(editor.chapters[2].chapter_id, first_id)
        self.assertNotEqual(editor.chapters[2].chapter_id, second_id)

    def test_chapter_editor_merge_keeps_leading_chapter_identity(self):
        first = Chapter(1, "Opening", "Opening narration.")
        second = Chapter(2, "Continuation", "Continuation narration.")
        first_id = first.chapter_id
        removed_id = second.chapter_id

        editor = ChapterEditor([first, second])
        editor.merge_with_next(0)

        self.assertEqual(len(editor.chapters), 1)
        self.assertEqual(editor.chapters[0].chapter_id, first_id)
        self.assertNotEqual(editor.chapters[0].chapter_id, removed_id)
        self.assertIn("Opening narration.", editor.chapters[0].text)
        self.assertIn("Continuation narration.", editor.chapters[0].text)

    def test_sound_chapter_bgm_get_migrates_legacy_number_keys_to_chapter_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            project = Project(
                "BGM Identity", folder,
                chapters=[Chapter(1, "Opening", "First."), Chapter(2, "Journey", "Second.")],
            )
            ids = [chapter.chapter_id for chapter in project.chapters]
            state = {
                "chapter_bgm_strategy": "custom",
                "background_audio_mode": "manual",
                "background_audio_enabled": True,
                "chapter_bgm_overrides": {
                    "1": {"rule": "none", "volume": 0.21},
                    "2": {"rule": "none", "volume": 0.32},
                },
            }
            bridge = SimpleNamespace(
                _active_project=Mock(return_value=project),
                _sound_catalog=Mock(return_value=[]),
            )
            with patch.object(host, "load_state", return_value=state), \
                 patch.object(host, "save_state") as save:
                result = host.PremiumV2Bridge._sound_chapter_bgm_get(bridge, {})
            self.assertTrue(set(ids).issubset(set(result["overrides"])))
            self.assertIn("1", result["overrides"])
            self.assertIn("2", result["overrides"])
            self.assertEqual(result["overrides"][ids[0]]["volume"], 0.21)
            self.assertEqual(result["overrides"][ids[1]]["volume"], 0.32)
            self.assertEqual([row["chapter_id"] for row in result["chapters"]], ids)
            save.assert_called_once()
            self.assertTrue(set(ids).issubset(set(state["chapter_bgm_overrides"])))
            self.assertIn("1", state["chapter_bgm_overrides"])
            self.assertIn("2", state["chapter_bgm_overrides"])

    def test_chapter_bgm_save_prefers_stable_id_when_display_number_is_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            track = folder / "theme.wav"
            track.write_bytes(b"test asset")
            project = Project(
                "BGM Identity", folder,
                chapters=[Chapter(1, "Current First", "First."), Chapter(2, "Current Second", "Second.")],
            )
            selected = project.chapters[1]
            state = {
                "chapter_bgm_strategy": "custom",
                "background_audio_mode": "manual",
                "background_audio_enabled": True,
                "chapter_bgm_overrides": {},
            }
            bridge = SimpleNamespace(
                _active_project=Mock(return_value=project),
                _sound_catalog=Mock(return_value=[{
                    "path": str(track.resolve()), "role": "music", "title": "Theme",
                }]),
                _now=Mock(return_value="2026-11-02T18:00:00+05:30"),
            )
            with patch.object(host, "load_state", return_value=state), patch.object(host, "save_state"):
                result = host.PremiumV2Bridge._sound_chapter_bgm_save(
                    bridge,
                    {
                        "chapter_id": selected.chapter_id, "number": 1,
                        "rule": "custom", "path": str(track), "volume": 0.27,
                        "start_offset": "immediate", "end_behavior": "fade_before_end",
                    },
                )
            self.assertEqual(result["number"], 2)
            self.assertEqual(result["chapter_id"], selected.chapter_id)
            self.assertIn(selected.chapter_id, state["chapter_bgm_overrides"])
            self.assertNotIn("1", state["chapter_bgm_overrides"])

    def test_generator_reuses_chapter_checkpoint_directory_after_reorder(self):
        from app.tts.generator import generate_chapter

        class RecordingProvider:
            recommended_chunk_chars = 1400
            recommended_chunk_sentences = 1

            def __init__(self):
                self.calls = 0

            def synthesize(self, text, output_path, voice=None):
                self.calls += 1
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(output_path), "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(22050)
                    stream.writeframes(b"\\x00\\x00" * 2205)
                return output_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "working_audio"
            provider = RecordingProvider()
            source_text = "A short chapter. Same voice."
            original = Chapter(1, "Opening", source_text, chapter_id="stable-opening")
            first = generate_chapter(original, provider, "Narrator", root,
                                      narration_speed=1.0, pacing_profile="off")
            original_dir = first.output_path
            calls_after_first = provider.calls
            moved = Chapter(2, "Opening", source_text, chapter_id="stable-opening")
            second = generate_chapter(moved, provider, "Narrator", root,
                                       narration_speed=1.0, pacing_profile="off")
            self.assertEqual(second.output_path, original_dir)
            self.assertEqual(provider.calls, calls_after_first)
            saved = json.loads((original_dir / "narration.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["chapter"], 2)
            self.assertEqual(saved["chapter_id"], "stable-opening")

    def test_assembler_resolves_chapter_bgm_by_identity_before_legacy_number(self):
        resolver = getattr(assembler, "_chapter_bgm_override_for", None)
        self.assertTrue(
            callable(resolver),
            "The final assembler must resolve chapter assignments by stable chapter identity.",
        )
        with tempfile.TemporaryDirectory() as temp:
            chapter_dir = Path(temp) / "001_Opening"
            chapter_dir.mkdir()
            (chapter_dir / "narration.json").write_text(
                json.dumps({"chapter": 1, "chapter_id": "stable-opening-id"}),
                encoding="utf-8",
            )
            overrides = {
                "stable-opening-id": {"rule": "custom", "path": "opening.wav"},
                "1": {"rule": "none"},
            }
            selected = resolver(chapter_dir, 1, overrides)
            self.assertEqual(selected["rule"], "custom")
            self.assertEqual(selected["path"], "opening.wav")


if __name__ == "__main__":
    unittest.main()
