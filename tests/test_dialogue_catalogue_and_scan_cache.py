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

    def _catalog_scan_bridge(self):
        bridge = host.PremiumV2Bridge.__new__(host.PremiumV2Bridge)
        bridge._jobs_lock = host.threading.RLock()
        bridge._catalog_scan_lock = host.threading.RLock()
        bridge._catalog_cache_lock = host.threading.RLock()
        bridge._catalog_scan_jobs = {}
        bridge._catalog_scan_generation = {"models": 0, "sound": 0}
        bridge._jobs = {}
        bridge._new_job = Mock(side_effect=lambda job_type, title, description: (
            bridge._jobs.setdefault(
                "scan-" + str(len(bridge._jobs) + 1),
                {"job_id": "scan-" + str(len(bridge._jobs) + 1),
                 "type": job_type, "state": "running"}
            )["job_id"]
        ))
        bridge._job_update = Mock()
        return bridge

    def test_models_inventory_cache_miss_queues_one_background_scan_and_keeps_stale_snapshot(self):
        bridge = self._catalog_scan_bridge()
        bridge._model_inventory_cache = [{"model_id": "cached"}]
        bridge._model_inventory_cache_at = 0
        builder = Mock(return_value=[{"model_id": "fresh"}])
        threads = []

        class DeferredThread:
            def __init__(self, target, args=(), **_kwargs):
                self.target, self.args = target, args
            def start(self):
                threads.append(self)

        with (
            patch("app.tts.model_registry.build_inventory", builder),
            patch.object(host.threading, "Thread", DeferredThread),
        ):
            first = bridge._models_list({})
            second = bridge._models_list({"force_refresh": True})
            self.assertEqual(first, [{"model_id": "cached"}])
            self.assertEqual(second, first)
            self.assertEqual(builder.call_count, 0, "A bridge read must never perform the cold filesystem scan.")
            self.assertEqual(len(threads), 1, "Concurrent refresh requests must share one scan.")
            threads[0].target(*threads[0].args)
            self.assertEqual(builder.call_count, 1)
        self.assertEqual(bridge._models_list({}), [{"model_id": "fresh"}])
        self.assertEqual(bridge._catalog_scan_jobs, {})
        self.assertIn("completed", [call.kwargs.get("state") for call in bridge._job_update.call_args_list])

    def test_sound_catalog_force_refresh_runs_off_dispatch_thread_and_preserves_snapshot_on_failure(self):
        bridge = self._catalog_scan_bridge()
        bridge._sound_catalog_cache = [{"path": "old.wav"}]
        bridge._sound_catalog_cache_at = 0
        scanner = Mock(side_effect=RuntimeError("simulated disk read failure"))
        bridge._build_sound_catalog = scanner
        threads = []

        class DeferredThread:
            def __init__(self, target, args=(), **_kwargs):
                self.target, self.args = target, args
            def start(self):
                threads.append(self)

        with patch.object(host.threading, "Thread", DeferredThread):
            first = bridge._sound_catalog({"force_refresh": True})
            second = bridge._sound_catalog({"force_refresh": True})

        self.assertEqual(first, [{"path": "old.wav"}])
        self.assertEqual(second, first)
        self.assertEqual(scanner.call_count, 0, "Forced catalogue refresh must not scan in the caller/Qt thread.")
        self.assertEqual(len(threads), 1)
        threads[0].target(*threads[0].args)
        self.assertEqual(scanner.call_count, 1)
        self.assertEqual(bridge._sound_catalog_cache, [{"path": "old.wav"}])
        self.assertEqual(bridge._catalog_scan_jobs, {})
        self.assertIn("failed", [call.kwargs.get("state") for call in bridge._job_update.call_args_list])


if __name__ == "__main__":
    unittest.main()
