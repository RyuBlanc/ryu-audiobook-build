"""Stage 4 contract tests for selected voice profile and requested preview duration."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.ui import premium_v2_host


class VoicePreviewContractTests(unittest.TestCase):
    def test_preview_handler_preserves_selected_profile_and_all_supported_durations(self):
        profile = SimpleNamespace(name="Saved Narrator")
        project = SimpleNamespace(folder=Path("unused"), chapters=[])
        for seconds in (10, 20, 30, 45, 60):
            with self.subTest(seconds=seconds):
                thread = Mock()
                bridge = SimpleNamespace(
                    _active_project=lambda: project,
                    _assert_no_active_model_lifecycle=lambda _activity: None,
                    _find_profile=lambda name: profile if name == profile.name else None,
                    _new_job=Mock(return_value="preview-job"),
                    _job_update=Mock(),
                    _now=premium_v2_host.PremiumV2Bridge._now,
                    _preview_worker=premium_v2_host.PremiumV2Bridge._preview_worker,
                )
                with patch.object(premium_v2_host, "load_state", return_value={}), \
                     patch.object(premium_v2_host.threading, "Thread", return_value=thread) as thread_factory:
                    result = premium_v2_host.PremiumV2Bridge._voice_preview(
                        bridge,
                        {"profile_name": profile.name, "text": "A sufficiently long preview passage.",
                         "duration_seconds": seconds},
                    )
                self.assertEqual(result["duration_seconds"], seconds)
                self.assertEqual(result["profile_name"], profile.name)
                self.assertEqual(result["state"], "running")
                args = thread_factory.call_args.kwargs["args"]
                self.assertEqual(args[1], profile)
                self.assertEqual(args[3], seconds)
                thread.start.assert_called_once()

    def test_preview_handler_rejects_unsupported_duration_before_starting_worker(self):
        profile = SimpleNamespace(name="Saved Narrator")
        project = SimpleNamespace(folder=Path("unused"), chapters=[])
        bridge = SimpleNamespace(
            _active_project=lambda: project,
            _assert_no_active_model_lifecycle=lambda _activity: None,
            _find_profile=lambda _name: profile,
            _new_job=Mock(),
            _job_update=Mock(),
            _now=premium_v2_host.PremiumV2Bridge._now,
        )
        with patch.object(premium_v2_host, "load_state", return_value={}), \
             patch.object(premium_v2_host.threading, "Thread") as thread_factory:
            with self.assertRaisesRegex(ValueError, "10, 20, 30, 45, or 60"):
                premium_v2_host.PremiumV2Bridge._voice_preview(
                    bridge, {"profile_name": profile.name, "text": "A preview passage.",
                             "duration_seconds": 15}
                )
        thread_factory.assert_not_called()
        bridge._new_job.assert_not_called()

    def test_preview_worker_reports_requested_and_measured_duration(self):
        profile = SimpleNamespace(name="Saved Narrator")
        provider = object()
        updates = []

        def update(_job_id, **kwargs):
            updates.append(kwargs)
            return kwargs

        bridge = SimpleNamespace(_job_update=update)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def fake_build(_text, _provider, _voice, output_path, **kwargs):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"preview")
                return SimpleNamespace(output_path=output_path, voices_used=("voice-id",), segments=3)

            with patch.object(premium_v2_host, "provider_from_profile", return_value=(provider, "voice-id")) as provider_factory, \
                 patch.object(premium_v2_host, "load_profiles", return_value=[]), \
                 patch.object(premium_v2_host, "app_root", return_value=root), \
                 patch.object(premium_v2_host, "build_voice_preview", side_effect=fake_build) as build, \
                 patch("app.audio.assembler._duration_ms", return_value=30_400):
                premium_v2_host.PremiumV2Bridge._preview_worker(
                    bridge, "preview-job", profile, "A longer source passage.", 30, {}
                )

        provider_factory.assert_called_once_with(profile)
        self.assertEqual(build.call_args.kwargs["target_seconds"], 30)
        completed = next(item for item in updates if item.get("state") == "completed")
        self.assertEqual(completed["result"]["requested_duration_seconds"], 30)
        self.assertEqual(completed["result"]["actual_duration_seconds"], 30.4)
        self.assertEqual(completed["result"]["voices_used"], ["voice-id"])
        self.assertEqual(completed["result"]["segments"], 3)

    def test_preview_worker_fails_closed_when_duration_cannot_be_measured(self):
        profile = SimpleNamespace(name="Saved Narrator")
        provider = object()
        updates = []

        def update(_job_id, **kwargs):
            updates.append(kwargs)
            return kwargs

        bridge = SimpleNamespace(_job_update=update)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def fake_build(_text, _provider, _voice, output_path, **kwargs):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"not-a-readable-audio-file")
                return SimpleNamespace(output_path=output_path, voices_used=("voice-id",), segments=1)

            with patch.object(premium_v2_host, "provider_from_profile", return_value=(provider, "voice-id")):
                with patch.object(premium_v2_host, "load_profiles", return_value=[]):
                    with patch.object(premium_v2_host, "app_root", return_value=root):
                        with patch.object(premium_v2_host, "build_voice_preview", side_effect=fake_build):
                            with patch("app.audio.assembler._duration_ms", side_effect=RuntimeError("probe unavailable")):
                                premium_v2_host.PremiumV2Bridge._preview_worker(
                                    bridge, "preview-job", profile, "A longer source passage.", 30, {}
                                )

        self.assertFalse(any(item.get("state") == "completed" for item in updates))
        failed = next(item for item in updates if item.get("state") == "failed")
        self.assertIn("duration could not be measured", failed["message"])
        self.assertTrue(failed["recoverable"])

    def test_frontend_does_not_mark_unplayable_or_unmeasured_preview_ready(self):
        adapter = Path(__file__).resolve().parents[1] / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        source = adapter.read_text(encoding="utf-8")
        self.assertIn("Number.isFinite(actual) || actual <= 0", source)
        self.assertIn("return false;", source)
        self.assertIn("const playable = preparePreviewPlayback(job, Number(duration));", source)
        self.assertIn("if ($('previewState') && playable) $('previewState').textContent = 'Ready';", source)
        self.assertIn("Preview job completed without a valid measured audio duration", source)


if __name__ == "__main__":
    unittest.main()
