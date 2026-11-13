"""Stage C2 Qwen Models Center install/repair lifecycle regressions."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.tts import qwen_character_runtime as qwen_runtime


class QwenRuntimeRepairTransactionTests(unittest.TestCase):
    def _existing_runtime(self, root: Path):
        runtime_root = root / "Provider Runtime" / "qwen3-tts"
        python_root = runtime_root / "python312"
        venv_root = runtime_root / "runtime"
        marker = runtime_root / "runtime.json"
        (python_root / "python.exe").parent.mkdir(parents=True, exist_ok=True)
        (python_root / "python.exe").write_bytes(b"previous-python")
        (venv_root / "Scripts").mkdir(parents=True)
        (venv_root / "Scripts" / "python.exe").write_bytes(b"previous-venv-python")
        previous_marker = {
            "ready": True,
            "bootstrap_version": qwen_runtime.BOOTSTRAP_VERSION,
            "python": qwen_runtime.PYTHON_VERSION,
            "qwen_tts": qwen_runtime.QWEN_TTS_VERSION,
            "torch": "previous-torch",
            "torchaudio": "previous-torchaudio",
            "tokenizer": qwen_runtime.TOKENIZER_ID,
            "accelerator": "cpu",
        }
        marker.write_text(json.dumps(previous_marker), encoding="utf-8")
        return runtime_root, python_root, venv_root, marker

    def _runtime_patches(self, runtime_root, python_root, venv_root, marker):
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(patch.object(qwen_runtime, "RUNTIME_ROOT", runtime_root))
        stack.enter_context(patch.object(qwen_runtime, "PYTHON_ROOT", python_root))
        stack.enter_context(patch.object(qwen_runtime, "VENV_ROOT", venv_root))
        stack.enter_context(patch.object(qwen_runtime, "MARKER", marker))
        stack.enter_context(patch.object(qwen_runtime, "_active_qwen_worker_pids", return_value=[]))
        return stack

    def test_successful_repair_replaces_runtime_only_after_new_self_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root, python_root, venv_root, marker = self._existing_runtime(root)

            def install_python(_progress=None):
                python_root.mkdir(parents=True, exist_ok=True)
                path = python_root / "python.exe"
                path.write_bytes(b"replacement-python")
                return path

            def create_venv(_progress=None):
                executable = venv_root / "Scripts" / "python.exe"
                executable.parent.mkdir(parents=True, exist_ok=True)
                executable.write_bytes(b"replacement-venv-python")
                return executable

            with (
                self._runtime_patches(runtime_root, python_root, venv_root, marker),
                patch.object(qwen_runtime, "_runtime_version_is_current", side_effect=[True, True]),
                patch.object(qwen_runtime, "_install_portable_python", side_effect=install_python),
                patch.object(qwen_runtime, "_create_or_repair_venv", side_effect=create_venv),
                patch.object(qwen_runtime, "_install_runtime_packages", return_value=("cpu", "2.9.1", "2.9.1")),
                patch.object(qwen_runtime, "verify_runtime", return_value="replacement runtime verified"),
            ):
                result = qwen_runtime.repair_runtime()

            self.assertEqual(result, "replacement runtime verified")
            self.assertEqual((python_root / "python.exe").read_bytes(), b"replacement-python")
            self.assertEqual(
                (venv_root / "Scripts" / "python.exe").read_bytes(),
                b"replacement-venv-python",
            )
            installed_marker = json.loads(marker.read_text(encoding="utf-8"))
            self.assertEqual(installed_marker["torch"], "2.9.1")
            self.assertEqual(installed_marker["accelerator"], "cpu")
            self.assertFalse((runtime_root / "runtime-repair-backup").exists())

    def test_failed_repair_restores_previous_python_venv_and_marker(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root, python_root, venv_root, marker = self._existing_runtime(root)
            previous_marker = marker.read_bytes()

            def install_python(_progress=None):
                python_root.mkdir(parents=True, exist_ok=True)
                (python_root / "python.exe").write_bytes(b"partial-replacement-python")
                return python_root / "python.exe"

            def create_venv(_progress=None):
                executable = venv_root / "Scripts" / "python.exe"
                executable.parent.mkdir(parents=True, exist_ok=True)
                executable.write_bytes(b"partial-replacement-venv")
                return executable

            with (
                self._runtime_patches(runtime_root, python_root, venv_root, marker),
                patch.object(qwen_runtime, "_runtime_version_is_current", return_value=True),
                patch.object(qwen_runtime, "_install_portable_python", side_effect=install_python),
                patch.object(qwen_runtime, "_create_or_repair_venv", side_effect=create_venv),
                patch.object(
                    qwen_runtime,
                    "_install_runtime_packages",
                    side_effect=RuntimeError("injected PyTorch install failure"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "injected PyTorch install failure"):
                    qwen_runtime.repair_runtime()

            self.assertEqual((python_root / "python.exe").read_bytes(), b"previous-python")
            self.assertEqual(
                (venv_root / "Scripts" / "python.exe").read_bytes(),
                b"previous-venv-python",
            )
            self.assertEqual(marker.read_bytes(), previous_marker)
            self.assertFalse((runtime_root / "runtime-repair-backup").exists())

    def test_repair_refuses_to_mutate_runtime_while_qwen_worker_is_active(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root, python_root, venv_root, marker = self._existing_runtime(root)
            previous_marker = marker.read_bytes()

            with (
                patch.object(qwen_runtime, "RUNTIME_ROOT", runtime_root),
                patch.object(qwen_runtime, "PYTHON_ROOT", python_root),
                patch.object(qwen_runtime, "VENV_ROOT", venv_root),
                patch.object(qwen_runtime, "MARKER", marker),
                patch.object(qwen_runtime, "_runtime_version_is_current", return_value=True),
                patch.object(qwen_runtime, "_active_qwen_worker_pids", return_value=[12345]),
                patch.object(qwen_runtime, "_install_portable_python") as install_python,
            ):
                with self.assertRaisesRegex(RuntimeError, "active"):
                    qwen_runtime.repair_runtime()

            install_python.assert_not_called()
            self.assertEqual((python_root / "python.exe").read_bytes(), b"previous-python")
            self.assertEqual((venv_root / "Scripts" / "python.exe").read_bytes(), b"previous-venv-python")
            self.assertEqual(marker.read_bytes(), previous_marker)

    def test_interrupted_repair_restores_original_files_before_next_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_root, python_root, venv_root, marker = self._existing_runtime(root)
            backup = runtime_root / "runtime-repair-backup"
            backup.mkdir()
            original = {
                "schema_version": 1,
                "targets": {"python312": True, "runtime": True, "runtime.json": True},
            }
            (backup / "manifest.json").write_text(json.dumps(original), encoding="utf-8")
            python_root.replace(backup / "python312")
            venv_root.replace(backup / "runtime")
            marker.replace(backup / "runtime.json")

            with (
                patch.object(qwen_runtime, "RUNTIME_ROOT", runtime_root),
                patch.object(qwen_runtime, "PYTHON_ROOT", python_root),
                patch.object(qwen_runtime, "VENV_ROOT", venv_root),
                patch.object(qwen_runtime, "MARKER", marker),
                patch.object(qwen_runtime, "_runtime_version_is_current", side_effect=[False, False, True]),
                patch.object(qwen_runtime, "_active_qwen_worker_pids", return_value=[]),
            ):
                qwen_runtime.install_runtime()

            self.assertEqual((python_root / "python.exe").read_bytes(), b"previous-python")
            self.assertEqual((venv_root / "Scripts" / "python.exe").read_bytes(), b"previous-venv-python")
            self.assertTrue(marker.is_file())
            self.assertFalse(backup.exists())


class QwenModelsCenterInstallPlanTests(unittest.TestCase):
    def _run_worker(self, selection: str, preference: str, expected: list[str]) -> None:
        from app.ui.models_page import QwenCharacterInstallWorker

        installed = []
        succeeded = []
        failed = []
        worker = QwenCharacterInstallWorker(selection)
        worker.finished_ok.connect(succeeded.append)
        worker.failed.connect(failed.append)
        with (
            patch("app.ui.models_page.install_qwen_runtime") as install_runtime,
            patch("app.ui.models_page.get_qwen_model_preference", return_value=preference),
            patch("app.ui.models_page.best_custom_kind", return_value="custom-0.6b"),
            patch("app.ui.models_page.best_clone_kind", return_value="base-0.6b"),
            patch("app.ui.models_page.best_voice_design_kind", return_value="design-1.7b"),
            patch(
                "app.ui.models_page.install_qwen_model",
                side_effect=lambda kind, _progress: installed.append(kind),
            ),
        ):
            worker.run()

        self.assertEqual(failed, [])
        self.assertEqual(len(succeeded), 1)
        self.assertEqual(installed, expected)
        install_runtime.assert_called_once()

    def test_install_selection_respects_global_model_size_for_all_three_modes(self):
        cases = (
            ("CustomVoice", "0.6b", ["custom-0.6b"]),
            ("VoiceDesign", "0.6b", ["design-1.7b", "base-0.6b"]),
            ("Voice Clone", "0.6b", ["base-0.6b"]),
            ("CustomVoice", "1.7b", ["custom-1.7b"]),
            ("VoiceDesign", "1.7b", ["design-1.7b", "base-1.7b"]),
            ("Voice Clone", "1.7b", ["base-1.7b"]),
        )
        for selection, preference, expected in cases:
            with self.subTest(selection=selection, preference=preference):
                self._run_worker(selection, preference, expected)

    def test_full_install_and_automatic_selection_install_exact_required_models(self):
        self._run_worker(
            "Full Qwen Voice Studio", "0.6b",
            ["custom-0.6b", "design-1.7b", "base-0.6b"],
        )
        self._run_worker(
            "Full Qwen Voice Studio", "1.7b",
            ["custom-1.7b", "design-1.7b", "base-1.7b"],
        )
        self._run_worker(
            "Full Qwen Voice Studio", "auto",
            ["custom-0.6b", "design-1.7b", "base-0.6b"],
        )


class QwenModelsCenterUninstallPreservationTests(unittest.TestCase):
    def _run_uninstall(self, component_id: str, models_root: Path, paths: dict):
        from app.ui import models_page

        succeeded = []
        failed = []
        worker = models_page.UninstallComponentWorker(component_id)
        worker.finished_ok.connect(succeeded.append)
        worker.failed.connect(failed.append)
        with (
            patch.object(models_page, "models_root", return_value=models_root),
            patch.object(models_page, "QWEN_MODEL_DIRS", paths["model_dirs"]),
            patch.object(models_page, "QWEN_RUNTIME_ROOT", paths["runtime_root"]),
            patch.object(models_page, "QWEN_VENV_ROOT", paths["venv_root"]),
            patch.object(models_page, "QWEN_PYTHON_ROOT", paths["python_root"]),
            patch.object(models_page, "QWEN_MARKER", paths["marker"]),
            patch.object(models_page, "QWEN_INSTALLER_PATH", paths["installer"]),
            patch.object(models_page, "QWEN_INSTALLER_LOG", paths["installer_log"]),
        ):
            worker.run()
        self.assertEqual(failed, [])
        self.assertEqual(succeeded, [component_id])

    def test_removing_one_qwen_model_keeps_other_models_and_saved_profiles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "Models"
            model_root = models / "qwen3-tts"
            model_dirs = {
                kind: model_root / kind
                for kind in (
                    "custom-0.6b", "custom-1.7b", "design-1.7b",
                    "base-0.6b", "base-1.7b",
                )
            }
            for folder in model_dirs.values():
                folder.mkdir(parents=True)
                (folder / "config.json").write_text("{}", encoding="utf-8")
            voices = root / "Voices"
            voices.mkdir()
            catalogue = voices / "voices.json"
            catalogue.write_text('[{"name":"Saved Qwen Voice"}]', encoding="utf-8")

            runtime_root = root / "Provider Runtime" / "qwen3-tts"
            anchor_dir = runtime_root / "voice_anchors"
            anchor_dir.mkdir(parents=True)
            anchor = anchor_dir / "qwen-design-saved.wav"
            anchor.write_bytes(b"saved voice anchor")
            paths = {
                "model_dirs": model_dirs,
                "runtime_root": runtime_root,
                "venv_root": runtime_root / "runtime",
                "python_root": runtime_root / "python312",
                "marker": runtime_root / "runtime.json",
                "installer": runtime_root / "python-installer.exe",
                "installer_log": runtime_root / "python-install.log",
            }

            self._run_uninstall("qwen-model:custom-0.6b", models, paths)

            self.assertFalse(model_dirs["custom-0.6b"].exists())
            self.assertTrue(model_dirs["custom-1.7b"].is_dir())
            self.assertTrue(model_dirs["design-1.7b"].is_dir())
            self.assertEqual(catalogue.read_text(encoding="utf-8"), '[{"name":"Saved Qwen Voice"}]')
            self.assertEqual(anchor.read_bytes(), b"saved voice anchor")

    def test_removing_qwen_runtime_keeps_models_saved_profiles_and_voice_anchors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            models = root / "Models"
            model_root = models / "qwen3-tts"
            model_dirs = {
                kind: model_root / kind
                for kind in (
                    "custom-0.6b", "custom-1.7b", "design-1.7b",
                    "base-0.6b", "base-1.7b",
                )
            }
            for folder in model_dirs.values():
                folder.mkdir(parents=True)
                (folder / "config.json").write_text("{}", encoding="utf-8")
            voices = root / "Voices"
            voices.mkdir()
            catalogue = voices / "voices.json"
            catalogue.write_text('[{"name":"Saved Qwen Voice"}]', encoding="utf-8")

            runtime_root = root / "Provider Runtime" / "qwen3-tts"
            venv_root = runtime_root / "runtime"
            python_root = runtime_root / "python312"
            venv_root.mkdir(parents=True)
            python_root.mkdir(parents=True)
            (venv_root / "runtime-file").write_bytes(b"venv")
            (python_root / "python.exe").write_bytes(b"python")
            marker = runtime_root / "runtime.json"
            marker.write_text('{"ready":true}', encoding="utf-8")
            installer = runtime_root / "python-installer.exe"
            installer.write_bytes(b"installer")
            installer_log = runtime_root / "python-install.log"
            installer_log.write_text("install log", encoding="utf-8")
            anchor_dir = runtime_root / "voice_anchors"
            anchor_dir.mkdir()
            anchor = anchor_dir / "qwen-design-saved.wav"
            anchor.write_bytes(b"saved voice anchor")
            paths = {
                "model_dirs": model_dirs,
                "runtime_root": runtime_root,
                "venv_root": venv_root,
                "python_root": python_root,
                "marker": marker,
                "installer": installer,
                "installer_log": installer_log,
            }

            self._run_uninstall("qwen-runtime", models, paths)

            self.assertFalse(venv_root.exists())
            self.assertFalse(python_root.exists())
            self.assertFalse(marker.exists())
            self.assertFalse(installer.exists())
            self.assertFalse(installer_log.exists())
            self.assertTrue(anchor.is_file())
            self.assertTrue(all(folder.is_dir() for folder in model_dirs.values()))
            self.assertTrue(catalogue.is_file())


if __name__ == "__main__":
    unittest.main()
