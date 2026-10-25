"""Regression tests for Qwen command and bootstrap-download failure handling."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from app.tts.qwen_character_runtime import _run, _download_file
from tests.test_models_center_lifecycle import _FakeResponse


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

    def test_bootstrap_download_rejects_truncated_http_body_and_preserves_existing_installer(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "python-installer.exe"
            target.write_bytes(b"existing-valid-installer")
            response = _FakeResponse(b"x" * 5_000_128)
            response.headers = {"Content-Length": "8_000_000"}

            with patch("app.tts.qwen_character_runtime.urllib.request.urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "expected bytes"):
                    _download_file("https://example.invalid/python-installer.exe", target)

            self.assertEqual(target.read_bytes(), b"existing-valid-installer")
            self.assertFalse(target.with_suffix(".exe.part").exists())

    def test_bootstrap_download_rejects_small_file_when_length_is_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "python-installer.exe"
            response = _FakeResponse(b"x" * 1024)
            response.headers = {}

            with patch("app.tts.qwen_character_runtime.urllib.request.urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "only"):
                    _download_file("https://example.invalid/python-installer.exe", target)

            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".exe.part").exists())


if __name__ == "__main__":
    unittest.main()
