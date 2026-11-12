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

    def test_qwen_preview_batch_policy_respects_the_selected_voice_design_engine(self):
        policies = {
            "design": ((0.0, 1), (7.0, 1), (11.99, 1), (12.0, 2), (24.0, 2)),
            "design-preview": ((0.0, 1), (6.99, 1), (7.0, 2), (16.0, 2)),
        }
        for mode, samples in policies.items():
            provider = self._provider(mode=mode)
            for memory_gb, expected in samples:
                with self.subTest(mode=mode, memory_gb=memory_gb), patch(
                    "app.tts.providers.qwen_character._detected_vram_gb",
                    return_value=memory_gb,
                ):
                    self.assertEqual(provider.recommended_preview_batch_size, expected)

    def test_voice_design_audition_uses_the_same_identity_locked_profile_as_production(self):
        root = Path(__file__).resolve().parents[1]
        host_source = (root / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        preview_start = host_source.index("def _preview_worker(")
        preview_worker = host_source[preview_start:]
        self.assertNotIn('preview_profile.qwen_mode = "design-preview"', preview_worker)
        self.assertIn("provider, voice = provider_from_profile(profile)", preview_worker)

        preview_source = (root / "app" / "tts" / "preview.py").read_text(encoding="utf-8")
        self.assertIn('qwen_mode in {"design", "design-preview"}', preview_source)
        worker_source = (root / "app" / "tts" / "qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertIn('if active_task == "design":', worker_source)
        self.assertIn("lock_design_identity(request)", worker_source)

    def test_qwen_clone_reference_is_checked_before_worker_startup(self):
        provider = self._provider(mode="clone")
        provider.reference_audio = Path(__file__).with_name("missing-qwen-clone-reference.wav")
        with patch.object(provider, "_start_worker") as start_worker:
            with self.assertRaisesRegex(RuntimeError, "reference recording is missing or empty"):
                provider.synthesize("A short clone preview.", Path("preview.wav"))
        start_worker.assert_not_called()



    def test_accelerator_qwen_preview_benchmarks_use_the_saved_profile_identity_path(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "tests/smoke_qwen_gpu_preview.py",
            "tests/smoke_qwen_amd_intel_preview.py",
        ):
            with self.subTest(script=relative):
                source = (root / relative).read_text(encoding="utf-8")
                self.assertNotIn('qwen_mode="design-preview"', source)
                self.assertIn("provider_from_profile(reloaded_design)", source)
                self.assertIn("save_profiles([design_profile])", source)
                self.assertIn("load_saved_profile(design_profile.name)", source)
                self.assertIn('qwen_mode="design"', source)
                self.assertIn('return_value="1.7b"', source)
                self.assertIn("target_seconds=30.0", source)

    def test_hosted_cpu_qwen_acceptance_measures_saved_profile_30_second_preview(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "tests/smoke_qwen_real_clone_design_production.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("qwen-voicedesign-saved-profile-30-second-preview.wav", source)
        self.assertIn("REAL_QWEN_VOICEDESIGN_SAVED_PROFILE_PREVIEW=PASS", source)
        self.assertIn("saved_preview_elapsed", source)
        self.assertIn("import time", source)
        self.assertIn('execution_backend != "cpu"', source)

if __name__ == "__main__":
    unittest.main()
