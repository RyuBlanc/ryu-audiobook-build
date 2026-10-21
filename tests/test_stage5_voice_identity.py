"""Stage 5 regression tests for voice identity and synthesis cache signatures.

These tests guard narrator profile persistence and stale chunk invalidation."""
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


if __name__ == "__main__":
    unittest.main()
