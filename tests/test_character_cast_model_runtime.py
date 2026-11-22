from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.model_runtime import LocalLLM


class LocalLLMRuntimeIdentityTests(unittest.TestCase):
    def test_local_runtime_reports_loaded_gguf_and_only_requested_gpu_offload(self):
        with tempfile.TemporaryDirectory() as temporary:
            model = Path(temporary) / "Qwen3-4B-Q4_K_M.gguf"
            model.write_bytes(b"test-model")
            llm = LocalLLM.__new__(LocalLLM)
            llm.external_url = ""
            llm.model = model
            llm.last_response_model = "qwen3-4b"
            llm.process = SimpleNamespace(poll=lambda: None)
            with patch("app.ai.model_runtime.detect_nvidia_vram_gb", return_value=8.0):
                info = llm.runtime_info()

        self.assertEqual(info["provider"], "llama.cpp")
        self.assertEqual(info["model_id"], "qwen3-4b-q4")
        self.assertEqual(info["model_file"], "Qwen3-4B-Q4_K_M.gguf")
        self.assertTrue(info["model_identity_verified"])
        self.assertTrue(info["gpu_offload_requested"])
        self.assertFalse(info["execution_backend_verified"])
        self.assertEqual(info["server_reported_model_id"], "qwen3-4b")

    def test_external_server_is_not_mislabeled_as_local_qwen_model(self):
        llm = LocalLLM.__new__(LocalLLM)
        llm.external_url = "https://private.example.invalid/secret-token"
        llm.last_response_model = None
        info = llm.runtime_info()

        self.assertEqual(info["provider"], "external_openai_compatible")
        self.assertEqual(info["model_id"], "unknown_external_model")
        self.assertFalse(info["model_identity_verified"])
        self.assertNotIn("external_url", info)
        self.assertNotIn("secret-token", repr(info))

    def test_external_response_model_is_reported_as_unverified_server_assertion(self):
        llm = LocalLLM.__new__(LocalLLM)
        llm.external_url = "https://private.example.invalid/"
        llm.last_response_model = "private-model-42"
        info = llm.runtime_info()

        self.assertEqual(info["model_id"], "private-model-42")
        self.assertEqual(info["server_reported_model_id"], "private-model-42")
        self.assertEqual(info["model_identity_source"], "chat_completion_response")
        self.assertFalse(info["model_identity_verified"])

    def test_complete_captures_the_model_id_returned_by_external_server(self):
        import json
        from unittest.mock import patch

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps({
                    "model": "private-model-42",
                    "choices": [{"message": {"content": '{"characters": []}'}}],
                }).encode("utf-8")

        llm = LocalLLM.__new__(LocalLLM)
        llm.external_url = "https://private.example.invalid/"
        llm.last_response_model = None
        llm.log_path = Path("unused.log")
        with (
            patch.object(llm, "start"),
            patch("app.ai.model_runtime.urllib.request.urlopen", return_value=Response()),
        ):
            output = llm.complete("system", "user")

        self.assertEqual(output, '{"characters": []}')
        self.assertEqual(llm.last_response_model, "private-model-42")


if __name__ == "__main__":
    unittest.main()
