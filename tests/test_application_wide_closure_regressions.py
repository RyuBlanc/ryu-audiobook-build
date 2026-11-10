from __future__ import annotations

import threading
import unittest
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.tts.voice_profile import VoiceProfile
import app.tts.profile_provider as profile_provider
from app.tts.qwen_model_preference import normalize_qwen_backend_preference
from app.tts.providers.qwen_character import QwenCharacterProvider


ROOT = Path(__file__).resolve().parents[1]


class QwenBackendRegressionTests(unittest.TestCase):
    def test_qwen_backend_normalizer_rejects_provider_identifier(self):
        self.assertEqual(normalize_qwen_backend_preference("qwen-character"), "automatic")
        self.assertEqual(normalize_qwen_backend_preference(" QWEN-CHARACTER "), "automatic")
        self.assertEqual(normalize_qwen_backend_preference("cuda"), "cuda")
        self.assertEqual(normalize_qwen_backend_preference("cpu"), "cpu")

    def test_saved_qwen_profile_with_provider_id_uses_global_automatic(self):
        captured = {}

        class FakeQwenProvider:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with (
            patch.object(profile_provider, "QwenCharacterProvider", FakeQwenProvider),
            patch.object(profile_provider, "get_qwen_backend_preference", return_value="automatic"),
            patch.object(profile_provider, "get_qwen_model_preference", return_value="0.6b"),
            patch.object(
                profile_provider, "qwen_model_kinds_for_preference",
                return_value=("custom-0.6b", "base-0.6b"),
            ),
        ):
            profile = VoiceProfile(
                name="Legacy Qwen Anime Hero",
                provider="qwen-character",
                voice_id="Ryan",
                backend="qwen-character",
                qwen_mode="custom",
            )
            provider, voice = profile_provider.provider_from_profile(profile)

        self.assertIsInstance(provider, FakeQwenProvider)
        self.assertEqual(voice, "Ryan")
        self.assertEqual(captured["backend"], "automatic")
        self.assertEqual(captured["model_kind"], "custom-0.6b")

    def test_qwen_provider_never_passes_provider_id_as_compute_backend(self):
        provider = QwenCharacterProvider(
            voice_id="Ryan", backend="qwen-character", model_kind="custom-0.6b"
        )
        self.assertEqual(provider.backend, "automatic")

    def test_saved_qwen_cpu_profile_uses_current_global_automatic_backend(self):
        captured = {}

        class FakeQwenProvider:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with (
            patch.object(profile_provider, "QwenCharacterProvider", FakeQwenProvider),
            patch.object(profile_provider, "get_qwen_backend_preference", return_value="automatic"),
            patch.object(profile_provider, "get_qwen_model_preference", return_value="0.6b"),
            patch.object(
                profile_provider, "qwen_model_kinds_for_preference",
                return_value=("custom-0.6b", "base-0.6b"),
            ),
        ):
            profile = VoiceProfile(
                name="Saved on CPU-only PC",
                provider="qwen-character",
                voice_id="Ryan",
                backend="cpu",
                qwen_mode="custom",
            )
            profile_provider.provider_from_profile(profile)

        self.assertEqual(captured["backend"], "automatic")

    def test_explicit_qwen_cpu_preference_is_preserved(self):
        captured = {}

        class FakeQwenProvider:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with (
            patch.object(profile_provider, "QwenCharacterProvider", FakeQwenProvider),
            patch.object(profile_provider, "get_qwen_backend_preference", return_value="cpu"),
            patch.object(profile_provider, "get_qwen_model_preference", return_value="0.6b"),
            patch.object(
                profile_provider, "qwen_model_kinds_for_preference",
                return_value=("custom-0.6b", "base-0.6b"),
            ),
        ):
            profile = VoiceProfile(
                name="Saved Qwen CPU preference",
                provider="qwen-character",
                voice_id="Ryan",
                backend="automatic",
                qwen_mode="custom",
            )
            profile_provider.provider_from_profile(profile)

        self.assertEqual(captured["backend"], "cpu")

    def test_explicit_global_qwen_cpu_preference_is_preserved(self):
        captured = {}

        class FakeQwenProvider:
            def __init__(self, **kwargs):
                captured.update(kwargs)

        with (
            patch.object(profile_provider, "QwenCharacterProvider", FakeQwenProvider),
            patch.object(profile_provider, "get_qwen_backend_preference", return_value="cpu"),
            patch.object(profile_provider, "get_qwen_model_preference", return_value="0.6b"),
            patch.object(
                profile_provider, "qwen_model_kinds_for_preference",
                return_value=("custom-0.6b", "base-0.6b"),
            ),
        ):
            profile = VoiceProfile(
                name="Saved on GPU PC",
                provider="qwen-character",
                voice_id="Ryan",
                backend="cuda",
                qwen_mode="custom",
            )
            profile_provider.provider_from_profile(profile)

        self.assertEqual(captured["backend"], "cpu")


class CharacterAnalysisTaskCancellationTests(unittest.TestCase):
    def test_running_character_analysis_job_can_be_cancelled_from_task_manager(self):
        event = threading.Event()
        job = {"job_id": "analysis-1", "type": "character-analysis", "state": "running"}
        update = Mock(side_effect=lambda job_id, **changes: {**job, **changes})
        bridge = SimpleNamespace(
            _jobs_lock=RLock(),
            _jobs={"analysis-1": job},
            _generators={},
            _analysis_cancel_events={"analysis-1": event},
            _preview_cancel_events={},
            _import_cancel_events={},
            _job_update=update,
        )

        from app.ui.premium_v2_host import PremiumV2Bridge
        result = PremiumV2Bridge._job_cancel(bridge, {"job_id": "analysis-1"})

        self.assertTrue(event.is_set())
        self.assertEqual(result["state"], "cancel_requested")
        update.assert_called_once()
        self.assertEqual(update.call_args.kwargs["stage"], "Cancellation requested")

    def test_task_manager_offers_cancel_for_character_analysis_jobs(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function backgroundGenerationJobActions(")
        end = adapter.index("let backendJobFilter", start)
        section = adapter[start:end]
        self.assertIn(
            "const canCancelAnalysis = String(job.type || '').toLowerCase() === 'character-analysis';",
            section,
        )
        self.assertIn("(canCancelAnalysis && ['queued','running'].includes(state))", section)
        self.assertIn("!canCancelAnalysis", section)


if __name__ == "__main__":
    unittest.main()
