from __future__ import annotations

import math
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.tts.audio_validation import wav_has_audible_content
from app.tts.expression import classify_expression, expression_temperature, reference_style
from app.tts.pacing import pause_after_ms, sentence_units, split_for_pacing
from app.tts import qwen_character_worker


def _write_pcm_wav(path: Path, silent: bool) -> None:
    rate = 24000
    payload = bytearray()
    for index in range(rate):
        sample = 0 if silent else int(6000 * math.sin(2 * math.pi * 220 * index / rate))
        payload.extend(sample.to_bytes(2, byteorder="little", signed=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(bytes(payload))


class QwenSpeechQualityRegressionTests(unittest.TestCase):
    def test_silent_wav_is_rejected_but_voiced_wav_is_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            silent = Path(temporary) / "silent.wav"
            voiced = Path(temporary) / "voiced.wav"
            _write_pcm_wav(silent, True)
            _write_pcm_wav(voiced, False)
            self.assertFalse(wav_has_audible_content(silent))
            self.assertTrue(wav_has_audible_content(voiced))

    def test_two_period_hesitation_is_preserved_and_paused(self):
        self.assertEqual(sentence_units("yes.. then what"), ["yes..", "then what"])
        self.assertEqual(
            split_for_pacing("yes.. then what", max_chars=800, max_sentences=10),
            ["yes..", "then what"],
        )
        self.assertGreaterEqual(pause_after_ms("yes..", "natural"), 500)

    def test_two_period_hesitation_survives_quoted_dialogue_split(self):
        chunks = split_for_pacing("“Yes.. then what?”", max_chars=800, max_sentences=10)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].rstrip().endswith(".."))
        self.assertIn("then what?", chunks[1])

    def test_classifier_distinguishes_explicit_joy_from_general_warmth(self):
        self.assertEqual(classify_expression("She was overjoyed by the reunion."), "joyful")
        self.assertEqual(reference_style("joyful"), "warm")
        self.assertGreater(expression_temperature("joyful"), expression_temperature("warm"))

    def test_classifier_recognizes_suspicion_without_mapping_it_to_anger(self):
        self.assertEqual(classify_expression("He looked at the sealed letter suspiciously."), "suspicious")
        # Saved VoiceDesign/Base keeps one acoustic identity anchor; these
        # related emotional families therefore share the cautious reference
        # family but receive distinct generation sampling values.
        self.assertEqual(reference_style("suspicious"), "concerned")
        self.assertEqual(reference_style("angry"), "concerned")
        self.assertNotEqual(expression_temperature("suspicious"), expression_temperature("angry"))


    def test_customvoice_retries_silent_first_response_without_changing_speaker_or_style(self):
        audible = np.sin(np.linspace(0.0, 8.0 * math.pi, 4000, dtype=np.float32))
        silent = np.zeros(4000, dtype=np.float32)
        model = unittest.mock.Mock()
        model.generate_custom_voice.side_effect = [([silent], 24000), ([audible], 24000)]
        soundfile = type("SoundFile", (), {"write": staticmethod(lambda *args, **kwargs: None)})()
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            qwen_character_worker, "_worker_diagnostic"
        ), patch.dict("sys.modules", {"soundfile": soundfile}):
            output = Path(temporary) / "custom.wav"
            qwen_character_worker._generate_custom(
                model,
                {"text": "Speak this complete sentence.", "speaker": "Ryan",
                 "language": "English", "expression_style": "warm", "seed": 18},
                output,
            )
        self.assertEqual(model.generate_custom_voice.call_count, 2)
        first, second = [call.kwargs for call in model.generate_custom_voice.call_args_list]
        self.assertEqual(first["speaker"], "Ryan")
        self.assertEqual(first["speaker"], second["speaker"])
        self.assertEqual(first["instruct"], second["instruct"])
        self.assertEqual(first["temperature"], second["temperature"])

    def test_silent_member_in_a_qwen_batch_is_retried_individually(self):
        audible = np.sin(np.linspace(0.0, 8.0 * math.pi, 4000, dtype=np.float32))
        silent = np.zeros(4000, dtype=np.float32)
        calls = []

        def render_one(index, request):
            calls.append((index, dict(request)))
            return [audible], 24000

        def make_request(index):
            return {"text": f"Sentence {index}", "profile_id": "saved-profile",
                    "expression_style": "joyful", "seed": 20}

        with patch.object(qwen_character_worker, "_worker_diagnostic"):
            repaired = qwen_character_worker._repair_silent_batch_outputs(
                [audible, silent], 24000, [0, 1],
                ["First sentence.", "Second sentence."],
                make_request, render_one, "saved VoiceDesign batch regression"
            )
        self.assertEqual(len(repaired), 2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 1)
        self.assertEqual(calls[0][1]["profile_id"], "saved-profile")
        self.assertTrue(qwen_character_worker._waveform_has_audible_content(repaired[1]))

    def test_saved_voice_silent_output_retries_once_with_same_identity_and_style(self):
        audible = np.sin(np.linspace(0.0, 8.0 * math.pi, 4000, dtype=np.float32))
        calls = []

        def render(request):
            calls.append(dict(request))
            if len(calls) == 1:
                return [np.zeros(4000, dtype=np.float32)], 24000
            return [audible], 24000

        request = {"text": "The saved voice must speak this exact sentence.",
                   "seed": 42, "profile_id": "saved-profile",
                   "expression_style": "neutral"}
        with patch.object(qwen_character_worker, "_worker_diagnostic"):
            wavs, sr = qwen_character_worker._generate_with_silence_retry(
                render, request, request["text"], "saved VoiceDesign regression"
            )
        self.assertEqual(sr, 24000)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["profile_id"], calls[1]["profile_id"])
        self.assertEqual(calls[0]["expression_style"], calls[1]["expression_style"])
        self.assertEqual(calls[0]["seed"], 42)
        self.assertNotEqual(calls[1]["seed"], 42)
        self.assertTrue(qwen_character_worker._waveform_has_audible_content(wavs[0]))


if __name__ == "__main__":
    unittest.main()
