"""Regression tests for measured audiobook generation progress and ETA stability."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
import wave

from app.chapters.detector import Chapter
from app.tts.generator import generate_chapter
from app.ui import premium_v2_host as host


class _ProgressHarness:
    _generation_progress = host.PremiumV2Bridge._generation_progress
    _now = staticmethod(host.PremiumV2Bridge._now)

    def __init__(self) -> None:
        started = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        self._jobs = {
            "eta-test": {
                "job_id": "eta-test",
                "type": "audiobook-generation",
                "state": "running",
                "started_at": started,
                "progress": 0,
            }
        }
        self._generation_progress_timing = {}

    def _job_update(self, job_id: str, **changes):
        row = self._jobs[job_id]
        row.update(changes)
        row["updated_at"] = self._now()
        return dict(row)


class _WavProvider:
    recommended_chunk_chars = 32
    recommended_chunk_sentences = 1
    recommended_batch_size = 1

    def synthesize(self, text, output_path, voice=None):
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(22050)
            handle.writeframes(bytes(8820))
        return target


class Stage5GenerationEtaStabilityTests(unittest.TestCase):
    def _publish_chunk(self, bridge, chunk_number, completed_work, seconds):
        bridge._generation_progress(
            "eta-test",
            1,
            10,
            completed_work,
            f"chunk:{chunk_number}/10:{completed_work}/10000",
        )
        bridge._generation_progress(
            "eta-test",
            1,
            10,
            completed_work,
            (
                f"chunk-timing:1000:{seconds:.6f}:{completed_work}:"
                f"10000:{chunk_number}:10"
            ),
        )

    def test_eta_uses_measured_chunk_times_and_resists_one_slow_outlier(self):
        bridge = _ProgressHarness()
        bridge._generation_progress("eta-test", 0, 10, 0, "plan:10000:0:10")

        # The first TTS call is excluded because it can include cold model load.
        self._publish_chunk(bridge, 1, 1000, 10.0)
        self.assertIsNone(bridge._jobs["eta-test"].get("eta_seconds"))

        self._publish_chunk(bridge, 2, 2000, 10.0)
        self._publish_chunk(bridge, 3, 3000, 10.0)
        self._publish_chunk(bridge, 4, 4000, 10.0)

        first_eta = bridge._jobs["eta-test"]["eta_seconds"]
        self.assertEqual(first_eta, 60)
        self.assertIsNotNone(bridge._jobs["eta-test"].get("eta_updated_at"))
        self.assertEqual(bridge._jobs["eta-test"]["generation_eta_sample_count"], 3)

        # A single 10x slower chunk must not make a multi-hour ETA jump.
        self._publish_chunk(bridge, 5, 5000, 100.0)
        second_eta = bridge._jobs["eta-test"]["eta_seconds"]
        self.assertEqual(second_eta, 50)
        self.assertLessEqual(second_eta, first_eta)

    def test_synthesis_timer_is_reported_by_generate_chapter_for_each_real_call(self):
        chapter = Chapter(
            1,
            "Timing fixture",
            "The first sentence has enough words. "
            "The second sentence also has enough words. "
            "The third sentence completes the fixture.",
        )
        observed = []

        with tempfile.TemporaryDirectory() as temporary:
            result = generate_chapter(
                chapter,
                _WavProvider(),
                "Narrator",
                Path(temporary) / "working-audio",
                narration_speed=1.0,
                pacing_profile="off",
                on_chunk_timing=lambda completed, work, seconds: observed.append(
                    (completed, work, seconds)
                ),
            )

        self.assertEqual(result.chunks_completed, result.chunks_total)
        self.assertGreaterEqual(len(observed), 2)
        self.assertEqual(
            [row[0] for row in observed],
            list(range(1, len(observed) + 1)),
        )
        self.assertTrue(all(work > 0 and seconds > 0 for _, work, seconds in observed))

    def test_frontend_counts_eta_down_between_measured_chunks(self):
        adapter = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "frontend"
            / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("function productionJobEtaSeconds(job)")
        end = adapter.index("function syncProductionPreviewChapterSelector()", start)
        eta = adapter[start:end]
        self.assertIn("job.eta_updated_at", eta)
        self.assertIn("Date.now() - measuredAt", eta)
        self.assertIn("value - liveSeconds", eta)

    def test_native_generation_page_uses_measured_samples_not_elapsed_fallback(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "ui"
            / "generation_page.py"
        ).read_text(encoding="utf-8")
        self.assertIn('elif message.startswith("chunk-timing:"):', source)
        self.assertIn("if len(ordered) >= 3:", source)
        self.assertIn("waiting for the active chunk", source)
        self.assertNotIn("fallback_rate = work_done / elapsed", source)

    def test_production_exposes_estimated_and_measured_audiobook_runtime(self):
        root = Path(__file__).resolve().parents[1]
        bridge = (root / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (root / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("estimated_listening_duration_seconds", bridge)
        self.assertIn("eligible_narration_word_count", bridge)
        self.assertIn("Estimated audiobook listening length", adapter)
        self.assertIn("Projected full audiobook runtime", adapter)
        self.assertIn("Measured full audiobook duration", adapter)

    def test_progress_ring_remains_a_true_circle_and_reports_completed_workload(self):
        root = Path(__file__).resolve().parents[1]
        adapter = (root / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("ring.style.width = 'min(240px, 62vw)'", adapter)
        self.assertIn("ring.style.height = 'min(240px, 62vw)'", adapter)
        self.assertIn("ring.style.aspectRatio = '1 / 1'", adapter)
        self.assertIn("completed_normalized_text_workload", (root / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
