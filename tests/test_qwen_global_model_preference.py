"""Tests for the app-wide Qwen model-size preference."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.tts.qwen_model_preference import qwen_model_kinds_for_preference
from app.tts.profile_provider import provider_from_profile
from app.tts.voice_profile import VoiceProfile
from app.tts.cast_provider import CastAwareProvider


class _DummyProvider:
    def voices(self):
        return ["narrator"]

    def synthesize(self, text, output_path, voice=None):
        return output_path


class QwenGlobalModelPreferenceTests(unittest.TestCase):
    def test_global_preference_maps_all_qwen_modes(self):
        self.assertEqual(
            qwen_model_kinds_for_preference("custom", "0.6b"),
            ("custom-0.6b", None),
        )
        self.assertEqual(
            qwen_model_kinds_for_preference("clone", "1.7b"),
            ("base-1.7b", None),
        )
        self.assertEqual(
            qwen_model_kinds_for_preference("design", "0.6b"),
            ("design-1.7b", "base-0.6b"),
        )
        self.assertEqual(
            qwen_model_kinds_for_preference("design-preview", "1.7b"),
            ("design-1.7b", None),
        )
        self.assertEqual(
            qwen_model_kinds_for_preference("custom", "auto"),
            (None, None),
        )

    def test_legacy_qwen_backend_values_are_migrated_and_persisted(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import app.tts.voice_profile as voice_profiles

        legacy_records = [
            {
                "name": "Legacy Provider Backend",
                "provider": "qwen-character",
                "voice_id": "Ryan",
                "backend": "qwen-character",
                "qwen_mode": "custom",
            },
            {
                "name": "Legacy Unknown Backend",
                "provider": "qwen-character",
                "voice_id": "Aiden",
                "backend": "not-a-compute-backend",
                "qwen_mode": "custom",
            },
            {
                "name": "Explicit CUDA Backend",
                "provider": "qwen-character",
                "voice_id": "Vivian",
                "backend": "cuda",
                "qwen_mode": "custom",
            },
        ]
        with tempfile.TemporaryDirectory() as temporary:
            profile_file = Path(temporary) / "voices.json"
            profile_file.write_text(json.dumps(legacy_records), encoding="utf-8")
            with patch.object(voice_profiles, "profiles_file", return_value=profile_file):
                loaded = voice_profiles.load_saved_profiles()

            by_name = {profile.name: profile for profile in loaded}
            self.assertEqual(by_name["Legacy Provider Backend"].backend, "automatic")
            self.assertEqual(by_name["Legacy Unknown Backend"].backend, "automatic")
            self.assertEqual(by_name["Explicit CUDA Backend"].backend, "cuda")
            self.assertTrue(all(profile.qwen_profile_id for profile in loaded))

            persisted = json.loads(profile_file.read_text(encoding="utf-8"))
            persisted_by_name = {record["name"]: record for record in persisted}
            self.assertEqual(persisted_by_name["Legacy Provider Backend"]["backend"], "automatic")
            self.assertEqual(persisted_by_name["Legacy Unknown Backend"]["backend"], "automatic")
            self.assertEqual(persisted_by_name["Explicit CUDA Backend"]["backend"], "cuda")
            self.assertTrue(all(record.get("qwen_profile_id") for record in persisted))

    def test_global_hardware_preference_and_low_memory_apply_to_auto_profiles(self):
        saved_profile = VoiceProfile(
            "Saved Hero", "qwen-character", "Ryan",
            model_id="custom-1.7b", qwen_mode="custom", backend="automatic",
        )
        with (
            patch("app.tts.profile_provider.get_qwen_model_preference", return_value="1.7b"),
            patch("app.tts.profile_provider.get_qwen_backend_preference", return_value="cpu"),
            patch("app.tts.profile_provider.get_qwen_low_memory_mode", return_value=True),
        ):
            provider, _voice = provider_from_profile(saved_profile)
        self.assertEqual(provider.backend, "cpu")
        self.assertTrue(provider.low_memory)

    def test_saved_profile_compute_backend_never_overrides_current_global_preference(self):
        # Profiles can move between the user's CPU-only laptop and a GPU PC.
        # Their portable voice identity must not carry a stale CPU/CUDA choice.
        for saved_backend in ("cpu", "cuda", "rocm", "xpu"):
            saved_profile = VoiceProfile(
                "Saved Hero", "qwen-character", "Ryan",
                model_id="custom-1.7b", qwen_mode="custom", backend=saved_backend,
            )
            with (
                self.subTest(saved_backend=saved_backend),
                patch("app.tts.profile_provider.get_qwen_model_preference", return_value="1.7b"),
                patch("app.tts.profile_provider.get_qwen_backend_preference", return_value="automatic"),
                patch("app.tts.profile_provider.get_qwen_low_memory_mode", return_value=False),
            ):
                provider, _voice = provider_from_profile(saved_profile)
                self.assertEqual(provider.backend, "automatic")

    def test_explicit_global_cpu_preference_still_applies_to_saved_gpu_profile(self):
        saved_profile = VoiceProfile(
            "Saved Hero", "qwen-character", "Ryan",
            model_id="custom-1.7b", qwen_mode="custom", backend="cuda",
        )
        with (
            patch("app.tts.profile_provider.get_qwen_model_preference", return_value="1.7b"),
            patch("app.tts.profile_provider.get_qwen_backend_preference", return_value="cpu"),
            patch("app.tts.profile_provider.get_qwen_low_memory_mode", return_value=False),
        ):
            provider, _voice = provider_from_profile(saved_profile)
        self.assertEqual(provider.backend, "cpu")

    def test_existing_custom_profile_uses_global_override_at_provider_creation(self):
        saved_profile = VoiceProfile(
            "Saved Hero", "qwen-character", "Ryan",
            model_id="custom-1.7b", qwen_mode="custom",
        )
        with patch("app.tts.profile_provider.get_qwen_model_preference", return_value="0.6b"):
            provider, voice = provider_from_profile(saved_profile)
        self.assertEqual(voice, "Ryan")
        self.assertEqual(provider.model_kind, "custom-0.6b")

    def test_existing_clone_profile_can_be_forced_to_larger_model(self):
        saved_profile = VoiceProfile(
            "Saved Clone", "qwen-character", "Clone",
            model_id="base-0.6b", qwen_mode="clone",
        )
        with patch("app.tts.profile_provider.get_qwen_model_preference", return_value="1.7b"):
            provider, _voice = provider_from_profile(saved_profile)
        self.assertEqual(provider.model_kind, "base-1.7b")

    def test_voice_design_keeps_design_model_but_global_selects_long_form_base(self):
        saved_profile = VoiceProfile(
            "Saved Designed Voice", "qwen-character", "Ryan",
            model_id="design-1.7b", qwen_mode="design",
        )
        with patch("app.tts.profile_provider.get_qwen_model_preference", return_value="0.6b"):
            provider, _voice = provider_from_profile(saved_profile)
        self.assertEqual(provider.model_kind, "design-1.7b")
        self.assertEqual(provider.long_form_model_kind, "base-0.6b")

    def test_qwen_cast_uses_restored_long_form_chunk_limits(self):
        narrator = VoiceProfile("Narrator", "piper", "amy", model_id="piper")
        character = VoiceProfile(
            "Hero", "qwen-character", "Ryan", model_id="auto", qwen_mode="custom"
        )
        cast = CastAwareProvider(
            _DummyProvider(), "amy", {"Hero": character}, {"Hero": "Hero"},
            narrator_profile=narrator,
        )
        self.assertEqual(cast.recommended_chunk_chars, 2400)
        self.assertEqual(cast.recommended_chunk_sentences, 10)

    def test_global_preference_invalidates_cast_generation_signature(self):
        narrator = VoiceProfile("Narrator", "piper", "amy", model_id="piper")
        character = VoiceProfile(
            "Hero", "qwen-character", "Ryan", model_id="auto", qwen_mode="custom"
        )
        with patch("app.tts.cast_provider.get_qwen_model_preference", return_value="0.6b"):
            first = CastAwareProvider(
                _DummyProvider(), "amy", {"Hero": character}, {"Hero": "Hero"},
                narrator_profile=narrator,
            ).generation_signature()
        with patch("app.tts.cast_provider.get_qwen_model_preference", return_value="1.7b"):
            second = CastAwareProvider(
                _DummyProvider(), "amy", {"Hero": character}, {"Hero": "Hero"},
                narrator_profile=narrator,
            ).generation_signature()
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
