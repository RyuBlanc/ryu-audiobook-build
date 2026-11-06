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

    def test_premium_v2_uninstall_ui_previews_exact_impact_and_refreshes_voice_state(self):
        source = (Path(__file__).resolve().parents[1] / "assets" / "frontend" /
                  "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        handler = source.split("if (button.matches('[data-model-install]", 1)[1].split(
            "if (button.matches('[data-assign-character]'))", 1
        )[0]
        self.assertIn("models.uninstall_preflight", handler)
        self.assertIn("impact.total_bytes", handler)
        self.assertIn("impact.file_count", handler)
        self.assertIn("impact.targets", handler)
        self.assertIn("impact.dependencies", handler)
        self.assertIn("impact.preserved", handler)
        self.assertIn("Confirm exact uninstall", handler)
        self.assertIn("models.uninstall", handler)
        self.assertIn("refreshModels()", handler)
        self.assertIn("refreshVoices()", handler)
        self.assertIn("refreshProviderCatalog", handler)
        self.assertIn("Background Jobs", handler)

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

    def test_chatterbox_runtime_uninstall_preflight_uses_provider_runtime_storage(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "Models"
            runtime = base / "Provider Runtime" / "chatterbox"
            runtime.mkdir(parents=True)
            (runtime / "runtime.json").write_text("{}", encoding="utf-8")
            row = {"model_id":"chatterbox-runtime","name":"Chatterbox Runtime",
                   "component_type":"model","installed":True}
            with (
                patch("app.core.paths.models_root", return_value=models),
                patch("app.tts.chatterbox_runtime.RUNTIME_DIR", runtime),
                patch("app.tts.model_registry.build_inventory", return_value=[row]),
            ):
                impact = bridge._models_uninstall_preflight({"model_id":"chatterbox-runtime"})
                outcome = bridge._models_uninstall_component("chatterbox-runtime", {}, lambda _message: None)
            self.assertEqual(impact["targets"], [str(runtime)])
            self.assertFalse(runtime.exists())
            self.assertIn("Chatterbox runtime", outcome)

    def test_individual_qwen_model_uninstall_preserves_other_model_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Models"
            runtime_root = root / "qwen3-tts"
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
                patch("app.tts.model_registry.build_inventory", return_value=[
                    {"model_id": "custom-0.6b", "name": "Qwen CustomVoice 0.6B",
                     "component_type": "model", "installed": True}
                ]),
            ):
                message = bridge._models_uninstall_component("custom-0.6b", {}, lambda _message: None)

            self.assertFalse(remove.exists())
            self.assertTrue(preserve.is_dir())
            self.assertTrue((preserve / "config.json").is_file())
            self.assertIn("other model folders", message)

    def test_model_uninstall_removes_only_paths_owned_by_selected_component(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Models"
            selected = root / "qwen3-tts" / "custom-0.6b"
            sibling = root / "qwen3-tts" / "base-0.6b"
            (selected / "weights").mkdir(parents=True)
            (selected / "weights" / "model.safetensors").write_bytes(b"weights")
            sibling.mkdir(parents=True)
            (sibling / "config.json").write_text("{}", encoding="utf-8")

            PremiumV2Bridge._models_remove_path(selected, root / "qwen3-tts")

            self.assertFalse(selected.exists())
            self.assertTrue((sibling / "config.json").is_file())

    def test_model_uninstall_refuses_symbolic_link_targets_and_nested_links(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            owned_root = base / "Models" / "qwen3-tts"
            outside = base / "Projects" / "keep.json"
            owned_root.mkdir(parents=True)
            outside.parent.mkdir(parents=True)
            outside.write_text("preserve", encoding="utf-8")
            link = owned_root / "linked-model"
            try:
                link.symlink_to(outside.parent, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("The current test account cannot create symbolic links.")
            with self.assertRaisesRegex(RuntimeError, "symbolic-link target"):
                PremiumV2Bridge._models_remove_path(link, owned_root)
            self.assertTrue(outside.is_file())
            self.assertEqual(outside.read_text(encoding="utf-8"), "preserve")

    def test_models_remove_path_rejects_symlinked_component_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            actual = base / "actual"
            actual.mkdir()
            link = base / "linked-root"
            try:
                link.symlink_to(actual, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("The current test account cannot create symbolic links.")
            target = actual / "child"
            target.mkdir()
            with self.assertRaisesRegex(RuntimeError, "symbolic-link component root"):
                PremiumV2Bridge._models_remove_path(target, link)
            self.assertTrue(target.is_dir())

    def test_model_uninstall_refuses_component_paths_outside_owned_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            owned_root = base / "Models" / "qwen3-tts"
            protected = base / "Projects" / "important.json"
            owned_root.mkdir(parents=True)
            protected.parent.mkdir(parents=True)
            protected.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "outside the selected component root"):
                PremiumV2Bridge._models_remove_path(protected, owned_root)

            self.assertEqual(protected.read_text(encoding="utf-8"), "keep")

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

    def test_chatterbox_uninstall_uses_provider_runtime_parent_and_refuses_installed_dependents(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "Models"
            runtime_parent = base / "ProviderRuntime"
            runtime = runtime_parent / "chatterbox"
            runtime.mkdir(parents=True)
            marker = runtime / "runtime.json"
            marker.write_text("{}", encoding="utf-8")
            row = {
                "model_id": "chatterbox-model-assets",
                "name": "Chatterbox model assets",
                "component_type": "model",
                "installed": True,
                "runtime_path": str(runtime),
            }
            with (
                patch("app.core.paths.models_root", return_value=models),
                patch("app.tts.chatterbox_runtime.RUNTIME_DIR", runtime),
                patch("app.tts.model_registry.build_inventory", return_value=[
                    {"model_id": "chatterbox-runtime", "name": "Chatterbox Runtime",
                     "component_type": "provider", "installed": True},
                    row,
                ]),
            ):
                with self.assertRaisesRegex(RuntimeError, "shared by installed components"):
                    bridge._models_uninstall_component("chatterbox-runtime", {}, lambda _message: None)
                row["installed"] = False
                outcome = bridge._models_uninstall_component("chatterbox-runtime", {}, lambda _message: None)
            self.assertFalse(runtime.exists())
            self.assertIn("shared Chatterbox runtime", outcome)

    def test_qwen_runtime_uninstall_only_removes_runtime_owned_paths(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime_root = base / "ProviderRuntime" / "qwen3-tts"
            venv = runtime_root / "runtime"
            python_root = runtime_root / "python312"
            marker = runtime_root / "runtime.json"
            installer = runtime_root / "python.exe"
            install_log = runtime_root / "python-install.log"
            weights = base / "Models" / "qwen3-tts" / "custom-0.6b"
            for folder in (venv, python_root, weights):
                folder.mkdir(parents=True)
            for path in (marker, installer, install_log):
                path.write_text("runtime", encoding="utf-8")
            with (
                patch("app.core.paths.models_root", return_value=base / "Models"),
                patch("app.tts.qwen_character_runtime.RUNTIME_ROOT", runtime_root),
                patch("app.tts.qwen_character_runtime.VENV_ROOT", venv),
                patch("app.tts.qwen_character_runtime.PYTHON_ROOT", python_root),
                patch("app.tts.qwen_character_runtime.MARKER", marker),
                patch("app.tts.qwen_character_runtime.INSTALLER_PATH", installer),
                patch("app.tts.qwen_character_runtime.INSTALLER_LOG", install_log),
                patch("app.tts.model_registry.build_inventory", return_value=[
                    {"model_id": "qwen-runtime", "name": "Qwen3-TTS Runtime",
                     "component_type": "provider", "installed": True}
                ]),
            ):
                outcome = bridge._models_uninstall_component("qwen-runtime", {}, lambda _message: None)
            self.assertFalse(venv.exists())
            self.assertFalse(python_root.exists())
            self.assertFalse(marker.exists())
            self.assertTrue(weights.is_dir())
            self.assertIn("weights", outcome)

    def test_uninstall_preflight_reports_exact_target_sizes_and_dependent_runtime_block(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "Models"
            runtime_parent = base / "ProviderRuntime"
            runtime = runtime_parent / "chatterbox"
            runtime.mkdir(parents=True)
            payload_file = runtime / "runtime.bin"
            payload_file.write_bytes(b"123456789")
            model = {
                "model_id": "chatterbox-runtime",
                "name": "Chatterbox Runtime",
                "component_type": "model",
                "installed": True,
            }
            dependent = {
                "model_id": "chatterbox-model-assets",
                "name": "Chatterbox Model Assets",
                "component_type": "model",
                "installed": True,
                "runtime_path": str(runtime),
            }
            with (
                patch("app.core.paths.models_root", return_value=models),
                patch("app.tts.chatterbox_runtime.RUNTIME_DIR", runtime),
                patch("app.tts.model_registry.build_inventory", return_value=[model, dependent]),
            ):
                result = bridge._models_uninstall_preflight({"model_id": "chatterbox-runtime"})
            self.assertTrue(result["blocked"])
            self.assertEqual(result["file_count"], 1)
            self.assertEqual(result["total_bytes"], 9)
            self.assertEqual(result["targets"], [str(runtime)])
            self.assertIn("Chatterbox Model Assets", result["block_reason"])

    def test_premium_v2_storage_root_change_refuses_to_replace_a_disconnected_location(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        handler = source.split("def _storage_choose_root", 1)[1].split("def _storage_open_root", 1)[0]
        self.assertIn("if not source.is_dir()", handler)
        self.assertIn("Reconnect its drive before changing the configured path", handler)
        self.assertIn("existing inventory must not be silently orphaned", handler)

    def test_storage_root_validation_keeps_model_weights_and_provider_runtime_separate(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "data" / "Models"
            runtime = base / "Runtime"
            cache = models / "huggingface"
            library = base / "Library"
            exports = base / "Exports"
            temp_root = base / "Temp"
            roots = {
                "library": ("library", library, library),
                "audio_assets": ("audio_assets", exports, exports),
                "models": ("models", models, models),
                "runtime": ("runtime", runtime, runtime),
                "model_cache": ("model_cache", cache, cache),
                "temporary": ("temporary", temp_root, temp_root),
            }
            with self.assertRaisesRegex(ValueError, "runtime"):
                bridge._validate_storage_root_separation("models", runtime, roots)
            with self.assertRaisesRegex(ValueError, "models"):
                bridge._validate_storage_root_separation("runtime", models, roots)
            # The legacy Hugging Face cache is intentionally nested in Models.
            bridge._validate_storage_root_separation("model_cache", cache, roots)
            # Existing installations may share a Models base while keeping
            # model weights and provider runtimes in separate subdirectories.
            roots["runtime"] = ("runtime", models, models)
            bridge._validate_storage_root_separation("models", models, roots)
            bridge._validate_storage_root_separation("runtime", models, roots)
            bridge._validate_storage_root_separation("model_cache", cache, roots)
            with self.assertRaisesRegex(ValueError, "contain the Models root"):
                bridge._validate_storage_root_separation("model_cache", base / "data", roots)

    def test_storage_migration_excludes_new_application_jobs(self):
        bridge = self.make_bridge()
        bridge._jobs["active-storage-migration"] = {
            "state": "running", "type": "storage-migration"
        }
        with self.assertRaisesRegex(RuntimeError, "verified storage migration is running"):
            bridge._new_job("voice-preview", "Preview", "Must wait for storage migration")

    def test_premium_v2_cleanup_removes_allowlisted_cache_and_temp_without_touching_models(self):
        from PySide6.QtWidgets import QMessageBox

        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "Models"
            cache = models / "huggingface"
            downloads = cache / "downloads"
            temp_root = base / "Temp"
            staging = temp_root / "staging"
            library = base / "Library"
            exports = base / "Audiobooks"
            for path in (downloads, staging, library, exports):
                path.mkdir(parents=True, exist_ok=True)
            model_file = models / "voice-weights.bin"
            download_file = downloads / "partial.bin"
            temp_file = staging / "work.tmp"
            model_file.write_bytes(b"model")
            download_file.write_bytes(b"partial")
            temp_file.write_bytes(b"temporary")
            with (
                patch("app.core.paths.models_root", return_value=models),
                patch("app.core.paths.model_cache_root", return_value=cache),
                patch("app.core.paths.runtimes_root", return_value=models),
                patch("app.core.paths.temporary_root", return_value=temp_root),
                patch("app.core.paths.library_root", return_value=library),
                patch("app.core.paths.audiobooks_root", return_value=exports),
                patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes),
            ):
                result = bridge._storage_cleanup_temp({})
            self.assertTrue(result["cleaned"])
            self.assertEqual(result["candidate_count"], 2)
            self.assertEqual(len(result["removed"]), 2)
            self.assertFalse(downloads.exists())
            self.assertFalse(staging.exists())
            self.assertTrue(model_file.is_file())

    def test_premium_v2_cleanup_refuses_to_run_while_any_application_job_is_active(self):
        bridge = self.make_bridge()
        bridge._jobs["active-preview"] = {"state": "running", "type": "preview"}
        with self.assertRaisesRegex(RuntimeError, "blocked while application jobs are active"):
            bridge._storage_cleanup_temp({})

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


    def test_qwen_bootstrap_download_rejects_truncated_http_body_and_preserves_existing_installer(self):
        from app.tts import qwen_character_runtime as qwen_runtime

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "python-installer.exe"
            target.write_bytes(b"existing-valid-installer")
            response = _FakeResponse(b"x" * 5_000_128)
            response.headers = {"Content-Length": str(8_000_000)}

            with patch("app.tts.qwen_character_runtime.urllib.request.urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "expected bytes"):
                    qwen_runtime._download_file(
                        "https://example.invalid/python-installer.exe",
                        target,
                    )

            self.assertEqual(target.read_bytes(), b"existing-valid-installer")
            self.assertFalse(target.with_suffix(".exe.part").exists())

    def test_qwen_bootstrap_download_rejects_short_file_without_content_length(self):
        from app.tts import qwen_character_runtime as qwen_runtime

        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "python-installer.exe"
            response = _FakeResponse(b"x" * 1024)
            response.headers = {}

            with patch("app.tts.qwen_character_runtime.urllib.request.urlopen", return_value=response):
                with self.assertRaisesRegex(RuntimeError, "only"):
                    qwen_runtime._download_file(
                        "https://example.invalid/python-installer.exe",
                        target,
                    )

            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".exe.part").exists())


    def test_qwen_shared_runtime_uninstall_preserves_all_model_weights_and_project_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Models"
            runtime_root = base / "ProviderRuntime" / "qwen3-tts"
            model_root = root / "qwen3-tts"
            venv_root = runtime_root / "runtime"
            python_root = runtime_root / "python312"
            marker = runtime_root / "runtime.json"
            installer = runtime_root / "python-installer.exe"
            installer_log = runtime_root / "python-install.log"
            model_dirs = {
                "custom-0.6b": model_root / "custom-0.6b",
                "custom-1.7b": model_root / "custom-1.7b",
                "design-1.7b": model_root / "design-1.7b",
                "base-0.6b": model_root / "base-0.6b",
                "base-1.7b": model_root / "base-1.7b",
            }
            for directory in (venv_root, python_root, *model_dirs.values()):
                directory.mkdir(parents=True, exist_ok=True)
            for index, directory in enumerate(model_dirs.values(), start=1):
                (directory / "model.safetensors").write_bytes(bytes([index]) * index)
            for file_path in (marker, installer, installer_log):
                file_path.write_text("runtime metadata", encoding="utf-8")
            project_file = Path(temporary) / "Projects" / "project.json"
            project_file.parent.mkdir(parents=True)
            project_file.write_text('{"project":"preserve"}', encoding="utf-8")
            settings_root = Path(temporary) / "Settings"
            settings_root.mkdir(parents=True)
            profile_file = settings_root / "voice_profiles.json"
            profile_file.write_text('{"profiles":[{"name":"Narrator"}]}', encoding="utf-8")
            assignment_file = settings_root / "character_assignments.json"
            assignment_file.write_text('{"chapter-1":{"Mira":"Voice Mira"}}', encoding="utf-8")

            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.qwen_character_runtime.RUNTIME_ROOT", runtime_root),
                patch("app.tts.qwen_character_runtime.MODEL_DIRS", model_dirs),
                patch("app.tts.qwen_character_runtime.VENV_ROOT", venv_root),
                patch("app.tts.qwen_character_runtime.PYTHON_ROOT", python_root),
                patch("app.tts.qwen_character_runtime.MARKER", marker),
                patch("app.tts.qwen_character_runtime.INSTALLER_PATH", installer),
                patch("app.tts.qwen_character_runtime.INSTALLER_LOG", installer_log),
            ):
                message = bridge._models_uninstall_component("qwen-runtime", {}, lambda _message: None)

            self.assertFalse(venv_root.exists())
            self.assertFalse(python_root.exists())
            self.assertFalse(marker.exists())
            self.assertFalse(installer.exists())
            self.assertFalse(installer_log.exists())
            for directory in model_dirs.values():
                self.assertTrue(directory.is_dir())
                self.assertTrue(any(directory.iterdir()))
            self.assertEqual(project_file.read_text(encoding="utf-8"), '{"project":"preserve"}')
            self.assertEqual(profile_file.read_text(encoding="utf-8"), '{"profiles":[{"name":"Narrator"}]}')
            self.assertEqual(assignment_file.read_text(encoding="utf-8"), '{"chapter-1":{"Mira":"Voice Mira"}}')
            self.assertIn("model weights", message)

    def test_chatterbox_shared_runtime_uninstall_preserves_cached_model_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Models"
            runtime_root = base / "ProviderRuntime" / "chatterbox"
            runtime_file = runtime_root / "Lib" / "site-packages" / "chatterbox.py"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_text("runtime", encoding="utf-8")
            cache_root = root / "huggingface" / "hub" / "models--resemble-ai--chatterbox"
            cache_file = cache_root / "snapshots" / "abc" / "model.safetensors"
            cache_file.parent.mkdir(parents=True)
            cache_file.write_bytes(b"model weights")
            settings_root = base / "Settings"
            settings_root.mkdir(parents=True)
            profile_file = settings_root / "voice_profiles.json"
            profile_file.write_text('{"profiles":[{"name":"Narrator"}]}', encoding="utf-8")
            assignment_file = settings_root / "character_assignments.json"
            assignment_file.write_text('{"chapter-1":{"Mira":"Voice Mira"}}', encoding="utf-8")
            project_file = base / "Projects" / "project.json"
            project_file.parent.mkdir(parents=True)
            project_file.write_text('{"project":"keep"}', encoding="utf-8")
            bridge = self.make_bridge()

            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.chatterbox_runtime.RUNTIME_DIR", runtime_root),
                patch("app.tts.model_registry.mark_installed"),
            ):
                message = bridge._models_uninstall_component(
                    "chatterbox-runtime", {}, lambda _message: None
                )

            self.assertFalse(runtime_root.exists())
            self.assertTrue(cache_file.is_file())
            self.assertEqual(cache_file.read_bytes(), b"model weights")
            self.assertEqual(profile_file.read_text(encoding="utf-8"), '{"profiles":[{"name":"Narrator"}]}')
            self.assertEqual(assignment_file.read_text(encoding="utf-8"), '{"chapter-1":{"Mira":"Voice Mira"}}')
            self.assertEqual(project_file.read_text(encoding="utf-8"), '{"project":"keep"}')
            self.assertIn("Saved profiles and books were kept", message)

    def test_individual_qwen_uninstall_refresh_reports_removed_model_as_missing(self):
        from app.tts.model_registry import build_inventory

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Models"
            qwen_root = root / "qwen3-tts"
            venv_root = qwen_root / "runtime"
            python_root = qwen_root / "python312"
            marker = qwen_root / "runtime.json"
            installer = qwen_root / "python-installer.exe"
            installer_log = qwen_root / "python-install.log"
            model_kinds = {
                "custom-0.6b": "example/custom",
                "custom-1.7b": "example/custom-large",
                "design-1.7b": "example/design",
                "base-0.6b": "example/base",
                "base-1.7b": "example/base-large",
            }
            model_dirs = {kind: qwen_root / kind for kind in model_kinds}
            selected = model_dirs["custom-0.6b"]
            sibling = model_dirs["base-0.6b"]
            selected.mkdir(parents=True)
            sibling.mkdir(parents=True)
            (selected / "weights.safetensors").write_bytes(b"selected")
            (sibling / "weights.safetensors").write_bytes(b"sibling")
            venv_root.mkdir(parents=True)
            python_root.mkdir(parents=True)
            (venv_root / "Scripts").mkdir(parents=True)
            python_executable = venv_root / "Scripts" / "python.exe"
            python_executable.write_bytes(b"python")
            bridge = self.make_bridge()

            def model_is_installed(kind):
                directory = model_dirs[kind]
                return directory.is_dir() and any(item.is_file() for item in directory.rglob("*"))

            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.model_registry.models_root", return_value=root),
                patch("app.tts.model_registry.settings_root", return_value=base / "Settings"),
                patch("app.tts.providers.piper.PiperProvider.model_paths", return_value=[]),
                patch("app.tts.providers.kokoro.KokoroProvider.assets_available", return_value=False),
                patch("app.tts.chatterbox_runtime.RUNTIME_DIR", root / "chatterbox-runtime"),
                patch("app.tts.chatterbox_runtime.runtime_ready", return_value=False),
                patch("app.tts.qwen_character_runtime.RUNTIME_ROOT", qwen_root),
                patch("app.tts.qwen_character_runtime.VENV_ROOT", venv_root),
                patch("app.tts.qwen_character_runtime.PYTHON_ROOT", python_root),
                patch("app.tts.qwen_character_runtime.PYTHON", python_executable),
                patch("app.tts.qwen_character_runtime.MARKER", marker),
                patch("app.tts.qwen_character_runtime.INSTALLER_PATH", installer),
                patch("app.tts.qwen_character_runtime.INSTALLER_LOG", installer_log),
                patch("app.tts.qwen_character_runtime.MODEL_IDS", model_kinds),
                patch("app.tts.qwen_character_runtime.MODEL_DIRS", model_dirs),
                patch("app.tts.qwen_character_runtime.model_installed", side_effect=model_is_installed),
                patch("app.tts.qwen_character_runtime.runtime_ready", return_value=True),
            ):
                bridge._models_uninstall_component("custom-0.6b", {}, lambda _message: None)
                refreshed = bridge._models_list({})

            by_id = {row["model_id"]: row for row in refreshed}
            self.assertFalse(by_id["custom-0.6b"]["installed"])
            self.assertEqual(by_id["custom-0.6b"]["status"], "Missing")
            self.assertTrue(by_id["base-0.6b"]["installed"])
            self.assertTrue((sibling / "weights.safetensors").is_file())


if __name__ == "__main__":
    unittest.main()
