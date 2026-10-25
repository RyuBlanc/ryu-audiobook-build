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

    def test_inventory_counts_nested_runtime_files_without_double_counting_qwen_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            model_root = base / "Models"
            model_root.mkdir()

            chatterbox_root = base / "chatterbox-runtime"
            chatterbox_file = chatterbox_root / "Lib" / "site-packages" / "sample.py"
            chatterbox_file.parent.mkdir(parents=True)
            chatterbox_file.write_bytes(b"c" * 9)

            qwen_root = base / "qwen3-tts"
            venv_root = qwen_root / "runtime"
            python_root = qwen_root / "python312"
            marker = qwen_root / "runtime.json"
            installer = qwen_root / "python-installer.exe"
            installer_log = qwen_root / "python-install.log"
            for path, payload in (
                (venv_root / "Scripts" / "python.exe", b"v" * 5),
                (python_root / "python.exe", b"p" * 7),
                (marker, b"m" * 2),
                (installer, b"i" * 3),
                (installer_log, b"l" * 4),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)

            model_kinds = {
                "custom-0.6b": "example/custom",
                "custom-1.7b": "example/custom-large",
                "design-1.7b": "example/design",
                "base-0.6b": "example/base",
                "base-1.7b": "example/base-large",
            }
            model_dirs = {kind: qwen_root / kind for kind in model_kinds}
            weights = model_dirs["custom-0.6b"] / "weights.safetensors"
            weights.parent.mkdir(parents=True)
            weights.write_bytes(b"w" * 13)

            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=model_root),
                patch("app.tts.providers.piper.PiperProvider.model_paths", return_value=[]),
                patch("app.tts.providers.kokoro.KokoroProvider.assets_available", return_value=False),
                patch("app.tts.chatterbox_runtime.RUNTIME_DIR", new=chatterbox_root),
                patch("app.tts.chatterbox_runtime.runtime_ready", return_value=False),
                patch("app.tts.qwen_character_runtime.RUNTIME_ROOT", new=qwen_root),
                patch("app.tts.qwen_character_runtime.VENV_ROOT", new=venv_root),
                patch("app.tts.qwen_character_runtime.PYTHON_ROOT", new=python_root),
                patch("app.tts.qwen_character_runtime.MARKER", new=marker),
                patch("app.tts.qwen_character_runtime.INSTALLER_PATH", new=installer),
                patch("app.tts.qwen_character_runtime.INSTALLER_LOG", new=installer_log),
                patch("app.tts.qwen_character_runtime.MODEL_IDS", new=model_kinds),
                patch("app.tts.qwen_character_runtime.MODEL_DIRS", new=model_dirs),
                patch("app.tts.qwen_character_runtime.model_installed", return_value=False),
                patch("app.tts.qwen_character_runtime.runtime_ready", return_value=False),
            ):
                rows = bridge._models_list({})

            by_id = {row["model_id"]: row for row in rows}
            self.assertEqual(by_id["chatterbox-runtime"]["storage_bytes"], 9)
            # Count the isolated Python runtimes and metadata, but leave the
            # separately inventoried model weights out of the runtime total.
            self.assertEqual(by_id["qwen-runtime"]["storage_bytes"], 21)
            self.assertEqual(by_id["custom-0.6b"]["storage_bytes"], 13)


    def test_piper_install_downloads_and_validates_model_and_config_pair(self):
        with tempfile.TemporaryDirectory() as temporary:
            model_root = Path(temporary) / "Models"
            model = b"piper-model-bytes" * 100
            config = json.dumps({
                "audio": {"sample_rate": 22050},
                "phoneme_id_map": {"_": [0]},
                "phoneme_type": "espeak",
                "speaker_id_map": {"default": 0},
                "language": {"code": "en_US"},
            }).encode()
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

    def test_models_center_file_readiness_rejects_partial_assets_without_loading_them(self):
        from tempfile import TemporaryDirectory
        from app.ui.models_page import _file_ready

        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            partial = root / "partial.gguf"
            complete = root / "complete.gguf"
            partial.write_bytes(b"partial")
            complete.write_bytes(b"x" * 1024)

            self.assertFalse(_file_ready(partial))
            self.assertTrue(_file_ready(complete))
            self.assertFalse(_file_ready(root / "missing.gguf"))

    def test_models_center_inventory_distinguishes_incomplete_local_runtimes(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "models_page.py").read_text(encoding="utf-8")
        refresh = source.split("def refresh(self) -> None:", 1)[1].split(
            "\n    def _update_operation_controls(", 1
        )[0]

        self.assertIn("if qwen_runtime_ready():", refresh)
        self.assertIn("Qwen3-TTS Python runtime — Incomplete", refresh)
        self.assertIn('ai_server = ai_root / "llama-server.exe"', refresh)
        self.assertIn("ai_ready = _file_ready(ai_server) and any(_file_ready(path) for path in ai_models)", refresh)
        self.assertIn("Audiobook AI — Incomplete", refresh)
        self.assertIn("Kokoro 82M — Incomplete", refresh)
        self.assertNotIn("if audiobook_ai_installed()", refresh)
        self.assertIn('"qwen-runtime")', refresh)
        self.assertIn("_directory_has_entries(model_root)", refresh)
        self.assertIn("Qwen3-TTS • {qwen_labels.get(kind, kind)} — Incomplete", refresh)
        self.assertIn('component_id = f"qwen-model:{kind}"', refresh)
        self.assertIn('"audiobook-ai")', refresh)

    def test_active_model_lifecycle_blocks_preview_analysis_and_generation(self):
        bridge = self.make_bridge()
        bridge._jobs["active-model-job"] = {
            "state": "running",
            "type": "model-install",
        }
        for action, invoke in (
            ("voice preview", lambda: bridge._voice_preview({})),
            ("character analysis", lambda: bridge._character_analyze({})),
            ("audiobook generation", lambda: bridge._production_generate_book({})),
        ):
            with self.subTest(action=action):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "while a model install, repair or uninstall is running",
                ):
                    invoke()

    def test_starting_second_model_operation_is_blocked_while_one_is_running(self):
        bridge = self.make_bridge()
        bridge._jobs["active-model-job"] = {"state": "running", "type": "model-install"}
        with self.assertRaisesRegex(RuntimeError, "Another model installation"):
            bridge._models_start_operation("repair", "qwen-runtime", {})


    def test_qwen_model_readiness_rejects_small_shard_shortfalls_and_malformed_config(self):
        from app.tts.qwen_character_runtime import model_installed

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "custom-0.6b"
            root.mkdir(parents=True)
            config_path = root / "config.json"
            config_path.write_text("{}", encoding="utf-8")
            index_path = root / "model.safetensors.index.json"
            index_path.write_text(json.dumps({
                "metadata": {"total_size": 4096},
                "weight_map": {
                    "layer_a.weight": "model-00001-of-00002.safetensors",
                    "layer_b.weight": "model-00002-of-00002.safetensors",
                },
            }), encoding="utf-8")
            first = root / "model-00001-of-00002.safetensors"
            second = root / "model-00002-of-00002.safetensors"
            first.write_bytes(b"a" * 2048)

            with patch("app.tts.qwen_character_runtime.MODEL_DIRS", {"custom-0.6b": root}):
                second.write_bytes(b"b" * 1900)
                self.assertFalse(
                    model_installed("custom-0.6b"),
                    "a small aggregate weight shortfall must not pass a 95% tolerance",
                )
                second.write_bytes(b"b" * 2048)
                self.assertTrue(model_installed("custom-0.6b"))
                config_path.write_text("{invalid json", encoding="utf-8")
                self.assertFalse(
                    model_installed("custom-0.6b"),
                    "malformed model config must not be marked installed",
                )

    def test_kokoro_download_rejects_truncated_http_body_and_preserves_existing_target(self):
        from app.ui.models_page import KokoroDownloadWorker

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "kokoro.bin"
            target.write_bytes(b"existing-valid-target")
            partial = _FakeResponse(b"x" * 1024)
            partial.headers = {"Content-Length": "2048"}
            worker = KokoroDownloadWorker()

            with patch("urllib.request.urlopen", return_value=partial):
                with self.assertRaisesRegex(RuntimeError, "expected bytes"):
                    worker._download(
                        "https://example.invalid/asset",
                        target,
                        "test asset",
                        minimum_bytes=512,
                    )

            self.assertEqual(target.read_bytes(), b"existing-valid-target")
            self.assertFalse(target.with_suffix(".bin.part").exists())

    def test_kokoro_download_rejects_too_small_asset_even_when_transfer_is_complete(self):
        from app.ui.models_page import KokoroDownloadWorker

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "voices.bin"
            response = _FakeResponse(b"x" * 1024)
            worker = KokoroDownloadWorker()

            with patch("urllib.request.urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "at least"):
                    worker._download(
                        "https://example.invalid/asset",
                        target,
                        "test asset",
                        minimum_bytes=2048,
                    )

            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".bin.part").exists())


if __name__ == "__main__":
    unittest.main()
