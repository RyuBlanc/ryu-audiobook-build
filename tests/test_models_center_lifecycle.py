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

    def test_performance_benchmark_requires_an_installed_local_piper_voice(self):
        bridge = self.make_bridge()
        with patch("app.tts.providers.piper.PiperProvider.model_paths", return_value=[]):
            with self.assertRaisesRegex(ValueError, "Install a local Piper voice"):
                bridge._performance_benchmark({})

    def test_performance_benchmark_runs_in_background_and_reports_real_measurement(self):
        from app.tts.benchmark import BenchmarkResult

        bridge = self.make_bridge()
        result = BenchmarkResult(
            provider="PiperProvider", backend="automatic", seconds=1.25,
            audio_seconds=2.5, realtime_factor=0.5, success=True,
        )

        class ImmediateThread:
            def __init__(self, target, args=(), **_kwargs):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            voice = base / "Models" / "piper" / "en_US-test-medium.onnx"
            voice.parent.mkdir(parents=True)
            voice.write_bytes(b"test model")
            with (
                patch.object(bridge, "_jobs_path", return_value=base / "jobs.json"),
                patch.object(bridge, "_history_path", return_value=base / "history.json"),
                patch.object(bridge, "_performance_history_path", return_value=base / "performance-history.json"),
                patch("app.tts.providers.piper.PiperProvider.model_paths", return_value=[voice]),
                patch("app.tts.benchmark.benchmark_provider", return_value=result),
                patch("threading.Thread", ImmediateThread),
            ):
                queued = bridge._performance_benchmark({})
                row = bridge._jobs[queued["job_id"]]
                self.assertEqual(row["state"], "completed")
                self.assertTrue(row["result"]["success"])
                self.assertEqual(row["result"]["voice"], voice.stem)
                self.assertEqual(len(bridge._performance_history), 1)
                self.assertEqual(bridge._performance_history[0]["result"]["voice"], voice.stem)

                device = type("Device", (), {
                    "backend":"cpu", "device":"cpu", "name":"CPU",
                    "memory_gb":0.0, "supported":True, "reason":"CPU fallback"
                })()
                with (
                    patch("psutil.cpu_percent", return_value=12.0),
                    patch("psutil.virtual_memory", return_value=type("VM", (), {
                        "total":8*1024**3, "available":4*1024**3, "percent":50.0
                    })()),
                    patch("app.tts.qwen_accelerator.detect_accelerators", return_value=(device,)),
                    patch("app.tts.qwen_accelerator.best_accelerator", return_value=device),
                ):
                    info = bridge._performance_info({})
                self.assertEqual(info["generation_seconds"], 1.25)
                self.assertEqual(info["benchmark_audio_seconds"], 2.5)
                self.assertEqual(info["benchmark_realtime_factor"], 0.5)
                self.assertEqual(info["benchmark_voice"], voice.stem)
                self.assertEqual(len(info["benchmark_history"]), 1)
                self.assertEqual(info["benchmark_history"][0]["result"]["voice"], voice.stem)

    def test_qwen_warm_preview_benchmark_records_real_duration_and_target_verdict(self):
        from app.tts.benchmark import BenchmarkResult

        bridge = self.make_bridge()
        result = BenchmarkResult(
            provider="QwenCharacterProvider", backend="cuda", seconds=45.0,
            audio_seconds=30.0, realtime_factor=1.5, success=True,
            requested_backend="automatic", backend_verified=True,
        )
        providers = []
        class FakeQwenProvider:
            def __init__(self, **kwargs):
                self.kwargs = kwargs
                self.last_execution_context = {
                    "device": "cuda:0", "backend": "cuda",
                    "model_kind": kwargs["model_kind"], "verified_inference": True,
                }
                self.closed = False
                providers.append(self)
            def synthesize(self, _text, output_path, voice=None):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(b"warmup")
                return output_path
            def close(self):
                self.closed = True
            @property
            def execution_backend(self):
                return self.last_execution_context["backend"]
            @property
            def execution_backend_verified(self):
                return True
            @property
            def execution_providers(self):
                return ()

        class ImmediateThread:
            def __init__(self, target, args=(), **_kwargs):
                self.target, self.args = target, args
            def start(self):
                self.target(*self.args)

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            with (
                patch.object(bridge, "_qwen_model_installed", return_value=True),
                patch("app.tts.providers.qwen_character.QwenCharacterProvider", FakeQwenProvider),
                patch("app.tts.benchmark.benchmark_provider", return_value=result),
                patch.object(bridge, "_performance_info", return_value={
                    "platform": "Windows test", "processor": "CPU test",
                    "gpu_name": "RTX test", "backend": "cuda",
                    "recommended_backend": "CUDA", "backend_active": True,
                    "accelerators": [], "cpu_percent": 45.0,
                    "memory_total_bytes": 16 * 1024**3,
                    "memory_available_bytes": 8 * 1024**3,
                    "memory_percent": 50.0, "gpu_percent": 55.0,
                    "vram_used_mb": 2048.0, "vram_total_mb": 8192.0,
                    "gpu_temperature_c": 60.0, "last_inference": {},
                    "measured_at": "2026-11-06T13:00:00Z",
                }),
                patch.object(bridge, "_jobs_path", return_value=base / "jobs.json"),
                patch.object(bridge, "_history_path", return_value=base / "history.json"),
                patch.object(bridge, "_performance_history_path", return_value=base / "performance-history.json"),
                patch("threading.Thread", ImmediateThread),
            ):
                queued = bridge._performance_qwen_benchmark({"model_kind": "custom-1.7b"})
                row = bridge._jobs[queued["job_id"]]
                self.assertEqual(row["state"], "completed")
                self.assertTrue(row["result"]["target_duration_met"])
                self.assertTrue(row["result"]["under_60_seconds"])
                self.assertTrue(row["result"]["target_performance_met"])
                self.assertEqual(row["result"]["execution_device"], "cuda:0")
                self.assertEqual(row["result"]["model_kind"], "custom-1.7b")
                self.assertEqual(len(providers), 1)
                self.assertTrue(providers[0].closed)

    def test_performance_history_clear_does_not_delete_background_job_history(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            history_path = Path(temporary) / "performance-history.json"
            job = {"job_id": "benchmark-1", "type": "tts-benchmark", "state": "completed"}
            bridge._jobs[job["job_id"]] = dict(job)
            bridge._history[job["job_id"]] = dict(job)
            with patch.object(bridge, "_performance_history_path", return_value=history_path):
                bridge._performance_history = [{
                    "benchmark_id": "benchmark-1",
                    "job_id": "benchmark-1",
                    "measured_at": "2026-11-06T12:00:00Z",
                    "state": "completed",
                    "result": {"success": True, "voice": "en_US-test-medium"},
                }]
                bridge._persist_performance_history()
                result = bridge._performance_history_clear({})
                self.assertEqual(result["cleared"], 1)
                self.assertTrue(result["background_job_history_preserved"])
                self.assertIn("benchmark-1", bridge._jobs)
                self.assertIn("benchmark-1", bridge._history)
                self.assertEqual(json.loads(history_path.read_text(encoding="utf-8")), [])

    def test_performance_info_reports_real_cpu_memory_and_gpu_device_inventory(self):
        bridge = self.make_bridge()
        device = type("Device", (), {
            "backend":"cuda", "device":"cuda:0", "name":"RTX Test",
            "memory_gb":8.0, "supported":True, "reason":"CUDA runtime active"
        })()
        with (
            patch("psutil.cpu_percent", return_value=37.5),
            patch("psutil.virtual_memory", return_value=type("VM", (), {
                "total":16*1024**3, "available":6*1024**3, "percent":62.5
            })()),
            patch("app.tts.qwen_accelerator.detect_accelerators", return_value=(device,)),
            patch("app.tts.qwen_accelerator.best_accelerator", return_value=device),
        ):
            result = bridge._performance_info({"refresh":True})
        self.assertTrue(result["available"])
        self.assertEqual(result["cpu_percent"],37.5)
        self.assertEqual(result["memory_total_bytes"],16*1024**3)
        self.assertEqual(result["memory_available_bytes"],6*1024**3)
        self.assertEqual(result["gpu_name"],"RTX Test")
        self.assertEqual(result["backend"],"cuda")
        self.assertTrue(result["backend_active"])
        self.assertIsNone(result["generation_seconds"])

    def test_performance_info_distinguishes_gpu_candidate_from_active_runtime(self):
        bridge = self.make_bridge()
        candidate = type("Device", (), {
            "backend":"cuda-candidate", "device":"cpu", "name":"RTX Test",
            "memory_gb":8.0, "supported":False, "reason":"CUDA runtime not active"
        })()
        with (
            patch("psutil.cpu_percent", return_value=11.0),
            patch("psutil.virtual_memory", return_value=type("VM", (), {
                "total":8, "available":4, "percent":50.0
            })()),
            patch("app.tts.qwen_accelerator.detect_accelerators", return_value=(candidate,)),
            patch("app.tts.qwen_accelerator.best_accelerator", return_value=candidate),
        ):
            result = bridge._performance_info({})
        self.assertEqual(result["backend"],"cuda-candidate")
        self.assertFalse(result["backend_active"])
        self.assertIn("runtime not active",result["recommended_backend"])
        self.assertIsNone(result["gpu_percent"])
        self.assertIsNone(result["vram_used_mb"])

    def test_performance_info_reports_real_cpu_memory_and_gpu_device_inventory(self):
        bridge = self.make_bridge()
        device = type("Device", (), {
            "backend":"cuda", "device":"cuda:0", "name":"RTX Test",
            "memory_gb":8.0, "supported":True, "reason":"CUDA runtime active"
        })()
        with (
            patch("psutil.cpu_percent", return_value=37.5),
            patch("psutil.virtual_memory", return_value=type("VM", (), {
                "total":16*1024**3, "available":6*1024**3, "percent":62.5
            })()),
            patch("app.tts.qwen_accelerator.detect_accelerators", return_value=(device,)),
            patch("app.tts.qwen_accelerator.best_accelerator", return_value=device),
        ):
            result = bridge._performance_info({"refresh":True})
        self.assertTrue(result["available"])
        self.assertEqual(result["cpu_percent"],37.5)
        self.assertEqual(result["memory_total_bytes"],16*1024**3)
        self.assertEqual(result["memory_available_bytes"],6*1024**3)
        self.assertEqual(result["gpu_name"],"RTX Test")
        self.assertEqual(result["backend"],"cuda")
        self.assertTrue(result["backend_active"])
        self.assertIsNone(result["generation_seconds"])

    def test_performance_info_distinguishes_gpu_candidate_from_active_runtime(self):
        bridge = self.make_bridge()
        candidate = type("Device", (), {
            "backend":"cuda-candidate", "device":"cpu", "name":"RTX Test",
            "memory_gb":8.0, "supported":False, "reason":"CUDA runtime not active"
        })()
        with (
            patch("psutil.cpu_percent", return_value=11.0),
            patch("psutil.virtual_memory", return_value=type("VM", (), {
                "total":8, "available":4, "percent":50.0
            })()),
            patch("app.tts.qwen_accelerator.detect_accelerators", return_value=(candidate,)),
            patch("app.tts.qwen_accelerator.best_accelerator", return_value=candidate),
        ):
            result = bridge._performance_info({})
        self.assertEqual(result["backend"],"cuda-candidate")
        self.assertFalse(result["backend_active"])
        self.assertIn("runtime not active",result["recommended_backend"])
        self.assertIsNone(result["gpu_percent"])
        self.assertIsNone(result["vram_used_mb"])

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
        uninstall_start = source.index("    def _models_uninstall(")
        uninstall_handler = source[uninstall_start:source.index("    @staticmethod", uninstall_start)]
        install_start = source.index("    def _models_install(")
        install_handler = source[install_start:source.index("    def _models_repair(", install_start)]
        self.assertIn('"chatterbox-model-assets"', uninstall_handler)
        self.assertNotIn('"chatterbox-model-assets"', install_handler)

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

    def test_qwen_model_install_routes_to_selected_model_and_preserves_runtime_separation(self):
        from app.tts.qwen_character_runtime import MODEL_DIRS

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "Models"
            runtimes = base / "Provider Runtime"
            model_root = models / "qwen3-tts"
            runtime_root = runtimes / "qwen3-tts"
            target = model_root / "custom-0.6b"
            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=models),
                patch("app.tts.qwen_character_runtime.MODEL_DIRS", {
                    **MODEL_DIRS, "custom-0.6b": target,
                }),
                patch("app.tts.qwen_character_runtime.RUNTIME_ROOT", runtime_root),
                patch("app.tts.qwen_character_runtime.install_model") as install_model,
            ):
                result = bridge._models_install_component("custom-0.6b", {}, None)

            install_model.assert_called_once_with("custom-0.6b", None, force_repair=False)
            self.assertIn("installed and file-verified", result)
            self.assertEqual(target, model_root / "custom-0.6b")
            self.assertNotEqual(target.parent, runtime_root)

    def test_audiobook_ai_install_runs_runtime_install_and_real_inference_self_test(self):
        bridge = self.make_bridge()
        with (
            patch("app.ai.model_runtime.install_runtime") as install_runtime,
            patch("app.ai.model_runtime.self_test", return_value="CPU inference ready") as self_test,
        ):
            result = bridge._models_install_component("audiobook-ai", {}, None)

        install_runtime.assert_called_once_with(None)
        self_test.assert_called_once_with()
        self.assertIn("CPU inference ready", result)
        self.assertIn("self-tested", result)

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

    def test_models_page_uninstalls_qwen_weights_from_models_root_not_runtime_root(self):
        from app.ui.models_page import UninstallComponentWorker

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "Models"
            provider_runtime = base / "Provider Runtime"
            weights_root = models / "qwen3-tts"
            runtime_root = provider_runtime / "qwen3-tts"
            selected = weights_root / "custom-0.6b"
            sibling = weights_root / "base-0.6b"
            (selected / "weights").mkdir(parents=True)
            (selected / "weights" / "model.safetensors").write_bytes(b"weights")
            sibling.mkdir(parents=True)
            (sibling / "config.json").write_text("{}", encoding="utf-8")
            runtime_root.mkdir(parents=True)
            (runtime_root / "runtime.json").write_text("{}", encoding="utf-8")

            worker = UninstallComponentWorker("qwen-model:custom-0.6b")
            completed = []
            failed = []
            worker.finished_ok.connect(completed.append)
            worker.failed.connect(failed.append)
            with (
                patch("app.ui.models_page.models_root", return_value=models),
                patch("app.ui.models_page.QWEN_MODEL_DIRS", {
                    "custom-0.6b": selected,
                    "base-0.6b": sibling,
                }),
                patch("app.ui.models_page.QWEN_RUNTIME_ROOT", runtime_root),
            ):
                worker.run()

            self.assertEqual(completed, ["qwen-model:custom-0.6b"])
            self.assertEqual(failed, [])
            self.assertFalse(selected.exists())
            self.assertTrue((sibling / "config.json").is_file())
            self.assertTrue((runtime_root / "runtime.json").is_file())

    def test_models_page_uninstalls_chatterbox_runtime_from_provider_runtime_root(self):
        from app.ui.models_page import UninstallComponentWorker

        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "Models"
            provider_runtime = base / "Provider Runtime"
            runtime = provider_runtime / "chatterbox-runtime"
            runtime_file = runtime / "Lib" / "site-packages" / "chatterbox.py"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_text("runtime", encoding="utf-8")
            weights = base / "Model Cache" / "hub" / "models--resemble-ai--chatterbox" / "model.safetensors"
            weights.parent.mkdir(parents=True)
            weights.write_bytes(b"cached model")
            models.mkdir()

            worker = UninstallComponentWorker("chatterbox-runtime")
            completed = []
            failed = []
            worker.finished_ok.connect(completed.append)
            worker.failed.connect(failed.append)
            with (
                patch("app.ui.models_page.models_root", return_value=models),
                patch("app.ui.models_page.runtimes_root", return_value=provider_runtime),
                patch("app.ui.models_page.CHATTERBOX_RUNTIME_DIR", runtime),
                patch("app.ui.models_page.mark_installed"),
            ):
                worker.run()

            self.assertEqual(completed, ["chatterbox-runtime"])
            self.assertEqual(failed, [])
            self.assertFalse(runtime.exists())
            self.assertTrue(weights.is_file())

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

    def test_uninstall_blocks_every_active_application_job_not_only_known_job_names(self):
        bridge = self.make_bridge()
        bridge._jobs["active-import-unknown-label"] = {
            "state": "running", "type": "file-transfer", "title": "Importing book assets"
        }
        with self.assertRaisesRegex(RuntimeError, "application work is active"):
            bridge._models_uninstall_component("kokoro", {}, lambda _message: None)

    def test_uninstall_ignores_only_its_own_lifecycle_job(self):
        bridge = self.make_bridge()
        bridge._jobs["this-uninstall"] = {
            "state": "running", "type": "model-uninstall", "title": "Uninstall Kokoro"
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Models"
            kokoro = root / "kokoro"
            kokoro.mkdir(parents=True)
            (kokoro / "model.onnx").write_bytes(b"model")
            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.model_registry.mark_installed"),
            ):
                result = bridge._models_uninstall_component(
                    "kokoro", {"_operation_job_id": "this-uninstall"}, lambda _message: None
                )
            self.assertIn("Removed the user-installed Kokoro", result)
            self.assertFalse(kokoro.exists())

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
            runtime_root = base / "Provider Runtime" / "qwen3-tts"
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

            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.qwen_character_runtime.RUNTIME_ROOT", runtime_root),
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
            self.assertIn("model weights", message)

    def test_chatterbox_shared_runtime_uninstall_uses_provider_runtime_root_and_preserves_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Models"
            provider_root = base / "Provider Runtime"
            runtime_root = provider_root / "chatterbox-runtime"
            runtime_file = runtime_root / "Lib" / "site-packages" / "chatterbox.py"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_text("runtime", encoding="utf-8")
            cache_root = base / "Model Cache" / "huggingface" / "hub" / "models--resemble-ai--chatterbox"
            cache_file = cache_root / "snapshots" / "abc" / "model.safetensors"
            cache_file.parent.mkdir(parents=True)
            cache_file.write_bytes(b"model weights")
            bridge = self.make_bridge()

            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.ui.premium_v2_host.runtimes_root", return_value=provider_root),
                patch("app.tts.chatterbox_runtime.RUNTIME_DIR", runtime_root),
                patch("app.tts.model_registry.mark_installed"),
            ):
                message = bridge._models_uninstall_component(
                    "chatterbox-runtime", {}, lambda _message: None
                )

            self.assertFalse(runtime_root.exists())
            self.assertTrue(cache_file.is_file())
            self.assertEqual(cache_file.read_bytes(), b"model weights")
            self.assertIn("Saved profiles and books were kept", message)

    def test_qwen_model_uninstall_uses_models_root_not_provider_runtime_root(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            models = base / "Models"
            provider_runtime = base / "Provider Runtime"
            qwen_models_root = models / "qwen3-tts"
            selected = qwen_models_root / "custom-0.6b"
            sibling = qwen_models_root / "base-0.6b"
            selected.mkdir(parents=True)
            sibling.mkdir(parents=True)
            (selected / "model.safetensors").write_bytes(b"selected weights")
            (sibling / "model.safetensors").write_bytes(b"sibling weights")
            qwen_runtime = provider_runtime / "qwen3-tts"
            (qwen_runtime / "runtime").mkdir(parents=True)
            bridge = self.make_bridge()

            with (
                patch("app.core.paths.models_root", return_value=models),
                patch("app.tts.qwen_character_runtime.MODEL_DIRS", {
                    "custom-0.6b": selected,
                    "base-0.6b": sibling,
                }),
                patch("app.tts.qwen_character_runtime.RUNTIME_ROOT", qwen_runtime),
            ):
                message = bridge._models_uninstall_component(
                    "custom-0.6b", {}, lambda _message: None
                )

            self.assertFalse(selected.exists())
            self.assertTrue((sibling / "model.safetensors").is_file())
            self.assertTrue((qwen_runtime / "runtime").is_dir())
            self.assertIn("other model folders", message)

    def test_chatterbox_model_asset_uninstall_removes_only_chatterbox_cache_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Models"
            cache_root = base / "Model Cache" / "hub"
            english = cache_root / "models--resemble-ai--chatterbox"
            multilingual = cache_root / "models--resemble-ai--chatterbox-multilingual"
            other_provider = cache_root / "models--Qwen--Qwen3-TTS"
            for folder in (english, multilingual, other_provider):
                folder.mkdir(parents=True)
                (folder / "weights.safetensors").write_bytes(b"weights")
            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.model_registry._chatterbox_cache_root", return_value=cache_root),
            ):
                message = bridge._models_uninstall_component("chatterbox-model-assets", {}, None)
            self.assertFalse(english.exists())
            self.assertFalse(multilingual.exists())
            self.assertTrue((other_provider / "weights.safetensors").is_file())
            self.assertIn("Other provider caches", message)

    def test_piper_uninstall_removes_only_selected_local_voice_and_sidecar(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Models"
            piper_root = root / "piper"
            selected = piper_root / "en_US-lessac-medium.onnx"
            sibling = piper_root / "en_US-amy-medium.onnx"
            piper_root.mkdir(parents=True)
            selected.write_bytes(b"selected")
            selected.with_suffix(".onnx.json").write_text("{}", encoding="utf-8")
            sibling.write_bytes(b"sibling")
            sibling.with_suffix(".onnx.json").write_text("{}", encoding="utf-8")
            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.providers.piper.PiperProvider.model_paths", return_value=[selected, sibling]),
                patch("app.tts.model_registry.mark_installed") as mark,
            ):
                bridge._models_uninstall_component("piper", {"voice_name": "en_US-lessac-medium"}, None)
            self.assertFalse(selected.exists())
            self.assertFalse(selected.with_suffix(".onnx.json").exists())
            self.assertTrue(sibling.is_file())
            self.assertTrue(sibling.with_suffix(".onnx.json").is_file())
            mark.assert_called_once_with("piper", True)

    def test_kokoro_uninstall_removes_only_user_model_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Models"
            target = root / "kokoro"
            target.mkdir(parents=True)
            (target / "kokoro-v1.0.onnx").write_bytes(b"model")
            preserved = base / "Projects" / "book.json"
            preserved.parent.mkdir()
            preserved.write_text("project", encoding="utf-8")
            bridge = self.make_bridge()
            with (
                patch("app.core.paths.models_root", return_value=root),
                patch("app.tts.model_registry.mark_installed") as mark,
            ):
                bridge._models_uninstall_component("kokoro", {}, None)
            self.assertFalse(target.exists())
            self.assertEqual(preserved.read_text(encoding="utf-8"), "project")
            mark.assert_called_once_with("kokoro", False)

    def test_audiobook_ai_uninstall_keeps_projects_and_other_model_roots(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "Models"
            target = root / "audiobook-ai"
            target.mkdir(parents=True)
            (target / "llama-server.exe").write_bytes(b"runtime")
            project = base / "Projects" / "book.json"
            project.parent.mkdir()
            project.write_text("project", encoding="utf-8")
            other_model = root / "qwen3-tts" / "custom-0.6b" / "model.safetensors"
            other_model.parent.mkdir(parents=True)
            other_model.write_bytes(b"qwen")
            bridge = self.make_bridge()
            with patch("app.core.paths.models_root", return_value=root):
                bridge._models_uninstall_component("audiobook-ai", {}, None)
            self.assertFalse(target.exists())
            self.assertEqual(project.read_text(encoding="utf-8"), "project")
            self.assertTrue(other_model.is_file())

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

    def test_performance_history_import_preserves_source_pc_hardware(self):
        bridge = self.make_bridge()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "pc-b-report.json"
            report.write_text(json.dumps({
                "schema": "ryu.performance-benchmark-history.v1",
                "exported_at": "2026-11-06T10:00:00Z",
                "records": [{
                    "benchmark_id": "source-run-1",
                    "measured_at": "2026-11-06T09:00:00Z",
                    "state": "completed",
                    "result": {
                        "provider": "PiperProvider",
                        "voice": "en_US-test-medium",
                        "seconds": 2.0,
                        "audio_seconds": 4.0,
                        "realtime_factor": 0.5,
                        "success": True,
                        "hardware": {"platform": "Windows PC B", "gpu_name": "RTX test B"},
                    },
                }],
            }), encoding="utf-8")
            with patch.object(bridge, "_performance_history_path", return_value=root / "history.json"):
                result = bridge._performance_history_import({"path": str(report)})
                imported = bridge._performance_history[0]
        self.assertEqual(result["imported"], 1)
        self.assertEqual(imported["source_origin"], "imported")
        self.assertEqual(imported["source_file_name"], report.name)
        self.assertEqual(imported["source_hardware"]["gpu_name"], "RTX test B")
        self.assertEqual(imported["result"]["workload_id"], "piper-default-preview-v1")
        self.assertNotEqual(imported["benchmark_id"], "source-run-1")

    def test_performance_history_compare_requires_matching_workload_and_reports_pc_speed(self):
        bridge = self.make_bridge()
        bridge._performance_history = [
            {
                "benchmark_id": "pc-a", "state": "completed", "source_origin": "local",
                "source_hardware": {"platform": "Windows A", "processor": "CPU A", "gpu_name": "GPU A"},
                "result": {"success": True, "provider": "PiperProvider", "workload_id": "piper-default-preview-v1",
                           "voice": "en_US-test-medium", "seconds": 2.0, "audio_seconds": 4.0,
                           "realtime_factor": 0.5, "backend": "cpu"},
            },
            {
                "benchmark_id": "pc-b", "state": "completed", "source_origin": "imported",
                "source_hardware": {"platform": "Windows B", "processor": "CPU B", "gpu_name": "GPU B"},
                "result": {"success": True, "provider": "PiperProvider", "workload_id": "piper-default-preview-v1",
                           "voice": "en_US-test-medium", "seconds": 1.0, "audio_seconds": 4.0,
                           "realtime_factor": 0.25, "backend": "cuda"},
            },
        ]
        comparison = bridge._performance_history_compare({"benchmark_ids": ["pc-a", "pc-b"]})
        self.assertTrue(comparison["comparable"])
        self.assertEqual(comparison["faster"], "Windows B · CPU B · GPU B")
        self.assertEqual(comparison["speedup_ratio"], 2.0)
        bridge._performance_history[1]["result"]["workload_id"] = "different-workload"
        with self.assertRaisesRegex(ValueError, "not comparable"):
            bridge._performance_history_compare({"benchmark_ids": ["pc-a", "pc-b"]})
