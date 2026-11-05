"""Stage 7 regression coverage for the unified model inventory contract."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.tts.model_registry import (
    component_file_inventory,
    load_inventory_snapshot,
    normalize_inventory_status,
    persist_inventory_snapshot,
    record_component_verification,
)


class ModelRegistryInventoryTests(unittest.TestCase):
    def test_file_presence_never_promotes_component_to_ready(self):
        self.assertEqual(
            normalize_inventory_status(
                "custom-0.6b", True, "model", "Installed and file-verified"
            ),
            "Installed",
        )

    def test_missing_runtime_dependency_is_partially_installed(self):
        self.assertEqual(
            normalize_inventory_status(
                "custom-0.6b", True, "model", "Weights installed · Qwen runtime required"
            ),
            "Partially installed",
        )

    def test_missing_and_partial_installations_are_distinct(self):
        self.assertEqual(
            normalize_inventory_status("kokoro", False, "model", "Not installed"),
            "Missing",
        )
        self.assertEqual(
            normalize_inventory_status(
                "kokoro", False, "model", "Model or voice pack missing",
                has_partial_files=True,
            ),
            "Partially installed",
        )

    def test_disconnected_location_takes_precedence_over_missing_files(self):
        self.assertEqual(
            normalize_inventory_status(
                "qwen-runtime", False, "runtime", "Not installed",
                location_available=False,
            ),
            "Location unavailable",
        )

    def test_ready_requires_matching_successful_verification_fingerprint(self):
        verification = {"success": True, "fingerprint": "same"}
        self.assertEqual(
            normalize_inventory_status(
                "audiobook-ai", True, "model", "Installed · model files present",
                verification=verification, current_fingerprint="same",
            ),
            "Ready",
        )
        self.assertEqual(
            normalize_inventory_status(
                "audiobook-ai", True, "model", "Installed · model files present",
                verification=verification, current_fingerprint="changed",
            ),
            "Installed",
        )

    def test_inventory_file_list_reports_real_paths_sizes_and_excludes_partial_downloads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Models"
            piper = root / "piper"
            piper.mkdir(parents=True)
            model = piper / "en_US-amy-medium.onnx"
            config = piper / "en_US-amy-medium.onnx.json"
            partial = piper / "unfinished.onnx.part"
            model.write_bytes(b"model-data")
            config.write_text('{"audio":{"sample_rate":22050}}', encoding="utf-8")
            partial.write_bytes(b"partial")

            with (
                patch("app.tts.model_registry.models_root", return_value=root),
                patch("app.tts.providers.piper.PiperProvider._bundled_root", return_value=None),
            ):
                first = component_file_inventory("piper", offset=0, limit=1)
                second = component_file_inventory("piper", offset=1, limit=1)

            self.assertEqual(first["total_files"], 2)
            self.assertTrue(first["has_more"])
            self.assertEqual(len(first["files"]), 1)
            self.assertEqual(len(second["files"]), 1)
            paths = {item["path"] for item in first["files"] + second["files"]}
            self.assertEqual(paths, {str(model.resolve()), str(config.resolve())})
            self.assertEqual(
                sum(item["size_bytes"] for item in first["files"] + second["files"]),
                model.stat().st_size + config.stat().st_size,
            )

    def test_inventory_snapshot_persists_metadata_and_verification_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary) / "Settings" / "model_inventory.json"
            row = {
                "model_id": "kokoro",
                "name": "Kokoro",
                "provider": "kokoro",
                "component_type": "model",
                "model_path": "C:/Models/kokoro",
                "runtime_path": "C:/Python/site-packages/kokoro_onnx",
                "storage_bytes": 1234,
                "status": "Installed",
                "status_detail": "Installed locally",
            }
            with patch("app.tts.model_registry._inventory_snapshot_path", return_value=snapshot):
                persist_inventory_snapshot([row])
                record_component_verification("kokoro", True, "runtime and assets checked", "fingerprint")
                value = load_inventory_snapshot()

            self.assertEqual(value["schema_version"], 1)
            self.assertEqual(value["components"]["kokoro"]["model_path"], row["model_path"])
            self.assertEqual(value["components"]["kokoro"]["storage_bytes"], 1234)
            self.assertEqual(value["components"]["kokoro"]["verification"]["fingerprint"], "fingerprint")
            self.assertTrue(value["components"]["kokoro"]["last_verified"])


if __name__ == "__main__":
    unittest.main()
