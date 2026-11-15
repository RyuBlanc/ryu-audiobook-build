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
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        path_guard = (ROOT / "app" / "ui" / "voice_library_acceptance.py").read_text(encoding="utf-8")
        self.assertIn("resolve_voice_library_acceptance_path(payload, key, must_exist=must_exist)", host)
        self.assertIn("RYU_VOICE_LIBRARY_ACCEPTANCE_ROOT", path_guard)
        self.assertIn("candidate = candidate.absolute()", path_guard)
        self.assertIn("relative_candidate = candidate.relative_to(root)", path_guard)
        self.assertIn("_is_link_or_junction", path_guard)
        self.assertIn("must be supplied", path_guard)
        self.assertIn('payload, "acceptance_output_path"', host)
        self.assertIn('payload, "acceptance_bundle_path", must_exist=True', host)
        self.assertIn('payload, "bundle_path", must_exist=True', host)
        commit = host[host.index("def _voice_bundle_import"):host.index("def _find_profile")]
        self.assertIn("acceptance_bundle = self._voice_library_acceptance_path(", commit)
        self.assertIn("acceptance_bundle if acceptance_bundle is not None", commit)
        self.assertIn("QFileDialog.getSaveFileName(", host)
        self.assertIn("QFileDialog.getOpenFileName(", host)


if __name__ == "__main__":
    unittest.main()
