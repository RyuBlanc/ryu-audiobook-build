"""Stage 3 regression coverage for expression, story effects, and multilingual pronunciation."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import wave

from app.audio.story_events import SAMPLE_RATE, detect_story_events, synthesize_story_effect
from app.tts.expression import classify_expression, reference_style
from app.tts.narration import apply_pronunciation_dictionary_with_counts
from app.audio import assembler


class Stage3EmotionStoryPronunciationTests(unittest.TestCase):
    def test_english_emotion_cues_cover_requested_delivery_families(self):
        cases = (
            ("She sounded happy and delighted.", "warm"),
            ("He laughed at the joke.", "amused"),
            ("She was crying after the loss.", "sad"),
            ("He was angry about the betrayal.", "angry"),
            ("She looked terrified and afraid.", "tense"),
            ("He was surprised by the news.", "excited"),
            ("The character was bored and uninterested.", "bored"),
            ("Her voice was calm and peaceful.", "calm"),
            ("He gave a serious answer.", "serious"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(classify_expression(source), expected)

    def test_japanese_emotion_cues_are_not_misclassified_as_uppercase_headings(self):
        cases = (
            ("彼女は悲しくて泣いた。", "sad"),
            ("彼は怒った。", "angry"),
            ("彼女は笑った。", "amused"),
            ("彼は恐怖で震えた。", "tense"),
            ("彼は驚いた。", "excited"),
            ("彼女は退屈した。", "bored"),
            ("彼は穏やかに話した。", "calm"),
            ("彼女は真剣に答えた。", "serious"),
        )
        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(classify_expression(source), expected)

    def test_all_caps_latin_heading_remains_neutral(self):
        self.assertEqual(classify_expression("CHAPTER ONE"), "neutral")
        self.assertEqual(classify_expression("彼は怒った。OMG"), "angry")

    def test_nuanced_emotions_keep_existing_stable_identity_anchor_mappings(self):
        self.assertEqual(reference_style("bored"), reference_style("thoughtful"))
        self.assertEqual(reference_style("calm"), reference_style("neutral"))

    def test_japanese_name_pronunciation_matches_when_followed_by_particles(self):
        result, counts = apply_pronunciation_dictionary_with_counts(
            "リムルが来た。リムルを見た。",
            [{"written_form": "リムル", "spoken_form": "Ri-mu-ru"}],
        )
        self.assertEqual(result, "Ri-mu-ruが来た。Ri-mu-ruを見た。")
        self.assertEqual(counts, {"リムル": 2})

    def test_latin_name_pronunciation_allows_japanese_particles_without_losing_word_boundaries(self):
        result, counts = apply_pronunciation_dictionary_with_counts(
            "Rimuruが来た。Rimuruを見た。 Rimurux stayed.",
            [{"written_form": "Rimuru", "spoken_form": "Ri-mu-ru"}],
        )
        self.assertEqual(result, "Ri-mu-ruが来た。Ri-mu-ruを見た。 Rimurux stayed.")
        self.assertEqual(counts, {"Rimuru": 2})

    def test_pronunciation_substitution_does_not_erase_japanese_emotion_cue(self):
        narrated, counts = apply_pronunciation_dictionary_with_counts(
            "リムルは怒った。",
            [{"written_form": "リムル", "spoken_form": "Ri-mu-ru"}],
        )
        self.assertEqual(narrated, "Ri-mu-ruは怒った。")
        self.assertEqual(counts, {"リムル": 1})
        self.assertEqual(classify_expression(narrated), "angry")

    def test_story_event_detection_returns_source_positions_and_expected_actions(self):
        source = (
            "He sprinted down the corridor. "
            "Rain hammered against the window. "
            "The door slammed shut."
        )
        events = detect_story_events(source)
        self.assertEqual(
            {event.kind for event in events},
            {"running_footsteps", "rain", "door_slam"},
        )
        for event in events:
            self.assertGreaterEqual(event.char_start, 0)
            self.assertGreater(event.char_end, event.char_start)
            self.assertTrue(source[event.char_start:event.char_end])

    def test_story_event_detection_supports_explicit_japanese_actions_and_ambience(self):
        source = "彼は廊下を走り抜けた。雨が激しく降っていた。雷が鳴り響いた。"
        events = detect_story_events(source)
        self.assertEqual(
            {event.kind for event in events},
            {"running_footsteps", "rain", "thunder"},
        )
        for event in events:
            self.assertTrue(source[event.char_start:event.char_end])

    def test_story_event_detection_rejects_common_metaphorical_running_phrases(self):
        self.assertEqual(
            detect_story_events("She was running a business and he was running late."),
            [],
        )

    def test_story_event_detector_respects_the_requested_event_cap(self):
        events = detect_story_events(
            "The door slammed shut. Rain hammered against the window. Birds chirped nearby.",
            max_events=1,
        )
        self.assertEqual(len(events), 1)

    def test_generated_story_effect_is_a_valid_stereo_wav(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "footsteps.wav"
            result = synthesize_story_effect(output, "running_footsteps", variant_seed=4)
            self.assertEqual(result, output)
            with wave.open(str(output), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 2)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.getframerate(), SAMPLE_RATE)
                self.assertGreater(audio.getnframes(), 0)

    def test_story_effects_are_mixed_against_real_chunk_text_and_audio_timing(self):
        source = Path(assembler.__file__).read_text(encoding="utf-8")
        for token in (
            "if story_effects_enabled:",
            "for event in detect_story_events(chunk_text):",
            "transition_offset_ms + int(text_position_ms) - 110",
            "MAX_EVENTS_PER_CHAPTER",
            "synthesize_story_effect(",
            "adelay={delay_ms}|{delay_ms}",
            "amix=inputs=",
            "Story effects changed chapter",
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()
