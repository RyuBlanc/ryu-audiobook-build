from __future__ import annotations

import builtins
import json
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class QwenExternalRuntimePackagingTests(unittest.TestCase):
    def test_frozen_build_copies_app_core_as_physical_sources_for_qwen_venv(self):
        build = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn('f"--add-data={ROOT / "app" / "core"};app/core"', build)
        self.assertTrue((ROOT / "app" / "core" / "__init__.py").is_file())
        self.assertTrue((ROOT / "app" / "core" / "paths.py").is_file())

    def test_qwen_accelerator_does_not_import_frozen_only_app_core(self):
        source = (ROOT / "app" / "tts" / "qwen_accelerator.py").read_text(encoding="utf-8")
        start = source.index("def automatic_accelerator(")
        end = source.index("\ndef accelerator_report(", start)
        selector = source[start:end]
        self.assertNotIn("from app.core.paths import settings_root", selector)
        self.assertIn('Path.home() / "Ryu', selector)
        self.assertIn('Audiobook" / "Settings"', selector)

    def test_worker_does_not_report_ready_with_pending_device(self):
        source = (ROOT / "app" / "tts" / "qwen_character_worker.py").read_text(encoding="utf-8")
        self.assertNotIn('"device": "pending"', source)
        self.assertIn('"backend": _actual_backend(device)', source)
        self.assertIn('"device": device', source)
        lazy_start = source.index('if active_task in {"design", "design-preview"}:')
        lazy_end = source.index("    else:", lazy_start)
        lazy_handshake = source[lazy_start:lazy_end]
        self.assertIn('"worker_ready": True', lazy_handshake)
        self.assertNotIn('"device": device', lazy_handshake)
        self.assertNotIn('"backend": _actual_backend(device)', lazy_handshake)

    def test_voice_design_preview_reports_verified_device_with_synthesis_result_after_load(self):
        source = (ROOT / "app" / "tts" / "qwen_character_worker.py").read_text(encoding="utf-8")
        start = source.index('elif active_task == "design-preview" and model is None:')
        end = source.index("if isinstance(batch_texts, list):", start)
        section = source[start:end]
        self.assertIn("load_model(args.kind)", section)
        self.assertNotIn('"ready": True', section)
        self.assertIn('elif active_task == "design-preview":', source)
        self.assertIn("_generate_design_preview(model, request, output)", source)
        self.assertIn('"ok": True', source)
        self.assertIn('"device": device', source)

    def test_provider_marks_actual_device_only_after_successful_audio_response(self):
        source = (ROOT / "app" / "tts" / "providers" / "qwen_character.py").read_text(encoding="utf-8")
        start = source.index("def _start_worker(self)")
        end = source.index("def _drain_stdout(", start)
        startup = source[start:end]
        self.assertNotIn("self._record_execution_context(response)", startup)
        self.assertIn('response.get("device")', startup)
        synth_start = source.index("def synthesize(")
        synth = source[synth_start:]
        self.assertIn('if response.get("ok") is True:', synth)
        self.assertIn("self._record_execution_context(response)", synth)

    def test_supported_gpu_is_default_without_verified_same_machine_cpu_win(self):
        from app.tts import qwen_accelerator as accelerator

        gpu = accelerator.Accelerator(
            backend="cuda",
            device="cuda:0",
            name="NVIDIA Test GPU",
            memory_gb=8.0,
            supported=True,
            reason="Test CUDA runtime is active",
        )
        original_import = builtins.__import__

        def block_frozen_core(name, *args, **kwargs):
            if name == "app.core" or name.startswith("app.core."):
                raise ModuleNotFoundError("No module named 'app.core'")
            return original_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as temp:
            history = Path(temp) / "missing-performance-history.json"
            with (
                patch.object(accelerator, "best_accelerator", return_value=gpu),
                patch.object(accelerator.platform, "processor", return_value="Test CPU"),
                patch("builtins.__import__", side_effect=block_frozen_core),
            ):
                for model_kind in ("custom-0.6b", "design-1.7b", "base-0.6b"):
                    with self.subTest(model_kind=model_kind):
                        selected, reason = accelerator.automatic_accelerator(
                            model_kind,
                            history_path=history,
                        )
                        self.assertEqual(selected.backend, "cuda")
                        self.assertEqual(selected.device, "cuda:0")
                        self.assertIn("Using supported CUDA accelerator", reason)

    def test_cpu_is_selected_only_when_verified_same_machine_benchmark_is_at_least_five_percent_faster(self):
        from app.tts import qwen_accelerator as accelerator

        gpu = accelerator.Accelerator(
            backend="cuda",
            device="cuda:0",
            name="NVIDIA Test GPU",
            memory_gb=8.0,
            supported=True,
            reason="Test CUDA runtime is active",
        )
        now = datetime.now(timezone.utc).isoformat()
        common = {
            "provider": "QwenCharacterProvider",
            "model_kind": "custom-0.6b",
            "workload_id": "qwen-customvoice-preview-30s-v1",
            "success": True,
            "backend_verified": True,
            "target_duration_met": True,
            "hardware": {
                "gpu_name": "NVIDIA Test GPU",
                "processor": "Test CPU",
            },
        }
        rows = [
            {
                "state": "completed",
                "measured_at": now,
                "result": {**common, "backend": "cpu", "seconds": 8.0, "audio_seconds": 30.0},
            },
            {
                "state": "completed",
                "measured_at": now,
                "result": {**common, "backend": "cuda", "seconds": 12.0, "audio_seconds": 30.0},
            },
        ]

        with tempfile.TemporaryDirectory() as temp:
            history = Path(temp) / "premium_v2_performance_history.json"
            history.write_text(json.dumps(rows), encoding="utf-8")
            with (
                patch.object(accelerator, "best_accelerator", return_value=gpu),
                patch.object(accelerator.platform, "processor", return_value="Test CPU"),
            ):
                selected, reason = accelerator.automatic_accelerator(
                    "custom-0.6b",
                    history_path=history,
                )
        self.assertEqual(selected.backend, "cpu")
        self.assertIn("at least 5% faster", reason)


if __name__ == "__main__":
    unittest.main()
