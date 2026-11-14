from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.tts import qwen_accelerator as accelerator


def _fake_torch(*, cuda=False, hip=None, xpu=False, device_name="Test GPU", memory_gib=8.0):
    props = SimpleNamespace(name=device_name, total_memory=int(memory_gib * (1024 ** 3)))
    return SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: cuda,
            device_count=lambda: 1 if cuda else 0,
            get_device_properties=lambda _index: props,
            get_device_name=lambda _index: device_name,
        ),
        xpu=SimpleNamespace(
            is_available=lambda: xpu,
            device_count=lambda: 1 if xpu else 0,
            get_device_properties=lambda _index: props,
        ),
        version=SimpleNamespace(hip=hip, cuda="12.8" if cuda and not hip else None),
    )


class QwenAcceleratorAcceptanceTests(unittest.TestCase):
    def setUp(self):
        accelerator._detect_accelerators_cached.cache_clear()

    def tearDown(self):
        accelerator._detect_accelerators_cached.cache_clear()

    def detect(self, fake_torch, nvidia_smi=()):
        with (
            patch.dict(sys.modules, {"torch": fake_torch}),
            patch.object(accelerator, "_nvidia_smi_devices", return_value=list(nvidia_smi)),
            patch.object(accelerator, "windows_host_identity", return_value=("", "", "")),
            patch.object(accelerator, "_windows_video_controllers", return_value=[]),
        ):
            return accelerator.detect_accelerators(refresh=True)

    def test_active_cuda_reports_nvidia_device_and_memory(self):
        devices = self.detect(_fake_torch(cuda=True, device_name="NVIDIA RTX 4070"))
        gpu = next(item for item in devices if item.supported)
        self.assertEqual((gpu.backend, gpu.device, gpu.name), ("cuda", "cuda:0", "NVIDIA RTX 4070"))
        self.assertAlmostEqual(gpu.memory_gb, 8.0, places=2)
        self.assertIn("CUDA", gpu.reason)

    def test_active_hip_torch_is_reported_as_rocm_not_nvidia(self):
        devices = self.detect(_fake_torch(cuda=True, hip="7.2.1", device_name="AMD Radeon RX 9070 XT"))
        gpu = next(item for item in devices if item.supported)
        self.assertEqual(gpu.backend, "rocm")
        self.assertEqual(gpu.device, "cuda:0")
        self.assertIn("ROCm", gpu.reason)

    def test_active_intel_xpu_is_discovered(self):
        devices = self.detect(_fake_torch(xpu=True, device_name="Intel Arc B580", memory_gib=12))
        gpu = next(item for item in devices if item.supported)
        self.assertEqual((gpu.backend, gpu.device), ("xpu", "xpu:0"))
        self.assertAlmostEqual(gpu.memory_gb, 12.0, places=2)

    def test_nvidia_smi_memory_output_is_normalized_to_gib(self):
        gpu_name = "NVIDIA GeForce RTX 3050 Laptop GPU"
        with patch.object(accelerator, "_run", return_value=f"{gpu_name}, 4096"):
            self.assertEqual(accelerator._nvidia_smi_devices(), [(gpu_name, 4.0)])

    def test_nvidia_without_cuda_runtime_is_candidate_not_active_device(self):
        # _nvidia_smi_devices() returns GiB; this mock deliberately models its
        # normalized contract rather than the raw MiB text from nvidia-smi.
        devices = self.detect(_fake_torch(), (("NVIDIA GeForce RTX 3050 Laptop GPU", 4.0),))
        candidate = next(item for item in devices if item.backend == "cuda-candidate")
        self.assertFalse(candidate.supported)
        self.assertEqual(candidate.device, "cpu")
        self.assertAlmostEqual(candidate.memory_gb, 4.0, places=2)
        self.assertIn("CUDA PyTorch is not active", candidate.reason)
        self.assertEqual(accelerator.best_accelerator().backend, "cuda-candidate")

    def test_windows_intel_allow_list_covers_current_arc_and_core_ultra_families(self):
        win11 = "Microsoft Windows 11 Pro"
        self.assertTrue(accelerator.is_supported_intel_windows_device("Intel Arc A770", "Intel Core i7-13700H", win11))
        self.assertTrue(accelerator.is_supported_intel_windows_device("Intel Arc B580", "Intel Core i7-14700K", win11))
        for cpu in ("Intel Core Ultra 7 155H", "Intel Core Ultra 9 285H", "Intel Core Ultra 9 288V", "Intel Core Ultra X9 388H"):
            with self.subTest(cpu=cpu):
                self.assertTrue(accelerator.is_supported_intel_windows_device("Intel Arc Graphics", cpu, win11))
        self.assertFalse(accelerator.is_supported_intel_windows_device("Intel Arc Graphics", "Intel Core i7-13700H", win11))
        self.assertFalse(accelerator.is_supported_intel_windows_device("Intel Arc Graphics", "Intel Core Ultra 7 155H", "Microsoft Windows 10 Pro"))

    def test_amd_windows_rocm_target_is_versioned_and_os_gated(self):
        spec = accelerator.amd_windows_runtime_spec("AMD Radeon RX 9070 XT", "AMD Ryzen 7", "Microsoft Windows 11 Pro", "25H2")
        self.assertIsNotNone(spec)
        self.assertEqual(spec["rocm"], "10.1.0")
        self.assertEqual(spec["arch"], "gfx1201")
        self.assertEqual(spec["torch"], "2.14.0+rocm10.1.0")
        self.assertIsNone(accelerator.amd_windows_runtime_spec("AMD Radeon RX 9070 XT", "AMD Ryzen 7", "Microsoft Windows 10 Pro", "22H2"))

    def test_future_paired_cpu_benchmark_does_not_override_active_gpu(self):
        hardware = {"gpu_name": "Test GPU", "processor": "Test CPU"}
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        def record(backend, seconds):
            return {
                "state": "completed", "measured_at": future,
                "result": {
                    "provider": "QwenCharacterProvider", "model_kind": "custom-0.6b",
                    "workload_id": "qwen-customvoice-preview-30s-v1",
                    "success": True, "backend_verified": True, "target_duration_met": True,
                    "backend": backend, "seconds": seconds, "audio_seconds": 30.0,
                    "hardware": hardware,
                },
            }
        gpu = SimpleNamespace(backend="cuda", device="cuda:0", name="Test GPU", supported=True, memory_gb=8.0, reason="")
        with tempfile.TemporaryDirectory() as temporary:
            history = Path(temporary) / "history.json"
            history.write_text(json.dumps([record("cuda", 40.0), record("cpu", 20.0)]), encoding="utf-8")
            with (
                patch.object(accelerator, "best_accelerator", return_value=gpu),
                patch("platform.processor", return_value="Test CPU"),
            ):
                selected, reason = accelerator.automatic_accelerator("custom-0.6b", history)
        self.assertEqual(selected.backend, "cuda")
        self.assertNotIn("CPU selected", reason)


if __name__ == "__main__":
    unittest.main()
