"""Regression coverage for Qwen's sentence-aware preview and safe GPU batching policy."""
from __future__ import annotations

import unittest
import ast
from pathlib import Path
from unittest.mock import patch

from app.tts.preview import _preview_units
from app.tts.providers.qwen_character import QwenCharacterProvider


class QwenPreviewPerformancePolicyTests(unittest.TestCase):
    def test_qwen_benchmark_registers_progress_callback_after_provider_construction(self):
        host_path = Path(__file__).resolve().parents[1] / "app/ui/premium_v2_host.py"
        module = ast.parse(host_path.read_text(encoding="utf-8"))
        worker = next(
            node for node in ast.walk(module)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_performance_qwen_benchmark_worker"
        )
        constructor = next(
            node for node in ast.walk(worker)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "QwenCharacterProvider"
        )
        self.assertNotIn("status_callback", {keyword.arg for keyword in constructor.keywords})
        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "provider"
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == "set_status_callback"
                for node in ast.walk(worker)
            ),
            "The benchmark must use the provider's optional progress setter safely.",
        )

    def _provider(self, mode: str = "design-preview") -> QwenCharacterProvider:
        return QwenCharacterProvider(
            voice_id="test narrator",
            model_kind="design-1.7b",
            qwen_mode=mode,
            qwen_profile_id="qwen-preview-policy-test",
        )

    def test_qwen_preview_uses_high_throughput_ten_sentence_chunks(self):
        provider = self._provider()
        sentence = "The road continued toward the old village."
        source = " ".join([sentence] * 12)

        units = _preview_units(
            source, provider, provider.voice_id, None, max_chars=4000
        )

        self.assertEqual(provider.recommended_preview_chunk_chars, 2400)
        self.assertEqual(provider.recommended_preview_chunk_sentences, 10)
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0][0].count("."), 10)
        self.assertEqual(units[1][0].count("."), 2)

    def test_qwen_preview_keeps_expression_family_changes_as_boundaries(self):
        provider = self._provider()
        source = "She felt delighted and happy. He was angry and furious."

        units = _preview_units(
            source, provider, provider.voice_id, None, max_chars=4000
        )

        self.assertEqual(len(units), 2)
        self.assertIn("delighted", units[0][0])
        self.assertNotIn("furious", units[0][0])
        self.assertIn("furious", units[1][0])

    def test_other_providers_keep_the_existing_one_sentence_preview_policy(self):
        class GenericProvider:
            pass

        units = _preview_units(
            "The first sentence is here. The second sentence is here. The third sentence is here.",
            GenericProvider(),
            "voice",
            None,
            max_chars=4000,
        )

        self.assertEqual(len(units), 3)

    def test_production_voice_design_batches_only_with_twelve_gib_or_more(self):
        provider = self._provider(mode="design")
        for memory_gb, expected in ((0.0, 1), (7.0, 1), (11.99, 1), (12.0, 2), (24.0, 2)):
            with self.subTest(memory_gb=memory_gb), patch(
                "app.tts.providers.qwen_character._detected_vram_gb",
                return_value=memory_gb,
            ):
                self.assertEqual(provider.recommended_batch_size, expected)

    def test_preview_or_non_design_qwen_modes_never_enable_long_form_batches(self):
        for mode in ("design-preview", "custom", "clone"):
            provider = self._provider(mode=mode)
            with self.subTest(mode=mode), patch(
                "app.tts.providers.qwen_character._detected_vram_gb",
                return_value=24.0,
            ):
                self.assertEqual(provider.recommended_batch_size, 1)

    def test_qwen_preview_batch_policy_remains_vram_gated(self):
        provider = self._provider()
        for memory_gb, expected in ((0.0, 1), (6.99, 1), (7.0, 2), (16.0, 2)):
            with self.subTest(memory_gb=memory_gb), patch(
                "app.tts.providers.qwen_character._detected_vram_gb",
                return_value=memory_gb,
            ):
                self.assertEqual(provider.recommended_preview_batch_size, expected)


if __name__ == "__main__":
    unittest.main()
