"""P0 regression coverage for local Audiobook AI runtime fallback."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from app.ai import model_runtime


class AudiobookAIRuntimeFallbackTests(unittest.TestCase):
    def _write_cpu_archive(self, archive: Path) -> None:
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("llama/bin/llama-server.exe", b"server-binary" * 512)
            zf.writestr("llama/bin/ggml-base.dll", b"cpu-runtime-dll")

    def test_cuda_download_failure_falls_back_to_cpu_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            models_root = Path(temporary)
            ai_root = models_root / "audiobook-ai"
            ai_root.mkdir()
            model = ai_root / "Qwen3-4B-Q4_K_M.gguf"
            model.write_bytes(b"existing local model")
            download_urls = []
            progress = []

            def fake_download(url, archive, label, callback=None):
                download_urls.append(url)
                if url == model_runtime.LLAMA_CUDA12_URL:
                    raise model_runtime.BrainRuntimeError("simulated CUDA release download failure")
                self._write_cpu_archive(Path(archive))

            with (
                patch.object(model_runtime, "models_root", return_value=models_root),
                patch.object(model_runtime, "detect_nvidia_vram_gb", return_value=8.0),
                patch.object(model_runtime, "download", side_effect=fake_download),
            ):
                target = model_runtime.install_runtime(progress.append)

            self.assertEqual(target, model)
            self.assertEqual(
                download_urls,
                [model_runtime.LLAMA_CUDA12_URL, model_runtime.LLAMA_CPU_URL],
            )
            self.assertTrue((ai_root / "llama-server.exe").is_file())
            self.assertGreater((ai_root / "llama-server.exe").stat().st_size, 1024)
            self.assertEqual((ai_root / "ggml-base.dll").read_bytes(), b"cpu-runtime-dll")
            self.assertTrue(any("retrying with the CPU runtime" in line for line in progress))
            self.assertTrue(any("CPU fallback runtime installed" in line for line in progress))

    def test_truncated_cuda_server_archive_falls_back_to_cpu_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            models_root = Path(temporary)
            ai_root = models_root / "audiobook-ai"
            ai_root.mkdir()
            model = ai_root / "Qwen3-4B-Q4_K_M.gguf"
            model.write_bytes(b"existing local model")
            download_urls = []

            def fake_download(url, archive, label, callback=None):
                download_urls.append(url)
                with zipfile.ZipFile(archive, "w") as zf:
                    if url == model_runtime.LLAMA_CUDA12_URL:
                        zf.writestr("cuda/bin/llama-server.exe", b"truncated")
                    else:
                        zf.writestr("cpu/bin/llama-server.exe", b"server-binary" * 512)
                        zf.writestr("cpu/bin/ggml-base.dll", b"cpu-runtime-dll")

            with (
                patch.object(model_runtime, "models_root", return_value=models_root),
                patch.object(model_runtime, "detect_nvidia_vram_gb", return_value=8.0),
                patch.object(model_runtime, "download", side_effect=fake_download),
            ):
                target = model_runtime.install_runtime()

            self.assertEqual(target, model)
            self.assertEqual(
                download_urls,
                [model_runtime.LLAMA_CUDA12_URL, model_runtime.LLAMA_CPU_URL],
            )
            self.assertTrue((ai_root / "llama-server.exe").is_file())
            self.assertGreater((ai_root / "llama-server.exe").stat().st_size, 1024)
            self.assertEqual((ai_root / "ggml-base.dll").read_bytes(), b"cpu-runtime-dll")

    def test_cpu_only_machine_uses_cpu_runtime_without_trying_cuda(self):
        with tempfile.TemporaryDirectory() as temporary:
            models_root = Path(temporary)
            ai_root = models_root / "audiobook-ai"
            ai_root.mkdir()
            (ai_root / "Qwen3-1.7B-Q5_K_M.gguf").write_bytes(b"existing local model")
            download_urls = []

            def fake_download(url, archive, label, callback=None):
                download_urls.append(url)
                self._write_cpu_archive(Path(archive))

            with (
                patch.object(model_runtime, "models_root", return_value=models_root),
                patch.object(model_runtime, "detect_nvidia_vram_gb", return_value=0.0),
                patch.object(model_runtime, "download", side_effect=fake_download),
            ):
                model_runtime.install_runtime()

            self.assertEqual(download_urls, [model_runtime.LLAMA_CPU_URL])
            self.assertTrue((ai_root / "llama-server.exe").is_file())


if __name__ == "__main__":
    unittest.main()
