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

    def test_icon_pack_selection_and_import_replace_the_live_cursor_immediately(self):
        import base64
        from PySide6.QtCore import QSettings as NativeQSettings
        from PySide6.QtGui import QImage
        from app.ui.premium_v2_host import PremiumV2Bridge, PremiumV2Window

        class Settings:
            def __init__(self):
                self.values = {"ui/icon_pack": "aether"}
                self.sync_count = 0

            def value(self, key, default=None):
                return self.values.get(key, default)

            def setValue(self, key, value):
                self.values[key] = value

            def sync(self):
                self.sync_count += 1

            def status(self):
                return NativeQSettings.Status.NoError

        settings = Settings()

        class SettingsFactory:
            Status = NativeQSettings.Status

            def __new__(cls, *_args, **_kwargs):
                return settings

        class FakePixmap:
            def __init__(self, path):
                self.path = Path(path)

            def isNull(self):
                return not self.path.is_file()

            def scaled(self, *_args):
                return self

            def save(self, buffer, _format):
                buffer.payload = self.path.read_bytes()
                return True

        class FakeBuffer:
            def __init__(self):
                self.payload = b""

            def open(self, _mode):
                return True

            def data(self):
                return self.payload

            def close(self):
                pass

        class FakeCursor:
            def __init__(self, pixmap, _hot_x, _hot_y):
                self.path = pixmap.path

        class FakeApplication:
            def __init__(self):
                self.current = None
                self.set_calls = []
                self.change_calls = []
                self.restore_calls = []

            def overrideCursor(self):
                return self.current

            def setOverrideCursor(self, cursor):
                self.current = cursor
                self.set_calls.append(cursor)

            def changeOverrideCursor(self, cursor):
                self.current = cursor
                self.change_calls.append(cursor)

            def restoreOverrideCursor(self):
                self.current = None
                self.restore_calls.append(True)

        application = FakeApplication()
        web = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            frontend = root / "assets" / "frontend" / "index.html"
            frontend.parent.mkdir(parents=True)
            frontend.write_text("<html></html>", encoding="utf-8")
            assets = root / "assets"
            drake_asset = assets / "drake_cursor_32.png"
            custom_source = root / "imported-pointer.png"

            for path, pixel in ((drake_asset, 0xFFFF2200), (custom_source, 0xFF00DD55)):
                image = QImage(32, 32, QImage.Format.Format_ARGB32)
                image.fill(pixel)
                self.assertTrue(image.save(str(path), "PNG"))

            web.viewport.return_value = Mock()
            window = types.SimpleNamespace(
                web=web,
                _icon_pack_cursor_override_active=False,
                setCursor=Mock(),
                unsetCursor=Mock(),
            )
            window._cursor_webengine_script = PremiumV2Window._cursor_webengine_script
            window._set_application_icon_pack_cursor = (
                lambda cursor: PremiumV2Window._set_application_icon_pack_cursor(window, cursor)
            )
            window._clear_application_icon_pack_cursor = (
                lambda: PremiumV2Window._clear_application_icon_pack_cursor(window)
            )
            window._apply_icon_pack_cursor = lambda: PremiumV2Window._apply_icon_pack_cursor(window)
            bridge = types.SimpleNamespace(
                settings=settings,
                parent=lambda: window,
                _settings_get=lambda _payload: {"icon_pack": settings.value("ui/icon_pack")},
            )
            window.bridge = bridge

            with (
                patch("app.ui.premium_v2_host.QSettings", SettingsFactory),
                patch("app.ui.premium_v2_host.QPixmap", FakePixmap),
                patch("app.ui.premium_v2_host.QCursor", FakeCursor),
                patch("app.ui.premium_v2_host.QBuffer", FakeBuffer),
                patch(
                    "app.ui.premium_v2_host.QIODevice",
                    types.SimpleNamespace(OpenModeFlag=types.SimpleNamespace(WriteOnly=object())),
                ),
                patch("app.ui.premium_v2_host.QApplication.instance", return_value=application),
                patch("app.ui.premium_v2_host.frontend_path", return_value=frontend),
                patch("app.ui.premium_v2_host.settings_root", return_value=root / "settings"),
            ):
                # Startup with the default Aether preference must not touch the
                # WebEngine viewport's cursor before its first page is loaded.
                PremiumV2Window._apply_icon_pack_cursor(window)
                self.assertEqual(web.viewport.return_value.unsetCursor.call_count, 0)
                self.assertEqual(settings.sync_count, 0)

                PremiumV2Bridge._settings_save(bridge, {"icon_pack": "drake"})
                self.assertEqual(application.current.path, drake_asset)

                with patch(
                    "app.ui.premium_v2_host.QFileDialog.getOpenFileName",
                    return_value=(str(custom_source), "PNG"),
                ):
                    imported = PremiumV2Bridge._icon_pack_import(bridge, {})

                custom_path = Path(settings.value("ui/custom_icon_path"))
                self.assertTrue(imported["saved"])
                self.assertEqual(imported["icon_pack"], "custom")
                self.assertTrue(custom_path.is_file())
                self.assertEqual(application.current.path, custom_path)

                # Choosing Aether again restores the original cursor on every
                # surface, including the WebEngine viewport.
                PremiumV2Bridge._settings_save(bridge, {"icon_pack": "aether"})
                self.assertIsNone(application.current)
                self.assertFalse(window._icon_pack_cursor_override_active)

            self.assertEqual(len(application.set_calls), 1)
            self.assertEqual(len(application.change_calls), 1)
            self.assertEqual(application.change_calls[0].path, custom_path)
            self.assertEqual(len(application.restore_calls), 1)
            self.assertEqual(settings.value("ui/icon_pack"), "aether")
            self.assertGreaterEqual(settings.sync_count, 5)

            javascript_calls = web.page.return_value.runJavaScript.call_args_list
            self.assertEqual(len(javascript_calls), 4)
            custom_data_url = "data:image/png;base64," + base64.b64encode(custom_path.read_bytes()).decode("ascii")
            self.assertIn(custom_data_url, javascript_calls[2].args[0])
            self.assertEqual(window.setCursor.call_args.args[0].path, custom_path)
            self.assertEqual(web.setCursor.call_args.args[0].path, custom_path)
            self.assertEqual(web.viewport.return_value.setCursor.call_args.args[0].path, custom_path)
            web.viewport.return_value.unsetCursor.assert_called_once_with()

    def test_icon_pack_cursor_uses_application_override_without_stacking_and_restores_on_aether(self):
        from app.ui.premium_v2_host import PremiumV2Window

        app = Mock()
        app.overrideCursor.return_value = None
        window = types.SimpleNamespace(_icon_pack_cursor_override_active=False)
        cursor = object()

        with patch("app.ui.premium_v2_host.QApplication.instance", return_value=app):
            PremiumV2Window._set_application_icon_pack_cursor(window, cursor)
            self.assertTrue(window._icon_pack_cursor_override_active)

            # Reapplying after settings refresh or page reload must replace,
            # not push another entry onto QApplication's override stack.
            app.overrideCursor.return_value = cursor
            PremiumV2Window._set_application_icon_pack_cursor(window, cursor)
            PremiumV2Window._clear_application_icon_pack_cursor(window)

        app.setOverrideCursor.assert_called_once_with(cursor)
        app.changeOverrideCursor.assert_called_once_with(cursor)
        app.restoreOverrideCursor.assert_called_once_with()
        self.assertFalse(window._icon_pack_cursor_override_active)

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

    def test_cast_aware_provider_forwards_context_to_narrator_and_qwen_batch_paths(self):
        from app.tts.cast_provider import CastAwareProvider
        context = {"before": "She had been worried.", "after": "The door opened."}

        narrator = Mock()
        narrator.synthesize.return_value = Path("narrator.wav")
        cast = CastAwareProvider(
            narrator_provider=narrator,
            narrator_voice="Narrator",
            profiles={},
            assignments={},
        )
        cast.set_generation_context(context)
        cast.synthesize("Yes...", Path("narration.wav"))
        narrator.set_generation_context.assert_called_once_with(context)

        qwen = Mock()
        qwen.synthesize_batch.return_value = [Path("one.wav"), Path("two.wav")]
        cast_with_qwen = CastAwareProvider(
            narrator_provider=Mock(),
            narrator_voice="Narrator",
            profiles={},
            assignments={},
        )
        cast_with_qwen._providers["shared:qwen:test"] = (qwen, "Ryan")
        cast_with_qwen._provider_for_voice = Mock(return_value=(qwen, "Ryan"))
        contexts = [context, {"before": "The crowd cheered.", "after": "She smiled."}]
        cast_with_qwen.set_batch_contexts(contexts)
        cast_with_qwen.synthesize_batch(
            [("Yes...", Path("one.wav")), ("Wonderful.", Path("two.wav"))],
            voice="Ryan",
        )
        qwen.set_batch_contexts.assert_called_once_with(contexts)
        qwen.synthesize_batch.assert_called_once()

    def test_webengine_cursor_builder_uses_valid_css_url_quoting_for_all_surfaces(self):
        from app.ui.premium_v2_host import PremiumV2Window
        script = PremiumV2Window._cursor_webengine_script("data:image/png;base64,AAAA")
        self.assertIn("cursor:url(\"'+url+'\")", script)
        self.assertIn(":root:root *", script)
        self.assertIn("::before", script)
        self.assertIn("::after", script)
        self.assertIn("document.documentElement.style.setProperty", script)
        self.assertIn("document.body.style.setProperty", script)
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
