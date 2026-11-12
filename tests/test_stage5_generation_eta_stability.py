"""Regression tests for measured audiobook generation progress and ETA stability."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
import wave
from unittest.mock import patch

from app.chapters.detector import Chapter
from app.tts.generator import generate_chapter
from app.ui import premium_v2_host as host
from app.ui.generation_page import _revise_monotonic_eta


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
        # The fourth chunk establishes a 60-second estimate at t=40. A
        # 100-second outlier expires that forecast but must not make the displayed
        # ETA jump back to 50 seconds. A fresh estimate is published only after
        # three further completed chunks confirm the overrun.
        clock_values = iter(
            (
                0.0,
                10.0, 10.0,
                20.0, 20.0,
                30.0, 30.0,
                40.0, 40.0,
                140.0, 140.0,
                150.0, 150.0,
                160.0, 160.0,
            )
        )
        with patch(
            "app.ui.premium_v2_host.time.monotonic",
            side_effect=lambda: next(clock_values),
        ):
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

            # The isolated slow call expires the old forecast. Do not publish
            # a replacement ETA from one chunk; retain the explicit overdue state.
            self._publish_chunk(bridge, 5, 5000, 100.0)
            self.assertEqual(bridge._jobs["eta-test"]["eta_seconds"], 0)
            self.assertEqual(
                bridge._jobs["eta-test"]["generation_eta_sample_count"], 4
            )

            # Two more completed chunks are still insufficient to rebase.
            self._publish_chunk(bridge, 6, 6000, 10.0)
            self.assertEqual(bridge._jobs["eta-test"]["eta_seconds"], 0)
            self._publish_chunk(bridge, 7, 7000, 10.0)

            recalibrated = bridge._jobs["eta-test"]
            self.assertEqual(recalibrated["eta_seconds"], 30)
            self.assertTrue(recalibrated["generation_eta_recalibrated"])
            self.assertIn("Three completed chunks", recalibrated["generation_eta_recalibration_reason"])
            self.assertAlmostEqual(
                recalibrated["generation_eta_seconds_per_text_unit"],
                0.01,
            )
            self.assertLessEqual(recalibrated["eta_seconds"], first_eta)

    def test_eta_never_increases_while_a_published_estimate_is_still_active(self):
        bridge = _ProgressHarness()
        clock_values = iter(
            (
                0.0,
                10.0, 10.0,
                20.0, 20.0,
                30.0, 30.0,
                40.0, 40.0,
                63.0, 63.0,
            )
        )
        with patch(
            "app.ui.premium_v2_host.time.monotonic",
            side_effect=lambda: next(clock_values),
        ):
            bridge._generation_progress("eta-test", 0, 10, 0, "plan:10000:0:10")
            self._publish_chunk(bridge, 1, 1000, 10.0)  # warm-up
            self._publish_chunk(bridge, 2, 2000, 10.0)
            self._publish_chunk(bridge, 3, 3000, 10.0)
            self._publish_chunk(bridge, 4, 4000, 10.0)

            initial_eta = bridge._jobs["eta-test"]["eta_seconds"]
            self.assertEqual(initial_eta, 60)

            # Twenty-three seconds later, the newly measured chunk is slower,
            # but its raw remaining-work estimate must not move the display
            # backwards; the published countdown continues from 60 seconds.
            self._publish_chunk(bridge, 5, 5000, 23.0)
            updated_eta = bridge._jobs["eta-test"]["eta_seconds"]
            self.assertEqual(updated_eta, 37)
            self.assertLess(updated_eta, initial_eta)
            self.assertEqual(
                bridge._jobs["eta-test"]["generation_eta_sample_count"], 4
            )

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

    def test_synthesis_timing_stops_before_validation_and_checkpoint_work(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "tts"
            / "generator.py"
        ).read_text(encoding="utf-8")
        single_start = source.index("synthesis_started = time.monotonic()")
        single_measured = source.index(
            "synthesis_seconds = max(0.001, time.monotonic() - synthesis_started)",
            single_start,
        )
        single_validation = source.index(
            "validate_and_commit(index, output, chunks[index])",
            single_start,
        )
        single_callback = source.index("on_chunk_timing(", single_validation)
        self.assertLess(single_measured, single_validation)
        self.assertLess(single_validation, single_callback)

        batch_start = source.index("batch_started = time.monotonic()")
        batch_measured = source.index(
            "batch_synthesis_seconds = max(0.001, time.monotonic() - batch_started)",
            batch_start,
        )
        batch_validation = source.index(
            "validate_and_commit(i, chunks_dir",
            batch_start,
        )
        batch_callback = source.index("on_chunk_timing(", batch_validation)
        self.assertLess(batch_measured, batch_validation)
        self.assertLess(batch_validation, batch_callback)

    def test_native_eta_never_increases_on_a_slow_chunk_and_smooths_faster_samples(self):
        eta, overruns, recalibrated = _revise_monotonic_eta(None, None, 100.0, 100.0, 0)
        self.assertEqual((eta, overruns, recalibrated), (100.0, 0, False))

        # A slower measured rate cannot push a still-active 100-second forecast
        # backwards after 23 seconds; the displayed value continues at 77s.
        eta, overruns, recalibrated = _revise_monotonic_eta(100.0, 100.0, 160.0, 123.0, 0)
        self.assertEqual((eta, overruns, recalibrated), (77.0, 0, False))

        # A faster measured rate shortens the countdown gradually, not abruptly.
        eta, overruns, recalibrated = _revise_monotonic_eta(77.0, 123.0, 30.0, 133.0, 0)
        self.assertAlmostEqual(eta, 57.75)
        self.assertEqual((overruns, recalibrated), (0, False))

    def test_native_eta_recalibrates_only_after_three_chunks_exceed_expired_forecast(self):
        eta, overruns, recalibrated = _revise_monotonic_eta(10.0, 0.0, 40.0, 20.0, 0)
        self.assertEqual((eta, overruns, recalibrated), (0.0, 1, False))
        eta, overruns, recalibrated = _revise_monotonic_eta(eta, 20.0, 40.0, 30.0, overruns)
        self.assertEqual((eta, overruns, recalibrated), (0.0, 2, False))
        eta, overruns, recalibrated = _revise_monotonic_eta(eta, 30.0, 40.0, 40.0, overruns)
        self.assertEqual((eta, overruns, recalibrated), (40.0, 0, True))

    def test_native_packaging_progress_does_not_fall_through_to_chapter_handler(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "app"
            / "ui"
            / "generation_page.py"
        ).read_text(encoding="utf-8")
        start = source.index('if message.startswith("m4b-package:"):')
        end = source.index('if message.startswith("m4b-complete"):', start)
        packaging_handler = source[start:end]
        self.assertIn("self.progress.setValue(self.progress.maximum())", packaging_handler)
        self.assertIn("return", packaging_handler)

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

    def test_dashboard_generation_eta_uses_the_live_measured_countdown(self):
        adapter = (
            Path(__file__).resolve().parents[1]
            / "assets"
            / "frontend"
            / "premium_v2_backend_adapter.js"
        ).read_text(encoding="utf-8")
        start = adapter.index("function refreshDashboardGeneration(jobs = [])")
        end = adapter.index("function audiobookPageActive()", start)
        dashboard = adapter[start:end]
        self.assertIn("const eta = productionJobEtaSeconds(job);", dashboard)
        self.assertNotIn("Number(job.eta_seconds)", dashboard)

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
        plan_start = source.index('if message.startswith("plan:"):')
        plan_end = source.index('if message.startswith("m4b-package:")', plan_start)
        plan = source[plan_start:plan_end]
        self.assertIn("self._eta_ema_sec_per_unit = None", plan)
        self.assertNotIn("self._estimated_generation_seconds", plan)

    def test_production_exposes_estimated_and_measured_audiobook_runtime(self):
        root = Path(__file__).resolve().parents[1]
        bridge = (root / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (root / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("estimated_listening_duration_seconds", bridge)
        self.assertIn("eligible_narration_word_count", bridge)
        self.assertIn("Estimated audiobook listening length", adapter)
        self.assertIn("Projected full audiobook runtime", adapter)
        self.assertIn("Measured full audiobook duration", adapter)
        self.assertIn("Valid synthesis chunks saved", adapter)
        self.assertIn("percentage advances when a chunk is validated", adapter)

    def test_progress_ring_remains_a_true_circle_and_reports_completed_workload(self):
        root = Path(__file__).resolve().parents[1]
        adapter = (root / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("ring.style.width = 'min(240px, 62vw)'", adapter)
        self.assertIn("ring.style.height = 'min(240px, 62vw)'", adapter)
        self.assertIn("ring.style.aspectRatio = '1 / 1'", adapter)
        self.assertIn("completed_normalized_text_workload", (root / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
