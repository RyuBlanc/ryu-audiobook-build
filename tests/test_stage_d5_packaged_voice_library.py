"""Stage D5 packaged Voice Library native-bridge acceptance contracts."""

from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class StageD5PackagedVoiceLibraryTests(unittest.TestCase):
    def test_frozen_app_acceptance_seeds_and_restores_three_profile_types(self):
        source = (ROOT / "tests" / "packaged_sound_ui_acceptance.py").read_text(encoding="utf-8")
        for token in (
            "original_voice_catalogue_bytes",
            "voice_catalogue_seeded",
            'qwen_mode="custom"',
            'qwen_mode="design"',
            'qwen_mode="clone"',
            "voice_library_profiles_payload",
            "voice_library_source_root",
            'environment["RYU_VOICE_LIBRARY_ACCEPTANCE_ROOT"]',
            'voices_root / "Qwen Profile Assets" / profile_id',
            'voices_root / "Qwen Profile Revisions" / profile_id',
        ):
            self.assertIn(token, source)

    def test_frozen_browser_script_runs_export_preflight_import_and_fresh_process_reload(self):
        source = (ROOT / "tests" / "stage2_packaged_sound_ui_acceptance.js").read_text(encoding="utf-8")
        for token in (
            'invoke("voice.list"',
            'invoke("voice.library.inspect"',
            'invoke("voice.bundle.export"',
            'invoke("voice.delete"',
            'invoke("voice.bundle.choose_import"',
            'invoke("voice.bundle.import"',
            "stage_d5_packaged_voice_library_export_preflight_import_asset_roundtrip",
            "stage_d5_packaged_voice_library_fresh_process_reload",
            "asset_sha256",
        ):
            self.assertIn(token, source)

    def test_native_acceptance_file_path_override_is_opt_in_and_confined(self):
        source = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("RYU_VOICE_LIBRARY_ACCEPTANCE_ROOT", source)
        self.assertIn("resolved.relative_to(root)", source)
        self.assertIn("candidate.is_symlink()", source)
        self.assertIn('payload, "acceptance_output_path"', source)
        self.assertIn('payload, "acceptance_bundle_path", must_exist=True', source)
        self.assertIn("QFileDialog.getSaveFileName(", source)
        self.assertIn("QFileDialog.getOpenFileName(", source)


if __name__ == "__main__":
    unittest.main()
