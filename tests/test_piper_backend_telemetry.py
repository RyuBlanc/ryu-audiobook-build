from __future__ import annotations

import sys
import types
import unittest
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.tts.benchmark import benchmark_provider
from app.tts.providers.piper import PiperProvider


class _Session:
    def __init__(self, providers):
        self._providers = providers

    def get_providers(self):
        return list(self._providers)


class PiperBackendTelemetryTests(unittest.TestCase):
    def test_piper_reports_actual_cuda_session_provider(self):
        class FakeVoice:
            session = _Session(["CUDAExecutionProvider", "CPUExecutionProvider"])

            @classmethod
            def load(cls, *_args, **_kwargs):
                return cls()

        fake_module = types.ModuleType("piper")
        fake_module.PiperVoice = FakeVoice
        with TemporaryDirectory() as temporary:
            model = Path(temporary) / "voice.onnx"
            model.write_bytes(b"fixture")
            provider = PiperProvider(model_path=model, backend="automatic")
            with patch.dict(sys.modules, {"piper": fake_module}):
                provider._load(model)
            self.assertEqual(provider.execution_backend, "cuda")
            self.assertEqual(
                provider.execution_providers,
                ("CUDAExecutionProvider", "CPUExecutionProvider"),
            )
            self.assertTrue(provider.execution_backend_verified)

    def test_piper_reports_cpu_session_provider_without_claiming_gpu(self):
        class FakeVoice:
            session = _Session(["CPUExecutionProvider"])

            @classmethod
            def load(cls, *_args, **_kwargs):
                return cls()

        fake_module = types.ModuleType("piper")
        fake_module.PiperVoice = FakeVoice
        with TemporaryDirectory() as temporary:
            model = Path(temporary) / "voice.onnx"
            model.write_bytes(b"fixture")
            provider = PiperProvider(model_path=model, backend="cpu")
            with patch.dict(sys.modules, {"piper": fake_module}):
                provider._load(model)
            self.assertEqual(provider.execution_backend, "cpu")
            self.assertEqual(provider.execution_providers, ("CPUExecutionProvider",))
            self.assertTrue(provider.execution_backend_verified)

    def test_benchmark_uses_verified_provider_backend_not_requested_auto_label(self):
        class FakeProvider:
            execution_backend = "cpu"
            execution_providers = ("CPUExecutionProvider",)
            execution_backend_verified = True

            def synthesize(self, _text, output_path, voice=None):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with wave.open(str(output_path), "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(8000)
                    wav.writeframes(b"\x00\x00" * 8000)
                return output_path

        result = benchmark_provider(FakeProvider(), voice="test", backend="automatic")
        self.assertTrue(result.success)
        self.assertEqual(result.backend, "cpu")
        self.assertEqual(result.requested_backend, "automatic")
        self.assertEqual(result.execution_providers, ("CPUExecutionProvider",))
        self.assertTrue(result.backend_verified)
        self.assertGreater(result.audio_seconds, 0)


if __name__ == "__main__":
    unittest.main()
