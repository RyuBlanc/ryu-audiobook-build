"""Stage C4 regressions for multilingual Qwen identity and expressive continuity."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from app.tts.expression import (
    DEFAULT_VOICE_DESIGN_ANCHOR_TEXT,
    default_voice_design_anchor_text,
)


class QwenMultilingualIdentityAnchorTests(unittest.TestCase):
    def test_default_identity_anchor_uses_japanese_for_full_name_and_code(self):
        expected = "こんにちは。これは声のテストです。落ち着いて、自然に、はっきりと話します。"
        self.assertEqual(default_voice_design_anchor_text("Japanese"), expected)
        self.assertEqual(default_voice_design_anchor_text("ja"), expected)
        self.assertEqual(default_voice_design_anchor_text("jpn"), expected)

    def test_default_identity_anchor_uses_korean_for_full_name_and_code(self):
        expected = "안녕하세요. 이것은 자연스러운 목소리 테스트입니다. 차분하고 또렷하게 말합니다."
        self.assertEqual(default_voice_design_anchor_text("Korean"), expected)
        self.assertEqual(default_voice_design_anchor_text("ko"), expected)
        self.assertEqual(default_voice_design_anchor_text("kor"), expected)

    def test_default_identity_anchor_uses_chinese_for_full_name_and_code(self):
        expected = "你好。这是一段自然的声音测试。我会用清晰、稳定、富有表现力的方式说话。"
        self.assertEqual(default_voice_design_anchor_text("Chinese"), expected)
        self.assertEqual(default_voice_design_anchor_text("Mandarin"), expected)
        self.assertEqual(default_voice_design_anchor_text("zh"), expected)
        self.assertEqual(default_voice_design_anchor_text("cmn"), expected)


    def test_all_other_qwen_supported_languages_have_native_anchors_and_region_aliases(self):
        cases = (
            ("German", "de-DE", "Hallo. Dies ist eine kurze Stimmprobe. Ich spreche ruhig, natürlich und deutlich."),
            ("French", "fr-FR", "Bonjour. Ceci est un court échantillon de voix. Je parle calmement, naturellement et clairement."),
            ("Russian", "ru-RU", "Здравствуйте. Это короткий образец голоса. Я говорю спокойно, естественно и чётко."),
            ("Portuguese", "pt-BR", "Olá. Esta é uma breve amostra de voz. Falo com calma, naturalidade e clareza."),
            ("Spanish", "es-ES", "Hola. Esta es una breve muestra de voz. Hablo con calma, naturalidad y claridad."),
            ("Italian", "it-IT", "Ciao. Questo è un breve campione vocale. Parlo con calma, naturalezza e chiarezza."),
        )
        for language, regional_code, expected in cases:
            with self.subTest(language=language):
                self.assertEqual(default_voice_design_anchor_text(language), expected)
                self.assertEqual(default_voice_design_anchor_text(regional_code), expected)

    def test_all_supported_region_codes_use_their_native_voice_design_anchor(self):
        cases = (
            ("ja-JP", "Japanese"),
            ("ko-KR", "Korean"),
            ("zh-Hans", "Chinese"),
            ("zh-Hant", "Chinese"),
            ("de-AT", "German"),
            ("de-CH", "German"),
            ("fr-CA", "French"),
            ("fr-BE", "French"),
            ("ru-UA", "Russian"),
            ("pt-AO", "Portuguese"),
            ("es-AR", "Spanish"),
            ("it-CH", "Italian"),
        )
        for regional_code, base_language in cases:
            with self.subTest(regional_code=regional_code):
                self.assertEqual(
                    default_voice_design_anchor_text(regional_code),
                    default_voice_design_anchor_text(base_language),
                )


    def test_english_default_remains_unchanged(self):
        self.assertEqual(default_voice_design_anchor_text("English"), DEFAULT_VOICE_DESIGN_ANCHOR_TEXT)
        self.assertEqual(default_voice_design_anchor_text(None), DEFAULT_VOICE_DESIGN_ANCHOR_TEXT)

    def test_saved_design_profile_without_custom_anchor_uses_its_language(self):
        from app.tts.profile_provider import provider_from_profile
        from app.tts.voice_profile import VoiceProfile

        languages = (
            "English", "Japanese", "Korean", "Chinese", "German",
            "French", "Russian", "Portuguese", "Spanish", "Italian",
        )
        with (
            patch("app.tts.profile_provider.get_qwen_model_preference", return_value="1.7b"),
            patch("app.tts.profile_provider.get_qwen_backend_preference", return_value="automatic"),
            patch("app.tts.profile_provider.get_qwen_low_memory_mode", return_value=False),
        ):
            for language in languages:
                with self.subTest(language=language):
                    profile = VoiceProfile(
                        name=f"{language} VoiceDesign",
                        provider="qwen-character",
                        voice_id=f"Designed {language} speaker",
                        model_id="design-1.7b",
                        language=language,
                        qwen_mode="design",
                        qwen_prompt=f"A natural {language} audiobook voice.",
                        qwen_profile_id=f"c4-{language.casefold()}-profile",
                    )
                    provider, voice = provider_from_profile(profile)
                    self.assertEqual(voice, profile.voice_id)
                    self.assertEqual(provider.qwen_anchor_text, default_voice_design_anchor_text(language))
                    self.assertEqual(provider.language, language)

    def test_non_cjk_qwen_languages_do_not_receive_japanese_phonetic_fallbacks(self):
        from app.tts.pronunciation_suggester import nativeish_pronunciation

        source = "Himejima Hanezu"
        for language in ("German", "French", "Russian", "Portuguese", "Spanish", "Italian"):
            with self.subTest(language=language):
                self.assertEqual(nativeish_pronunciation(source, language), source)


    def test_explicit_anchor_transcript_is_preserved(self):
        from app.tts.providers.qwen_character import QwenCharacterProvider

        provider = QwenCharacterProvider(
            voice_id="Japanese speaker",
            language="Japanese",
            model_kind="design-1.7b",
            qwen_mode="design",
            qwen_anchor_text="ユーザーが指定した保存済みの参照文です。",
        )
        self.assertEqual(provider.qwen_anchor_text, "ユーザーが指定した保存済みの参照文です。")

    def test_explicit_anchor_audio_without_transcript_does_not_get_a_guessed_transcript(self):
        from app.tts.providers.qwen_character import QwenCharacterProvider

        provider = QwenCharacterProvider(
            voice_id="Japanese speaker",
            language="Japanese",
            model_kind="design-1.7b",
            qwen_mode="design",
            qwen_anchor_path=Path("user-supplied-anchor.wav"),
        )
        self.assertEqual(provider.qwen_anchor_text, "")

    def test_native_script_does_not_override_an_explicit_saved_qwen_language(self):
        from app.tts.providers.qwen_character import _request_language_for_text

        cases = (
            ("Japanese", "こんにちは。", "Japanese"),
            ("Korean", "안녕하세요.", "Korean"),
            ("Chinese", "你好。", "Chinese"),
            ("ja-JP", "こんにちは。", "ja-JP"),
            ("en-US", "Mira said ありがとう.", "Auto"),
            ("English", "Mira said 你好.", "Auto"),
            ("Auto", "こんにちは。", "Auto"),
            ("French", "Mira said ありがとう.", "French"),
        )
        for language, source, expected in cases:
            with self.subTest(language=language, source=source):
                self.assertEqual(_request_language_for_text(language, source), expected)


    def test_worker_fallback_uses_the_same_language_aware_reference(self):
        from app.tts.qwen_character_worker import _expression_anchor_text

        languages = (
            "English", "Japanese", "Korean", "Chinese", "German",
            "French", "Russian", "Portuguese", "Spanish", "Italian",
        )
        for language in languages:
            with self.subTest(language=language):
                self.assertEqual(
                    _expression_anchor_text({"language": language}, "neutral"),
                    default_voice_design_anchor_text(language),
                )


class MultilingualExpressionCueTests(unittest.TestCase):

    def test_other_six_qwen_languages_classify_sentence_level_emotion(self):
        cases = {
            "German": (
                ("Sie war traurig und weinte.", "sad"),
                ("Er war wütend.", "angry"),
                ("Sie hatte Angst.", "concerned"),
                ("Panik ergriff sie; es war gefährlich.", "tense"),
                ("Er lachte.", "amused"),
                ("Sie war überrascht.", "excited"),
                ("Er war glücklich.", "warm"),
                ("Sie war gelangweilt.", "bored"),
                ("Er blieb ruhig.", "calm"),
                ("Vielleicht kommt er zurück…", "thoughtful"),
                ("Sie war neugierig.", "curious"),
                ("Er antwortete ernsthaft.", "serious"),
                ("Sie erinnerte sich an früher.", "reflective"),
            ),
            "French": (
                ("Elle était triste et pleurait.", "sad"),
                ("Il était furieux.", "angry"),
                ("Elle avait peur.", "concerned"),
                ("Elle paniqua face au danger.", "tense"),
                ("Il sourit.", "amused"),
                ("Elle fut surprise.", "excited"),
                ("Il était heureux.", "warm"),
                ("Elle s'ennuyait.", "bored"),
                ("Il resta calme.", "calm"),
                ("Peut-être reviendra-t-il…", "thoughtful"),
                ("Elle était curieuse.", "curious"),
                ("Il répondit sérieusement.", "serious"),
                ("Elle se souvint de son enfance.", "reflective"),
            ),
            "Spanish": (
                ("Estaba triste y lloró.", "sad"),
                ("Estaba furioso.", "angry"),
                ("Tenía miedo.", "concerned"),
                ("Entró en pánico y había peligro.", "tense"),
                ("Él se rió.", "amused"),
                ("Ella estaba sorprendida.", "excited"),
                ("Estaba feliz.", "warm"),
                ("Estaba aburrida.", "bored"),
                ("Permaneció tranquila.", "calm"),
                ("Quizás vuelva…", "thoughtful"),
                ("Tenía curiosidad.", "curious"),
                ("Respondió seriamente.", "serious"),
                ("Recordó su infancia.", "reflective"),
            ),
            "Portuguese": (
                ("Ela estava triste e chorou.", "sad"),
                ("Ele estava furioso.", "angry"),
                ("Ela sentia medo.", "concerned"),
                ("Entrou em pânico diante do perigo.", "tense"),
                ("Ele riu.", "amused"),
                ("Ela ficou surpresa.", "excited"),
                ("Ele estava feliz.", "warm"),
                ("Ela estava entediada.", "bored"),
                ("Ele permaneceu calmo.", "calm"),
                ("Talvez ele volte…", "thoughtful"),
                ("Ela estava curiosa.", "curious"),
                ("Ele respondeu seriamente.", "serious"),
                ("Ela lembrou da infância.", "reflective"),
            ),
            "Italian": (
                ("Era triste e pianse.", "sad"),
                ("Era arrabbiato.", "angry"),
                ("Aveva paura.", "concerned"),
                ("Era in panico e c'era pericolo.", "tense"),
                ("Lui rise.", "amused"),
                ("Era sorpresa.", "excited"),
                ("Era felice.", "warm"),
                ("Era annoiata.", "bored"),
                ("Rimase calmo.", "calm"),
                ("Forse tornerà…", "thoughtful"),
                ("Era curiosa.", "curious"),
                ("Rispose seriamente.", "serious"),
                ("Ricordò la sua infanzia.", "reflective"),
            ),
            "Russian": (
                ("Она грустила и плакала.", "sad"),
                ("Он был зол.", "angry"),
                ("Она боялась.", "concerned"),
                ("Началась паника, была опасность.", "tense"),
                ("Он смеялся.", "amused"),
                ("Она была удивлена.", "excited"),
                ("Он был счастлив.", "warm"),
                ("Ей было скучно.", "bored"),
                ("Он говорил спокойно.", "calm"),
                ("Возможно, он вернётся…", "thoughtful"),
                ("Ей было любопытно.", "curious"),
                ("Он ответил серьёзно.", "serious"),
                ("Она вспомнила детство.", "reflective"),
            ),
        }
        from app.tts.expression import classify_expression

        for language, examples in cases.items():
            for source, expected in examples:
                with self.subTest(language=language, source=source):
                    self.assertEqual(classify_expression(source), expected)

    def test_chinese_story_cues_keep_sentence_level_emotion(self):
        cases = (
            ("她很伤心，忍不住哭了。", "sad"),
            ("他非常愤怒。", "angry"),
            ("她害怕得发抖。", "tense"),
            ("他笑了起来。", "amused"),
            ("她惊讶地看着他。", "excited"),
            ("他感到快乐。", "warm"),
            ("她觉得无聊。", "bored"),
            ("他说话平静。", "calm"),
            ("他认真地回答。", "serious"),
            ("也许他会回来……", "thoughtful"),
            ("她很好奇。", "curious"),
        )
        from app.tts.expression import classify_expression

        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(classify_expression(source), expected)

    def test_korean_story_cues_keep_sentence_level_emotion(self):
        cases = (
            ("그녀는 슬퍼서 울었다.", "sad"),
            ("그는 몹시 화가 났다.", "angry"),
            ("그녀는 무서워 떨었다.", "tense"),
            ("그는 크게 웃었다.", "amused"),
            ("그녀는 깜짝 놀랐다.", "excited"),
            ("그는 행복하고 기뻤다.", "warm"),
            ("그녀는 지루했다.", "bored"),
            ("그는 차분하게 말했다.", "calm"),
            ("그녀는 진지하게 대답했다.", "serious"),
            ("아마도 그럴지도 몰라…", "thoughtful"),
            ("그녀는 정말 궁금했다.", "curious"),
        )
        from app.tts.expression import classify_expression

        for source, expected in cases:
            with self.subTest(source=source):
                self.assertEqual(classify_expression(source), expected)


if __name__ == "__main__":
    unittest.main()
