"""Stage 5 regression tests for voice identity and synthesis cache signatures.

These tests guard narrator profile persistence, narrator-only and cast-aware cache invalidation, and stale chunk integrity."""
from pathlib import Path
import tempfile
import unittest

from app.tts.cast_provider import CastAwareProvider
from app.tts.voice_profile import VoiceProfile


class DummyProvider:
    def voices(self):
        return ["narrator"]

    def synthesize(self, text, output_path, voice=None):
        return output_path


class VoiceIdentitySignatureTests(unittest.TestCase):
    def test_narrator_profile_changes_invalidate_cast_generation_signature(self):
        provider = DummyProvider()
        base = VoiceProfile("Narrator", "piper", "en_US-amy-medium", model_id="piper")
        first = CastAwareProvider(provider, base.voice_id, {}, {}, narrator_profile=base)
        changed = VoiceProfile("Narrator", "kokoro", "af_heart", model_id="kokoro")
        second = CastAwareProvider(provider, changed.voice_id, {}, {}, narrator_profile=changed)
        self.assertNotEqual(first.generation_signature(), second.generation_signature())

    def test_assigned_profile_parameters_invalidate_generation_signature(self):
        provider = DummyProvider()
        narrator = VoiceProfile("Narrator", "piper", "amy", model_id="piper")
        cast_a = VoiceProfile("Character Voice", "qwen-character", "Ryan",
                              model_id="qwen3", qwen_prompt="warm", qwen_seed=10)
        cast_b = VoiceProfile("Character Voice", "qwen-character", "Ryan",
                              model_id="qwen3", qwen_prompt="stern", qwen_seed=10)
        first = CastAwareProvider(provider, "amy", {"Character Voice": cast_a},
                                  {"Hero": "Character Voice"}, narrator_profile=narrator)
        second = CastAwareProvider(provider, "amy", {"Character Voice": cast_b},
                                   {"Hero": "Character Voice"}, narrator_profile=narrator)
        self.assertNotEqual(first.generation_signature(), second.generation_signature())

    def test_reference_audio_replacement_at_same_path_invalidates_signature(self):
        provider = DummyProvider()
        with tempfile.TemporaryDirectory() as temp:
            sample = Path(temp) / "reference.wav"
            sample.write_bytes(b"reference A")
            profile = VoiceProfile("Clone", "chatterbox", "Clone", sample_path=str(sample))
            first = CastAwareProvider(provider, "amy", {"Clone": profile},
                                      {"Hero": "Clone"}, narrator_profile=VoiceProfile("Narrator", "piper", "amy"))
            signature_a = first.generation_signature()
            sample.write_bytes(b"reference B with different content")
            second = CastAwareProvider(provider, "amy", {"Clone": profile},
                                       {"Hero": "Clone"}, narrator_profile=VoiceProfile("Narrator", "piper", "amy"))
            self.assertNotEqual(signature_a, second.generation_signature())

    def test_missing_reference_is_part_of_signature_not_silently_ignored(self):
        provider = DummyProvider()
        profile = VoiceProfile("Clone", "chatterbox", "Clone", sample_path="missing-reference.wav")
        first = CastAwareProvider(provider, "amy", {"Clone": profile},
                                  {"Hero": "Clone"}, narrator_profile=VoiceProfile("Narrator", "piper", "amy"))
        signature_missing = first.generation_signature()
        profile.sample_path = None
        second = CastAwareProvider(provider, "amy", {"Clone": profile},
                                   {"Hero": "Clone"}, narrator_profile=VoiceProfile("Narrator", "piper", "amy"))
        self.assertNotEqual(signature_missing, second.generation_signature())

    def test_saved_profile_round_trips_voice_identity_and_synthesis_settings(self):
        from unittest.mock import patch
        from app.tts.voice_profile import load_saved_profiles, save_profiles

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "voices"
            profile = VoiceProfile(
                name="Persisted Qwen Character",
                provider="qwen-character",
                voice_id="Ryan",
                model_id="qwen3-customvoice",
                backend="cuda",
                language="English",
                qwen_mode="custom",
                qwen_prompt="warm, clear audiobook voice",
                qwen_seed=7741,
                qwen_profile_id="stable-profile-identity",
                authorized=True,
            )
            with patch("app.tts.voice_profile.voices_root", return_value=root):
                with patch("app.tts.voice_profile.builtin_voice_profiles", return_value=[]):
                    save_profiles([profile])
                    loaded = load_saved_profiles()

        self.assertEqual(len(loaded), 1)
        restored = loaded[0]
        self.assertEqual(restored.provider, profile.provider)
        self.assertEqual(restored.voice_id, profile.voice_id)
        self.assertEqual(restored.model_id, profile.model_id)
        self.assertEqual(restored.backend, profile.backend)
        self.assertEqual(restored.language, profile.language)
        self.assertEqual(restored.qwen_prompt, profile.qwen_prompt)
        self.assertEqual(restored.qwen_seed, profile.qwen_seed)
        self.assertEqual(restored.qwen_profile_id, profile.qwen_profile_id)

    def test_narrator_only_profile_changes_invalidate_generation_signature(self):
        from app.tts.profile_provider import ProfileBoundProvider
        provider = DummyProvider()
        first_profile = VoiceProfile("Narrator", "piper", "amy", model_id="piper", qwen_prompt="calm")
        second_profile = VoiceProfile("Narrator", "piper", "amy", model_id="piper", qwen_prompt="expressive")
        first = ProfileBoundProvider(provider, first_profile)
        second = ProfileBoundProvider(provider, second_profile)
        self.assertNotEqual(first.generation_signature(), second.generation_signature())

    def test_audiobook_generation_passes_the_selected_narrator_profile_into_cast_signature(self):
        host = (Path(__file__).resolve().parents[1] / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        cast = (Path(__file__).resolve().parents[1] / "app" / "tts" / "cast_provider.py").read_text(encoding="utf-8")
        self.assertIn("narrator_profile=profile", host)
        self.assertIn('"narrator_profile": self._profile_signature(self.narrator_profile)', cast)
        self.assertIn('"sample_audio_sha256"', cast)
        self.assertIn('"anchor_audio_sha256"', cast)


if __name__ == "__main__":
    unittest.main()
