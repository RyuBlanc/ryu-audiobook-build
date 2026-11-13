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

    def test_english_default_remains_unchanged(self):
        self.assertEqual(default_voice_design_anchor_text("English"), DEFAULT_VOICE_DESIGN_ANCHOR_TEXT)
        self.assertEqual(default_voice_design_anchor_text(None), DEFAULT_VOICE_DESIGN_ANCHOR_TEXT)

    def test_saved_design_profile_without_custom_anchor_uses_its_language(self):
        from app.tts.profile_provider import provider_from_profile
        from app.tts.voice_profile import VoiceProfile

        profile = VoiceProfile(
            name="Japanese VoiceDesign",
            provider="qwen-character",
            voice_id="Designed Japanese speaker",
            model_id="design-1.7b",
            language="Japanese",
            qwen_mode="design",
            qwen_prompt="A calm, natural Japanese audiobook voice.",
            qwen_profile_id="c4-japanese-profile",
        )
        with (
            patch("app.tts.profile_provider.get_qwen_model_preference", return_value="1.7b"),
            patch("app.tts.profile_provider.get_qwen_backend_preference", return_value="automatic"),
            patch("app.tts.profile_provider.get_qwen_low_memory_mode", return_value=False),
        ):
            provider, voice = provider_from_profile(profile)

        self.assertEqual(voice, profile.voice_id)
        self.assertEqual(provider.qwen_anchor_text, default_voice_design_anchor_text("Japanese"))
        self.assertEqual(provider.language, "Japanese")

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

    def test_worker_fallback_uses_the_same_language_aware_reference(self):
        from app.tts.qwen_character_worker import _expression_anchor_text

        self.assertEqual(
            _expression_anchor_text({"language": "Japanese"}, "neutral"),
            default_voice_design_anchor_text("Japanese"),
        )
        self.assertEqual(
            _expression_anchor_text({"language": "Korean"}, "neutral"),
            default_voice_design_anchor_text("Korean"),
        )


class MultilingualExpressionCueTests(unittest.TestCase):
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
