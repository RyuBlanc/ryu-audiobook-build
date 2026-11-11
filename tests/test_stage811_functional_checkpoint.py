from __future__ import annotations

import threading
import unittest
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.tts.cast_provider import CastAwareProvider
from app.tts.manager import GenerationManager
from app.ui import premium_v2_host as host


class FunctionalCheckpoint20261111Tests(unittest.TestCase):
    def test_unassigned_dialogue_uses_global_fallback_not_narrator(self):
        router = CastAwareProvider(
            narrator_provider=SimpleNamespace(),
            narrator_voice="Narrator",
            profiles={},
            assignments={},
            unassigned_voice="Unassigned Character",
        )
        router._speakers_for = Mock(return_value=([], "single", ""))

        parts = router.split_for_cast('“No assigned speaker.”', "Narrator")

        self.assertEqual(parts, [("No assigned speaker.", "Unassigned Character")])

    def test_explicit_character_assignment_beats_global_fallback(self):
        router = CastAwareProvider(
            narrator_provider=SimpleNamespace(),
            narrator_voice="Narrator",
            profiles={},
            assignments={"mira": "Mira Voice"},
            unassigned_voice="Unassigned Character",
        )
        router._speakers_for = Mock(return_value=(["Mira"], "single", ""))

        parts = router.split_for_cast('“I am Mira.”', "Narrator")

        self.assertEqual(parts, [("I am Mira.", "Mira Voice")])

    def test_cancel_preview_signals_qwen_provider_without_waiting(self):
        cancel_event = threading.Event()
        provider = SimpleNamespace(request_cancel=Mock())
        row = {"job_id": "preview-1", "type": "voice-preview", "state": "running"}
        bridge = SimpleNamespace(
            _jobs_lock=threading.RLock(),
            _jobs={"preview-1": row},
            _generators={},
            _preview_cancel_events={"preview-1": cancel_event},
            _preview_providers={"preview-1": provider},
            _import_cancel_events={},
            _analysis_cancel_events={},
        )

        def update(job_id, **changes):
            bridge._jobs[job_id].update(changes)
            return dict(bridge._jobs[job_id])

        bridge._job_update = Mock(side_effect=update)
        result = host.PremiumV2Bridge._job_cancel(bridge, {"job_id": "preview-1"})

        self.assertTrue(cancel_event.is_set())
        provider.request_cancel.assert_called_once_with()
        self.assertEqual(result["state"], "cancel_requested")
        self.assertEqual(result["stage"], "Cancelling voice synthesis")

    def test_generation_progress_keeps_narration_and_package_percent_separate(self):
        started = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        bridge = SimpleNamespace(
            _jobs_lock=threading.RLock(),
            _jobs={"generation-1": {"started_at": started}},
            _generation_progress_timing={},
        )

        def update(job_id, **changes):
            bridge._jobs[job_id].update(changes)
            return dict(bridge._jobs[job_id])

        bridge._job_update = Mock(side_effect=update)
        with patch(
            "app.ui.premium_v2_host.time.monotonic",
            side_effect=[10.0, 11.0, 12.0, 13.0, 14.0, 15.0],
        ):
            host.PremiumV2Bridge._generation_progress(
                bridge, "generation-1", 0, 23, 0, "plan:2000:0:8"
            )
            host.PremiumV2Bridge._generation_progress(
                bridge, "generation-1", 1, 23, 0, "chunk-start:1/8"
            )
            for completed, work in ((1, 250), (2, 500), (3, 750), (4, 1000)):
                host.PremiumV2Bridge._generation_progress(
                    bridge, "generation-1", 1, 23, work,
                    f"chunk:{completed}/8:{work}/2000",
                )
            self.assertIsNone(bridge._jobs["generation-1"].get("eta_seconds"))
            # Three usable samples are collected only after the first chunk
            # (which includes model warm-up) has been excluded.
            host.PremiumV2Bridge._generation_progress(
                bridge, "generation-1", 1, 23, 1250, "chunk:5/8:1250/2000"
            )
            self.assertIsNotNone(bridge._jobs["generation-1"].get("eta_seconds"))
            self.assertIn("measured throughput", bridge._jobs["generation-1"].get("generation_eta_basis", ""))

            host.PremiumV2Bridge._generation_progress(
                bridge, "generation-1", 23, 23, 2000,
                "chapter-complete:8/8:1420.500:1420.500",
            )
            self.assertEqual(
                bridge._jobs["generation-1"]["generated_audio_duration_seconds"],
                1420.5,
            )
            host.PremiumV2Bridge._generation_progress(
                bridge, "generation-1", 23, 23, 2000, "m4b-packaging"
            )
            self.assertEqual(bridge._jobs["generation-1"]["progress"], 100)
            self.assertEqual(bridge._jobs["generation-1"]["packaging_progress_percent"], 0)
            host.PremiumV2Bridge._generation_progress(
                bridge, "generation-1", 23, 23, 2000, "m4b-package:1/4:Encoded chapter index"
            )
            self.assertEqual(bridge._jobs["generation-1"]["progress"], 100)
            self.assertEqual(bridge._jobs["generation-1"]["packaging_progress_percent"], 25)
            self.assertEqual(bridge._jobs["generation-1"]["packaging_completed_steps"], 1)
            self.assertEqual(bridge._jobs["generation-1"]["packaging_total_steps"], 4)

    def test_completed_chapter_audio_duration_is_measured_from_wav_frames(self):
        with TemporaryDirectory() as temporary:
            chapter_dir = Path(temporary) / "chapter"
            chunks = chapter_dir / "chunks"
            chunks.mkdir(parents=True)
            for name, seconds in (("00001.wav", 2.0), ("00002.wav", 3.5)):
                path = chunks / name
                with wave.open(str(path), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(24000)
                    audio.writeframes(b"\x00\x00" * int(24000 * seconds))
            (chunks / "broken.wav").write_bytes(b"not a wav")
            measured = GenerationManager._measure_chapter_audio_seconds(chapter_dir)
            self.assertEqual(measured, 5.5)

    def test_saved_qwen_profile_preview_resolves_exact_saved_record(self):
        saved_profile = SimpleNamespace(
            name="Novel SLASHDØG Ikuse Tobio",
            provider="qwen-character",
            qwen_mode="design",
            qwen_prompt="Saved profile prompt",
            qwen_seed=3471,
            voice_id="Ryan",
            sample_path=None,
        )
        bridge = SimpleNamespace(_find_profile=Mock(return_value=saved_profile))

        resolved = host.PremiumV2Bridge._preview_profile_from_payload(
            bridge, {"profile_name": saved_profile.name}, {}
        )

        self.assertIs(resolved, saved_profile)
        bridge._find_profile.assert_called_once_with(saved_profile.name)
        self.assertEqual(resolved.qwen_mode, "design")
        self.assertEqual(resolved.qwen_prompt, "Saved profile prompt")
        self.assertEqual(resolved.qwen_seed, 3471)

    def test_profile_load_notification_does_not_create_plain_text_toast(self):
        adapter = (Path(__file__).resolve().parents[1] / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("options.toast !== false", adapter)
        self.assertIn(
            "Generate a fresh preview before playback or assignment.', false, {toast:false}",
            adapter,
        )

    def test_unassigned_default_is_global_and_generation_acknowledgement_is_two_click(self):
        adapter = (Path(__file__).resolve().parents[1] / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        backend = (Path(__file__).resolve().parents[1] / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("voice/unassigned_character_profile", backend)
        self.assertIn("scope", backend)
        self.assertIn("Save for All Series and Books", adapter)
        self.assertIn("Some characters are still pending profile assigning.", adapter)
        self.assertIn("Press OK, then click Generate full audiobook again to continue.", adapter)
        self.assertIn("productionUnassignedAcknowledgementKey !== acknowledgementKey", adapter)

    def test_narrator_only_remains_available_with_character_profiles(self):
        adapter = (Path(__file__).resolve().parents[1] / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        backend = (Path(__file__).resolve().parents[1] / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("narrator_only_eligible = narrator_ready", backend)
        self.assertNotIn("if (narratorOnly && configuredCharacterVoiceCount > 0)", adapter)
        self.assertIn("state[\"narrator_only_generation\"] = enabled", backend)

    def test_qwen_preview_starts_at_zero_and_progress_is_completed_segment_based(self):
        adapter = (Path(__file__).resolve().parents[1] / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        backend = (Path(__file__).resolve().parents[1] / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("stage='Loading voice model', progress=0", backend)
        self.assertIn("actual_percent = min(95, max(0, round(95 * current / max(1, total))))", backend)
        self.assertIn("Loading voice model · 0%", adapter)
        self.assertIn("preview_completed_segments", backend)

    def test_progress_ring_is_a_true_circle_and_final_duration_is_not_guessed(self):
        adapter = (Path(__file__).resolve().parents[1] / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        backend = (Path(__file__).resolve().parents[1] / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("ring.style.aspectRatio = '1 / 1'", adapter)
        self.assertIn("ring.style.borderRadius = '50%'", adapter)
        self.assertIn("Measured full audiobook duration", adapter)
        self.assertIn("measured_duration_ms = int(_duration_ms(actual))", backend)
        self.assertIn('"output_duration_seconds": None', backend)


if __name__ == "__main__":
    unittest.main()
