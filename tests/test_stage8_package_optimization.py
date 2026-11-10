from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from package_size_report import build_report
from scripts.qt_payload_pruner import prune_optional_qt_assets


ROOT = Path(__file__).resolve().parents[1]


class Stage8PackageOptimizationTests(unittest.TestCase):
    def test_release_pruner_removes_only_optional_devtools_debug_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            resources = root / "_internal" / "PySide6" / "resources"
            resources.mkdir(parents=True)
            debug = resources / "qtwebengine_devtools_resources.debug.pak"
            devtools = resources / "qtwebengine_devtools_resources.pak"
            webengine = resources / "qtwebengine_resources.pak"
            debug.write_bytes(b"optional debug resources")
            devtools.write_bytes(b"regular devtools resources")
            webengine.write_bytes(b"required web runtime resources")
            offline_model = root / "_internal" / "bundled_models" / "piper" / "voice.onnx"
            offline_model.parent.mkdir(parents=True)
            offline_model.write_bytes(b"required offline voice model")
            starter_audio = root / "_internal" / "assets" / "starter_audio" / "track.mp3"
            starter_audio.parent.mkdir(parents=True)
            starter_audio.write_bytes(b"required starter audio")

            removed = prune_optional_qt_assets(root)

            self.assertEqual(removed, ["_internal/PySide6/resources/qtwebengine_devtools_resources.debug.pak"])
            self.assertFalse(debug.exists())
            self.assertTrue(devtools.exists())
            self.assertTrue(webengine.exists())
            self.assertTrue(offline_model.exists())
            self.assertTrue(starter_audio.exists())

    def test_build_excludes_only_unused_qt_modules_and_runs_release_pruner(self):
        source = (ROOT / "build.py").read_text(encoding="utf-8")
        for module in (
            "PySide6.QtQuick",
            "PySide6.QtQml",
            "PySide6.QtQuick3D",
            "PySide6.QtQuick3DPhysics",
            "PySide6.QtPdf",
            "PySide6.QtShaderTools",
        ):
            self.assertIn(f"--exclude-module={module}", source)
        self.assertIn("prune_optional_qt_assets(ROOT /", source)

    def test_installer_uses_ultra_lzma2_compression(self):
        source = (ROOT / "installer" / "RyuAudiobook.iss").read_text(encoding="utf-8")
        self.assertIn("Compression=lzma2/ultra64", source)
        self.assertIn("SolidCompression=yes", source)

    def test_package_report_uses_validated_application_version_environment(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "dist" / "Ryu's Audiobook").mkdir(parents=True)
            with patch.dict("os.environ", {"RYU_APP_VERSION": "1.2.0"}, clear=False):
                report = build_report(root)
            self.assertEqual(report["build"]["app_version"], "1.2.0")


if __name__ == "__main__":
    unittest.main()
