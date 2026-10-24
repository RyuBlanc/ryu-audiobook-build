"""Regression tests for the Premium V2 Models Center lifecycle."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.ui.premium_v2_host import PremiumV2Bridge


class _FakeResponse:
    def __init__(self, data: bytes):
        self.data = data
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        if not self.data:
            return b""
        if size < 0:
            result, self.data = self.data, b""
            return result
        result, self.data = self.data[:size], self.data[size:]
        return result


class ModelsCenterLifecycleTests(unittest.TestCase):
    def make_bridge(self) -> PremiumV2Bridge:
        with (
            patch("app.ui.premium_v2_host.ensure_roots"),
            patch.object(PremiumV2Bridge, "_load_durable_jobs"),
        ):
            return PremiumV2Bridge()

    def test_models_bridge_exposes_install_repair_uninstall_and_verify(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        for command, handler in (
            ("models.list", "_models_list"),
            ("models.install", "_models_install"),
            ("models.repair", "_models_repair"),
            ("models.uninstall", "_models_uninstall"),
            ("models.verify", "_models_verify"),
        ):
            self.assertIn(f'"{command}": self.{handler}', source)
            self.assertIn(f'"{command}": True', source)

    def test_piper_install_downloads_and_validates_model_and_config_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            model_root = Path(temporary) / "Models"
            model = b"piper-model-bytes" * 100
            config = json.dumps({"audio": {"sample_rate": 22050}, "phoneme_id_map": {"_": [0]}}).encode()
            requests = []

            def open_url(request, timeout=0, context=None):
                url = request.full_url
                requests.append(url)
                return _FakeResponse(config if ".onnx.json?" in url else model)

            def piper_paths():
                root = model_root / "piper"
                return sorted(root.rglob("*.onnx")) if root.exists() else []

            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=model_root),
                patch("app.tts.providers.piper.PiperProvider.model_paths", side_effect=piper_paths),
                patch("app.tts.model_registry.mark_installed") as mark_installed,
                patch("urllib.request.urlopen", side_effect=open_url),
            ):
                result = bridge._models_install_component(
                    "piper", {"voice_name": "en_US-amy-medium"}, lambda _message: None
                )

            voice_root = model_root / "piper"
            self.assertTrue((voice_root / "en_US-amy-medium.onnx").is_file())
            self.assertTrue((voice_root / "en_US-amy-medium.onnx.json").is_file())
            self.assertEqual(json.loads((voice_root / "en_US-amy-medium.onnx.json").read_text()), json.loads(config))
            self.assertEqual(len(requests), 2)
            self.assertTrue(all("huggingface.co/rhasspy/piper-voices/resolve/main/" in url for url in requests))
            self.assertIn("installed and verified", result)
            mark_installed.assert_called_once_with("piper", True)

    def test_invalid_piper_voice_id_is_rejected_before_network_access(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch("app.core.paths.models_root", return_value=Path(temporary)),
                patch("urllib.request.urlopen") as open_url,
            ):
                with self.assertRaisesRegex(ValueError, "valid Piper voice ID"):
                    bridge._models_install_component(
                        "piper", {"voice_name": "../outside"}, lambda _message: None
                    )
                open_url.assert_not_called()

    def test_individual_qwen_model_uninstall_preserves_other_model_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Models"
            runtime_root = root / "qwen-runtime"
            remove = runtime_root / "custom-0.6b"
            preserve = runtime_root / "base-0.6b"
            (remove / "weights").mkdir(parents=True)
            (remove / "weights" / "model.safetensors").write_bytes(b"x")
            preserve.mkdir(parents=True)
            (preserve / "config.json").write_text("{}", encoding="utf-8")
            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.qwen_character_runtime.MODEL_DIRS",
                      {"custom-0.6b": remove, "base-0.6b": preserve}),
                patch("app.tts.qwen_character_runtime.RUNTIME_ROOT", runtime_root),
            ):
                message = bridge._models_uninstall_component("custom-0.6b", {}, lambda _message: None)

            self.assertFalse(remove.exists())
            self.assertTrue(preserve.is_dir())
            self.assertTrue((preserve / "config.json").is_file())
            self.assertIn("other model folders", message)

    def test_starting_second_model_operation_is_blocked_while_one_is_running(self):
        bridge = self.make_bridge()
        bridge._jobs["active-model-job"] = {"state": "running", "type": "model-install"}
        with self.assertRaisesRegex(RuntimeError, "Another model installation"):
            bridge._models_start_operation("repair", "qwen-runtime", {})


if __name__ == "__main__":
    unittest.main()
