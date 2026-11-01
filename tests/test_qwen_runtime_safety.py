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


if __name__ == "__main__":
    unittest.main()
