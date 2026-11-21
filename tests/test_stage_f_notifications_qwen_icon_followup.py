"""Stage F regressions for notification retention, Qwen delivery and icon application."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from app.tts.expression import classify_expression, expression_temperature
from app.tts import qwen_character_worker
from app.tts.providers.qwen_character import _request_language_for_text
from app.tts.narration import apply_pronunciation_dictionary_with_counts
from app.tts.pronunciation_suggester import is_pronunciation_term_candidate
from app.tts.generator import story_context_for_chunk


ROOT = Path(__file__).resolve().parents[1]


class StageFNotificationQwenIconFollowupTests(unittest.TestCase):
    def test_notification_history_is_persistent_clearable_and_expires_after_24_hours(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("RYU_NOTIFICATION_STORAGE_KEY", adapter)
        self.assertIn("RYU_NOTIFICATION_TTL_MS = 24 * 60 * 60 * 1000", adapter)
        self.assertIn("window.localStorage.getItem", adapter)
        self.assertIn("window.localStorage.setItem", adapter)
        self.assertIn("data-clear-ryu-notification", adapter)
        self.assertIn("data-clear-all-ryu-notifications", adapter)
        self.assertIn("overflow-y:auto", adapter)
        self.assertIn("grid-template-columns:minmax(0,1fr) 28px", adapter)
        self.assertNotIn("item.at <= 30000", adapter)
        self.assertNotIn("ryuToastTimer", adapter)
        self.assertIn("do not cover", adapter)
        self.assertNotIn("RYU_NOTIFICATION_LIMIT", adapter)

    def test_voice_design_default_preset_is_applied_and_synchronised_to_profile(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("function ensureVoiceDesignLanguageOptions()", adapter)
        self.assertIn("function syncVoiceDesignDraftToProfile()", adapter)
        self.assertIn("applyVoiceDesignPreset(preset)", adapter)
        self.assertIn("queueMicrotask(() => syncVoiceDesignDraftToProfile())", adapter)
        self.assertIn("Korean", adapter)
        self.assertIn("qwen_mode:'design'", adapter)
        self.assertIn("VoiceDesign", adapter[adapter.index("async function saveVoice(options = {})"):])

    def test_packaged_cursor_is_embedded_for_webengine_instead_of_relying_on_file_urls(self):
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        cursor = host[host.index("def _apply_icon_pack_cursor"):host.index("def _on_web_load_finished")]
        self.assertIn("QBuffer", host)
        self.assertIn("data:image/png;base64,", cursor)
        self.assertIn("self.web.page().runJavaScript(script)", cursor)
        self.assertIn("self.web.setCursor(cursor)", cursor)

    def test_yes_ellipsis_and_yes_exclamation_have_different_low_intensity_delivery(self):
        self.assertEqual(classify_expression("Yes..."), "thoughtful")
        self.assertEqual(classify_expression("Yes…"), "thoughtful")
        self.assertEqual(classify_expression("Yes!"), "serious")
        self.assertEqual(classify_expression("Yes."), "neutral")
        self.assertEqual(classify_expression("Yes!! We did it!"), "excited")
        self.assertEqual(classify_expression("No!"), "tense")
        self.assertLess(expression_temperature("warm"), 0.8)
        self.assertLess(expression_temperature("thoughtful"), 0.8)
        self.assertLess(expression_temperature("excited"), 0.8)

    def test_explicit_japanese_and_korean_language_choices_are_preserved_for_all_qwen_modes(self):
        self.assertEqual(_request_language_for_text("Japanese", "リムルが来た。"), "Japanese")
        self.assertEqual(_request_language_for_text("Korean", "리무루가 왔다."), "Korean")
        self.assertEqual(_request_language_for_text("English", "リムルが来た。"), "Auto")
        self.assertEqual(_request_language_for_text("English", "Rimuru arrived."), "English")

    def test_japanese_and_korean_character_terms_can_use_explicit_reviewed_pronunciation_rules(self):
        source = "リムルが来た。리무루가 왔다。"
        converted, counts = apply_pronunciation_dictionary_with_counts(
            source,
            [
                {"written_form":"リムル","spoken_form":"Rimuru","enabled":True},
                {"written_form":"리무루","spoken_form":"Rimuru","enabled":True},
            ],
        )
        self.assertEqual(converted, "Rimuruが来た。Rimuru가 왔다。")
        self.assertEqual(counts, {"リムル":1,"리무루":1})

    def test_webengine_cursor_builder_uses_valid_css_url_quoting_for_all_surfaces(self):
        from app.ui.premium_v2_host import PremiumV2Window
        script = PremiumV2Window._cursor_webengine_script("data:image/png;base64,AAAA")
        self.assertIn("cursor:url(\"'+url+'\")", script)
        self.assertIn("html *,body *", script)
        self.assertIn("!important", script)
        self.assertNotIn('url(\\\"', script)

    def test_story_context_changes_short_reactions_without_overriding_full_sentences(self):
        from app.tts.expression import classify_expression_with_context
        self.assertEqual(classify_expression_with_context("Yes...", "They finally won the battle.", ""), "warm")
        self.assertEqual(
            classify_expression_with_context("Yes.", "She was terrified; the monster had cornered them.", ""),
            "tense",
        )
        self.assertEqual(
            classify_expression_with_context("The monster attacked.", "They finally won earlier.", ""),
            "neutral",
        )

    def test_explicit_adjacent_speech_attribution_controls_delivery(self):
        from app.tts.expression import classify_expression_with_context
        self.assertEqual(classify_expression_with_context('"Come here."', "She whispered,", ""), "soft")
        self.assertEqual(classify_expression_with_context('"Stop!"', "", "he shouted."), "tense")

    def test_context_windows_are_bounded_and_preserve_story_order(self):
        chunks = ["Opening scene.", "She was afraid.", "Yes...", "The door opened."]
        context = story_context_for_chunk(chunks, 2, context_chars=300)
        self.assertIn("She was afraid.", context["before"])
        self.assertIn("The door opened.", context["after"])
        self.assertNotIn("Yes...", context["before"] + context["after"])

    def test_english_sentence_with_one_foreign_name_does_not_switch_qwen_language(self):
        self.assertEqual(_request_language_for_text("English", "The story follows リムル."), "English")
        self.assertEqual(_request_language_for_text("English", "リムルが来た。"), "Auto")

    def test_reviewed_dictionary_matches_devanagari_tamil_telugu_and_arabic(self):
        source = "राम आया।தமிழ் சொல். తెలుగు మాట. مرحبا بك."
        rules = [
            {"written_form":"राम","spoken_form":"Raam"},
            {"written_form":"தமிழ்","spoken_form":"Thamizh"},
            {"written_form":"తెలుగు","spoken_form":"Telugu"},
            {"written_form":"مرحبا","spoken_form":"Marhaba"},
        ]
        converted, counts = apply_pronunciation_dictionary_with_counts(source, rules)
        self.assertEqual(converted, "Raam आया।Thamizh சொல். Telugu మాట. Marhaba بك.")
        self.assertEqual(len(counts), 4)

    def test_foreign_romanized_vocabulary_needs_language_and_confidence_evidence(self):
        self.assertTrue(is_pronunciation_term_candidate(
            "Hyeon-woo", source_language="Korean", script="Latin",
            confidence=0.94, reason="Romanized Korean name."
        ))
        self.assertTrue(is_pronunciation_term_candidate(
            "Thirukkural", source_language="Tamil", script="Latin",
            confidence=0.96, reason="Tamil cultural term."
        ))
        self.assertFalse(is_pronunciation_term_candidate(
            "Beautiful", source_language="Japanese", script="Latin",
            confidence=0.99, reason="Model guess."
        ))
        self.assertFalse(is_pronunciation_term_candidate(
            "Randomword", source_language="Auto-detect", script="Latin",
            confidence=0.99, reason="No source evidence."
        ))

    def test_customvoice_receives_contextual_instruction_and_restrained_sampling(self):
        model = Mock()
        model.generate_custom_voice.return_value = ([object()], 24000)
        soundfile = types.SimpleNamespace(write=Mock())
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {"soundfile": soundfile}):
            output = Path(temp) / "custom.wav"
            qwen_character_worker._generate_custom(
                model,
                {"text": "Yes...", "speaker": "Ryan", "language": "English", "instruct": "Warm male voice", "context_before": "They finally won the battle.", "context_after": "The crowd cheered."},
                output,
            )
        kwargs = model.generate_custom_voice.call_args.kwargs
        self.assertIn("Default to low-intensity", kwargs["instruct"])
        self.assertIn("same", kwargs["instruct"].lower())
        self.assertIn("PRECEDING STORY CONTEXT", kwargs["instruct"])
        self.assertIn("They finally won the battle.", kwargs["instruct"])
        self.assertLess(kwargs["temperature"], 0.8)
        self.assertLess(kwargs["subtalker_temperature"], 0.8)

    def test_voice_design_preview_uses_selected_language_and_controlled_expression(self):
        model = Mock()
        model.generate_voice_design.return_value = ([object()], 24000)
        soundfile = types.SimpleNamespace(write=Mock())
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {"soundfile": soundfile}):
            output = Path(temp) / "design.wav"
            qwen_character_worker._generate_design_preview(
                model,
                {"text": "Yes...", "language": "Japanese", "instruct": "Calm character", "expression_style": "thoughtful", "context_before": "The danger had passed.", "context_after": "She smiled."},
                output,
            )
        kwargs = model.generate_voice_design.call_args.kwargs
        self.assertEqual(kwargs["language"], "Japanese")
        self.assertIn("brief hesitation", kwargs["instruct"])
        self.assertIn("The danger had passed.", kwargs["instruct"])
        self.assertIn("She smiled.", kwargs["instruct"])
        self.assertLess(kwargs["temperature"], 0.8)

    def test_qwen_clone_keeps_reference_audio_and_uses_lower_contextual_temperature(self):
        model = Mock()
        model.generate_voice_clone.return_value = ([object()], 24000)
        soundfile = types.SimpleNamespace(write=Mock())
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {"soundfile": soundfile}):
            reference = Path(temp) / "reference.wav"
            reference.write_bytes(b"reference")
            output = Path(temp) / "clone.wav"
            qwen_character_worker._generate_clone(
                model,
                {"text": "Yes...", "reference": str(reference), "language": "Korean", "ref_text": "안녕하세요", "context_before": "They finally won the battle."},
                output,
            )
        kwargs = model.generate_voice_clone.call_args.kwargs
        self.assertEqual(kwargs["language"], "Korean")
        self.assertEqual(kwargs["ref_text"], "안녕하세요")
        self.assertLess(kwargs["temperature"], 0.8)
        self.assertLess(kwargs["subtalker_temperature"], 0.8)
        self.assertAlmostEqual(kwargs["temperature"], expression_temperature("warm"))


if __name__ == "__main__":
    unittest.main()
