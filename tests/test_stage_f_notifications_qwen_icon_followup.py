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
        self.assertEqual(classify_expression("Yes!"), "warm")
        self.assertEqual(classify_expression("Yes."), "neutral")
        self.assertEqual(classify_expression("Yes!! We did it!"), "excited")
        self.assertEqual(classify_expression("No!"), "tense")
        self.assertLess(expression_temperature("warm"), 0.8)
        self.assertLess(expression_temperature("thoughtful"), 0.8)
        self.assertLess(expression_temperature("excited"), 0.8)

    def test_customvoice_receives_contextual_instruction_and_restrained_sampling(self):
        model = Mock()
        model.generate_custom_voice.return_value = ([object()], 24000)
        soundfile = types.SimpleNamespace(write=Mock())
        with tempfile.TemporaryDirectory() as temp, patch.dict(sys.modules, {"soundfile": soundfile}):
            output = Path(temp) / "custom.wav"
            qwen_character_worker._generate_custom(
                model,
                {"text": "Yes!", "speaker": "Ryan", "language": "English", "instruct": "Warm male voice"},
                output,
            )
        kwargs = model.generate_custom_voice.call_args.kwargs
        self.assertIn("Default to low-intensity", kwargs["instruct"])
        self.assertIn("same", kwargs["instruct"].lower())
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
                {"text": "Yes...", "language": "Japanese", "instruct": "Calm character", "expression_style": "thoughtful"},
                output,
            )
        kwargs = model.generate_voice_design.call_args.kwargs
        self.assertEqual(kwargs["language"], "Japanese")
        self.assertIn("brief hesitation", kwargs["instruct"])
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
                {"text": "No!", "reference": str(reference), "language": "Korean", "ref_text": "안녕하세요"},
                output,
            )
        kwargs = model.generate_voice_clone.call_args.kwargs
        self.assertEqual(kwargs["language"], "Korean")
        self.assertEqual(kwargs["ref_text"], "안녕하세요")
        self.assertLess(kwargs["temperature"], 0.8)
        self.assertLess(kwargs["subtalker_temperature"], 0.8)


if __name__ == "__main__":
    unittest.main()
