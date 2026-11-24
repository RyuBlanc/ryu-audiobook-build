"""Direct integration coverage for simultaneous character voice synthesis."""

from __future__ import annotations

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from app.tts.audio_validation import wav_has_audible_content
from app.tts.multivoice import synthesize_voice_set


class _ToneProvider:
    def __init__(self, silent_voices=()):
        self.silent_voices = {str(value) for value in silent_voices}
        self.calls = []

    def is_qwen_voice(self, _voice):
        return False

    def synthesize(self, text, output_path, voice=None):
        self.calls.append((text, voice))
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = 24000
        frame_count = sample_rate // 3
        frequency = 0 if str(voice) in self.silent_voices else (440 if str(voice) == "Mira" else 660)
        frames = bytearray()
        for index in range(frame_count):
            value = 0 if frequency == 0 else int(9000 * math.sin(2 * math.pi * frequency * index / sample_rate))
            frames.extend(struct.pack("<h", value))
        with wave.open(str(output), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(sample_rate)
            audio.writeframes(bytes(frames))
        return output


class MultiVoiceSynthesisTests(unittest.TestCase):
    def test_two_character_voices_are_blended_into_one_audible_wav(self):
        provider = _ToneProvider()
        with tempfile.TemporaryDirectory(prefix="ryu-multivoice-blend-") as temporary:
            output = Path(temporary) / "chorus.wav"
            result = synthesize_voice_set(provider, "Stay here.", ["Mira", "Ren"], output)

            self.assertEqual(result, output)
            self.assertEqual(provider.calls, [("Stay here.", "Mira"), ("Stay here.", "Ren")])
            self.assertTrue(output.is_file())
            self.assertTrue(wav_has_audible_content(output))
            with wave.open(str(output), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getframerate(), 44100)
                self.assertGreater(audio.getnframes(), 0)

    def test_silent_child_voice_blocks_the_chorus_before_blending(self):
        provider = _ToneProvider(silent_voices={"Ren"})
        with tempfile.TemporaryDirectory(prefix="ryu-multivoice-silent-") as temporary:
            output = Path(temporary) / "must-not-complete.wav"
            with self.assertRaisesRegex(RuntimeError, "Ren.*silent audio"):
                synthesize_voice_set(provider, "Stay here.", ["Mira", "Ren"], output)

            self.assertEqual(provider.calls, [("Stay here.", "Mira"), ("Stay here.", "Ren")])
            self.assertFalse(output.exists(), "A silent child must not produce an accepted chorus WAV.")


if __name__ == "__main__":
    unittest.main()
