from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.chapters.detector import Chapter
from app.chapters.dialogue import dialogue_segments
from app.chapters.speaker_segmentation import segment_chapter_speakers
from app.ui import premium_v2_host as host


class DialogueCatalogueAndScanCacheTests(unittest.TestCase):
    def test_character_studio_dialogue_rows_use_same_source_spans_as_production(self):
        text = (
            "Mira looked up.\n"
            "“Who are you?” she asked.\n\n"
            "—I am Ren.\n\n"
            "'Then let us go,' Mira replied.\n\n"
            "The room became quiet."
        )
        chapter = Chapter(1, "Opening", text)
        production = [
            (row.start, row.end)
            for row in segment_chapter_speakers(chapter)
            if row.kind != "narration"
        ]
        character_studio = [(row.start, row.end) for row in dialogue_segments(chapter)]
        self.assertEqual(character_studio, production)
        self.assertEqual(len(character_studio), 3)

    def test_multi_speaker_saved_assignment_is_visible_and_conflicts_are_not_confirmed(self):
        text = "“We should leave,” Mira said."
        chapter = Chapter(1, "Opening", text)
        start = text.index("“")
        end = len(text)
        chapter.dialogue_assignments = [{
            "start": start, "end": end, "text": text[start:end],
            "speakers": ["Mira", "Ren"], "source": "manual",
        }]
        rows = dialogue_segments(chapter)
        self.assertEqual(len(rows), 1)
        self.assertTrue({"Mira", "Ren"}.issubset({item[0] for item in rows[0].suggestions}))

        chapter.dialogue_assignments.append({
            "start": start, "end": end, "text": text[start:end],
            "speakers": ["Tara"], "source": "manual",
        })
        conflicted = dialogue_segments(chapter)
        self.assertEqual(len(conflicted), 1)
        self.assertNotEqual(conflicted[0].suggested_speaker, "Tara")

    def test_models_inventory_refresh_is_cached_and_force_refreshes(self):
        bridge = host.PremiumV2Bridge.__new__(host.PremiumV2Bridge)
        builder = Mock(side_effect=[[{"model_id": "qwen"}], [{"model_id": "piper"}]])
        with patch("app.tts.model_registry.build_inventory", builder):
            first = bridge._models_list({})
            second = bridge._models_list({})
            refreshed = bridge._models_list({"force_refresh": True})
        self.assertEqual(first, second)
        self.assertEqual(first, [{"model_id": "qwen"}])
        self.assertEqual(refreshed, [{"model_id": "piper"}])
        self.assertEqual(builder.call_count, 2)

    def test_sound_catalog_scan_is_cached_and_import_style_refresh_bypasses_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bridge = host.PremiumV2Bridge.__new__(host.PremiumV2Bridge)
            app_root = root / "app"
            audio_root = app_root / "Audio Library"
            audio_root.mkdir(parents=True)
            bundled_root = root / "bundle"
            (bundled_root / "assets" / "starter_audio").mkdir(parents=True)
            first_file = audio_root / "first.wav"
            first_file.write_bytes(b"first")
            with (
                patch.object(host, "app_root", return_value=app_root),
                patch.object(sys, "_MEIPASS", str(bundled_root), create=True),
                patch(
                    "app.audio.library.metadata_for",
                    side_effect=lambda path: {
                        "role": "music", "category": "fantasy", "title": Path(path).stem
                    },
                ),
            ):
                first = bridge._sound_catalog({})
                second_file = audio_root / "second.wav"
                second_file.write_bytes(b"second")
                cached = bridge._sound_catalog({})
                refreshed = bridge._sound_catalog({"force_refresh": True})

            self.assertEqual(len(first), 1)
            self.assertEqual(len(cached), 1)
            self.assertEqual(len(refreshed), 2)


if __name__ == "__main__":
    unittest.main()
