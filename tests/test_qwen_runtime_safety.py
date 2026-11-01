"""Regression tests for the Qwen runtime command runner."""
from __future__ import annotations

import sys
import time
import unittest

from app.tts.qwen_character_runtime import _run


class QwenRuntimeSafetyTests(unittest.TestCase):
    def test_command_runner_enforces_timeout_when_child_stalls_without_stdout(self):
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "timed out after 0.3 seconds"):
            _run(
                [sys.executable, "-u", "-c", "import time; time.sleep(5)"],
                timeout=0.3,
            )
        self.assertLess(time.monotonic() - started, 3.0)

    def test_command_runner_streams_progress_and_reports_nonzero_exit(self):
        progress = []
        with self.assertRaisesRegex(RuntimeError, "exit code 7"):
            _run(
                [sys.executable, "-u", "-c", "print('download stage', flush=True); raise SystemExit(7)"],
                progress=progress.append,
                timeout=5,
            )
        self.assertIn("download stage", progress)

    def test_gpu_cuda_install_failure_falls_back_to_cpu_pytorch(self):
        from pathlib import Path
        from unittest.mock import call, patch
        from app.tts import qwen_character_runtime as runtime

        results = [
            (0, "pip bootstrap ready"),
            (1, "CUDA 12.8 wheel unavailable"),
            (1, "CUDA 12.6 wheel unavailable"),
            (0, "CPU torch installed"),
            (0, "qwen-tts installed"),
            (0, "torch=2.9.1 cuda=False"),
        ]
        progress = []
        with (
            patch.object(runtime, "_has_nvidia_gpu", return_value=True),
            patch.object(runtime, "_run_capture", side_effect=results) as runner,
        ):
            runtime._install_runtime_packages(Path("python.exe"), progress.append)

        commands = [entry.args[0] for entry in runner.call_args_list]
        index_urls = [
            commands[index][commands[index].index("--index-url") + 1]
            for index in range(len(commands))
            if "--index-url" in commands[index]
        ]
        self.assertEqual(
            index_urls,
            [
                "https://download.pytorch.org/whl/cu128",
                "https://download.pytorch.org/whl/cu126",
                "https://download.pytorch.org/whl/cpu",
            ],
        )
        self.assertTrue(any("(CPU)…" in message for message in progress))
        self.assertEqual(runner.call_count, 6)

    def test_stdout_drain_uses_captured_queue_after_close_clears_provider_state(self):
        import queue
        import threading
        from types import SimpleNamespace
        from app.tts.providers.qwen_character import QwenCharacterProvider

        read_blocked = threading.Event()
        release_reader = threading.Event()

        class BlockingStdout:
            def __init__(self):
                self.calls = 0

            def readline(self):
                self.calls += 1
                if self.calls == 1:
                    return '{"ready": true}\n'
                read_blocked.set()
                release_reader.wait(timeout=3.0)
                return ""

        provider = QwenCharacterProvider(
            voice_id="stdout-race-test",
            backend="cpu",
            model_kind="design-1.7b",
            qwen_mode="design-preview",
        )
        output_queue = queue.Queue()
        worker = SimpleNamespace(stdout=BlockingStdout())
        provider._worker = worker
        provider._stdout_queue = output_queue

        reader = threading.Thread(
            target=provider._drain_stdout,
            args=(worker, output_queue),
            daemon=True,
        )
        reader.start()
        self.assertTrue(read_blocked.wait(timeout=2.0))

        # This is the state transition performed by QwenCharacterProvider.close().
        provider._worker = None
        provider._stdout_queue = None
        release_reader.set()
        reader.join(timeout=2.0)

        self.assertFalse(reader.is_alive(), "Qwen stdout reader did not terminate.")
        self.assertEqual(output_queue.get_nowait(), '{"ready": true}')
        self.assertIsNone(output_queue.get_nowait())

    def test_close_tolerates_already_closed_qwen_streams(self):
        from types import SimpleNamespace
        from app.tts.providers.qwen_character import QwenCharacterProvider

        class AlreadyClosedStream:
            def close(self):
                raise ValueError("I/O operation on closed file")

        provider = QwenCharacterProvider(
            voice_id="closed-stream-test",
            backend="cpu",
            model_kind="design-1.7b",
            qwen_mode="design-preview",
        )
        provider._worker = SimpleNamespace(
            stdin=AlreadyClosedStream(),
            stdout=AlreadyClosedStream(),
            poll=lambda: 0,
        )
        provider.close()
        self.assertIsNone(provider._worker)
        self.assertIsNone(provider._stdout_queue)
        self.assertIsNone(provider._stdout_thread)

    def test_cpu_only_pc_attempts_cpu_pytorch_directly(self):
        from pathlib import Path
        from unittest.mock import patch
        from app.tts import qwen_character_runtime as runtime

        results = [
            (0, "pip bootstrap ready"),
            (0, "CPU torch installed"),
            (0, "qwen-tts installed"),
            (0, "torch=2.9.1 cuda=False"),
        ]
        with (
            patch.object(runtime, "_has_nvidia_gpu", return_value=False),
            patch.object(runtime, "_run_capture", side_effect=results) as runner,
        ):
            runtime._install_runtime_packages(Path("python.exe"))

        commands = [entry.args[0] for entry in runner.call_args_list]
        index_urls = [
            commands[index][commands[index].index("--index-url") + 1]
            for index in range(len(commands))
            if "--index-url" in commands[index]
        ]
        self.assertEqual(index_urls, ["https://download.pytorch.org/whl/cpu"])
        self.assertEqual(runner.call_count, 4)


class QwenCudaPrecisionTests(unittest.TestCase):
    def test_cuda_uses_bfloat16_when_device_supports_it(self):
        from types import SimpleNamespace
        from app.tts.qwen_character_worker import _inference_dtype

        bf16 = object()
        fp16 = object()
        fp32 = object()
        torch = SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: True, is_bf16_supported=lambda: True),
            bfloat16=bf16, float16=fp16, float32=fp32,
        )
        self.assertIs(_inference_dtype(torch, "cuda:0"), bf16)

    def test_cuda_falls_back_to_float16_when_bfloat16_is_unavailable(self):
        from types import SimpleNamespace
        from app.tts.qwen_character_worker import _inference_dtype

        bf16 = object()
        fp16 = object()
        fp32 = object()
        torch = SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: True, is_bf16_supported=lambda: False),
            bfloat16=bf16, float16=fp16, float32=fp32,
        )
        self.assertIs(_inference_dtype(torch, "cuda:0"), fp16)

    def test_cuda_bfloat16_probe_failure_also_uses_float16(self):
        from types import SimpleNamespace
        from app.tts.qwen_character_worker import _inference_dtype

        fp16 = object()
        torch = SimpleNamespace(
            cuda=SimpleNamespace(
                is_available=lambda: True,
                is_bf16_supported=lambda: (_ for _ in ()).throw(RuntimeError("unsupported probe")),
            ),
            bfloat16=object(), float16=fp16, float32=object(),
        )
        self.assertIs(_inference_dtype(torch, "cuda:0"), fp16)

    def test_cpu_inference_keeps_float32(self):
        from types import SimpleNamespace
        from app.tts.qwen_character_worker import _inference_dtype

        fp32 = object()
        torch = SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: False),
            bfloat16=object(), float16=object(), float32=fp32,
        )
        self.assertIs(_inference_dtype(torch, "cpu"), fp32)



class QwenAcceleratorDiscoveryTests(unittest.TestCase):
    def test_accelerator_policy_prefers_cuda_then_rocm_then_xpu(self):
        from unittest.mock import patch
        from app.tts import qwen_accelerator as accelerator

        cases = [
            ("cuda", "cuda:0"),
            ("rocm", "cuda:0"),
            ("xpu", "xpu:0"),
        ]
        for backend, device in cases:
            with self.subTest(backend=backend), patch.object(
                accelerator, "detect_accelerators",
                return_value=(accelerator.Accelerator(
                    backend, device, backend.upper(), 8.0, True, "test"
                ),),
            ):
                self.assertEqual(accelerator.best_accelerator().backend, backend)
                self.assertEqual(accelerator.best_accelerator().device, device)

    def test_shared_system_memory_is_not_misreported_as_gpu_vram(self):
        from unittest.mock import patch
        from app.tts import qwen_accelerator as accelerator

        directml = accelerator.Accelerator(
            "directml", "directml", "Intel UHD Graphics", 0.0, False,
            "Shared memory is not dedicated VRAM",
        )
        with patch.object(accelerator, "detect_accelerators", return_value=(directml,)):
            self.assertEqual(accelerator.model_selection_memory_gb(), 0.0)

    def test_uncertified_directml_adapter_is_reported_not_selected(self):
        from unittest.mock import patch
        from app.tts import qwen_accelerator as accelerator

        directml = accelerator.Accelerator(
            "directml", "directml", "AMD Radeon iGPU", 0.0, False,
            "DirectML operator compatibility not certified",
        )
        with patch.object(accelerator, "detect_accelerators", return_value=(directml,)):
            selected = accelerator.best_accelerator()
            self.assertEqual(selected.backend, "directml")
            self.assertFalse(selected.supported)
            self.assertEqual(selected.device, "cpu")
            self.assertEqual(accelerator.model_selection_memory_gb(), 0.0)
            self.assertIn("AMD Radeon iGPU", accelerator.accelerator_report())
            self.assertIn("not certified", accelerator.accelerator_report())

    def test_accelerator_report_includes_uncertified_reason(self):
        from unittest.mock import patch
        from app.tts import qwen_accelerator as accelerator

        device = accelerator.Accelerator(
            "directml", "directml", "AMD Radeon", 0.0, False,
            "Qwen DirectML not certified",
        )
        with patch.object(accelerator, "detect_accelerators", return_value=(device,)):
            report = accelerator.accelerator_report()
        self.assertIn("not certified", report)
        self.assertIn("Qwen DirectML not certified", report)




class QwenAcceleratorRuntimeInstallTests(unittest.TestCase):
    def _run_install(self, adapter, platform, responses, self_test_output):
        from pathlib import Path
        from unittest.mock import patch
        from app.tts import qwen_character_runtime as runtime

        commands = []
        pip_bootstrap_done = False

        def capture(command, timeout=120):
            nonlocal pip_bootstrap_done
            commands.append(list(command))
            command_text = " ".join(str(value) for value in command)
            if not pip_bootstrap_done:
                pip_bootstrap_done = True
                return (0, "pip bootstrap ok")
            if "qwen-tts==" in command_text:
                return (0, "Qwen package installed")
            if "-c" in command and "import torch" in command[command.index("-c") + 1]:
                return (0, self_test_output)
            return responses.pop(0)

        messages = []
        with (
            patch.object(runtime, "detect_accelerators", return_value=(adapter,)),
            patch.object(runtime, "best_accelerator", return_value=adapter),
            patch.object(runtime, "_run_capture", side_effect=capture),
            patch.object(runtime.os, "name", platform),
        ):
            runtime._install_runtime_packages(Path("qwen-python.exe"), messages.append)
        return commands, messages

    def test_amd_rocm_windows_uses_official_rocm_721_python312_wheels(self):
        from app.tts.qwen_accelerator import Accelerator

        adapter = Accelerator("rocm", "cpu", "AMD Radeon RX 9070", 16.0, False, "candidate")
        commands, messages = self._run_install(
            adapter,
            "nt",
            [(0, "AMD ROCm packages installed")],
            "torch=2.9.1+rocm7.2.1 torchaudio=2.9.1+rocm7.2.1 hip=7.2.1 cuda=True xpu=False",
        )
        joined = " ".join(str(value) for command in commands for value in command)
        self.assertIn("rocm-rel-7.2.1", joined)
        self.assertIn("torch-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl", joined)
        self.assertIn("torchaudio-2.9.1%2Brocm7.2.1-cp312-cp312-win_amd64.whl", joined)
        self.assertTrue(any("AMD ROCm" in message for message in messages))

    def test_intel_xpu_windows_uses_official_pytorch_xpu_index(self):
        from app.tts.qwen_accelerator import Accelerator

        adapter = Accelerator("xpu", "cpu", "Intel Arc Graphics", 8.0, False, "candidate")
        commands, messages = self._run_install(
            adapter,
            "nt",
            [(0, "Intel XPU wheels installed")],
            "torch=2.9.1 torchaudio=2.9.1 hip=None cuda=False xpu=True",
        )
        joined = " ".join(str(value) for command in commands for value in command)
        self.assertIn("https://download.pytorch.org/whl/xpu", joined)
        self.assertTrue(any("Intel XPU" in message for message in messages))

    def test_amd_rocm_install_rejects_wheels_without_active_hip_runtime(self):
        from pathlib import Path
        from unittest.mock import patch
        from app.tts import qwen_character_runtime as runtime
        from app.tts.qwen_accelerator import Accelerator

        adapter = Accelerator("rocm", "cpu", "AMD Radeon RX 9070", 16.0, False, "candidate")
        responses = [
            (0, "pip bootstrap ok"),
            (0, "ROCm packages installed"),
            (0, "Qwen package installed"),
            (0, "torch=2.9.1 hip=None cuda=False xpu=False"),
        ]

        def capture(command, timeout=120):
            command_text = " ".join(str(value) for value in command)
            if "pip" in command_text and "setuptools" in command_text:
                return (0, "pip bootstrap ok")
            if "qwen-tts==" in command_text:
                return (0, "Qwen package installed")
            if "-c" in command and "import torch" in command[command.index("-c") + 1]:
                return responses.pop()
            return responses.pop(0)

        with (
            patch.object(runtime, "detect_accelerators", return_value=(adapter,)),
            patch.object(runtime, "best_accelerator", return_value=adapter),
            patch.object(runtime, "_run_capture", side_effect=capture),
            patch.object(runtime.os, "name", "nt"),
        ):
            with self.assertRaisesRegex(RuntimeError, "no HIP runtime"):
                runtime._install_runtime_packages(Path("qwen-python.exe"))

    def test_intel_xpu_install_rejects_if_xpu_is_not_available(self):
        from pathlib import Path
        from unittest.mock import patch
        from app.tts import qwen_character_runtime as runtime
        from app.tts.qwen_accelerator import Accelerator

        adapter = Accelerator("xpu", "cpu", "Intel Arc Graphics", 8.0, False, "candidate")
        responses = [
            (0, "pip bootstrap ok"),
            (0, "XPU wheels installed"),
            (0, "Qwen package installed"),
            (0, "torch=2.9.1 hip=None cuda=False xpu=False"),
        ]

        def capture(command, timeout=120):
            command_text = " ".join(str(value) for value in command)
            if "pip" in command_text and "setuptools" in command_text:
                return (0, "pip bootstrap ok")
            if "qwen-tts==" in command_text:
                return (0, "Qwen package installed")
            if "-c" in command and "import torch" in command[command.index("-c") + 1]:
                return responses.pop()
            return responses.pop(0)

        with (
            patch.object(runtime, "detect_accelerators", return_value=(adapter,)),
            patch.object(runtime, "best_accelerator", return_value=adapter),
            patch.object(runtime, "_run_capture", side_effect=capture),
            patch.object(runtime.os, "name", "nt"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Intel XPU wheels"):
                runtime._install_runtime_packages(Path("qwen-python.exe"))




if __name__ == "__main__":
    unittest.main()
