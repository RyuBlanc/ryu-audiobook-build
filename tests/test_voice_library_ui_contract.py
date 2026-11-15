"""D4 Premium V2 Voice Library frontend/backend wiring contract tests."""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class VoiceLibraryUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        cls.adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        cls.host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")

    def test_saved_library_is_inside_step_one_and_keeps_existing_source_catalogue(self):
        marker = '<div class="panel active" data-panel="1">'
        start = self.html.index(marker)
        panel_end = self.html.index('<div class="panel" data-panel="2">', start)
        panel = self.html[start:panel_end]
        self.assertIn('id="savedVoiceLibrary"', panel)
        self.assertIn('id="voiceLibraryRows"', panel)
        self.assertIn('id="voiceLibrarySearch"', panel)
        self.assertIn('id="voiceLibraryModelFilter"', panel)
        self.assertIn('data-source="customvoice"', panel)
        self.assertIn('data-source="voicedesign"', panel)
        self.assertIn('data-source="qwenclone"', panel)
        self.assertIn("Built-in and system", panel)

    def test_library_exposes_all_five_profile_categories_and_independent_model_filter(self):
        html = self.html
        for category in ("All", "Designed", "Cloned", "Preset", "Cloud"):
            self.assertIn('data-library-kind="' + category + '"', html)
        self.assertIn('id="voiceLibraryModelFilter"', html)
        self.assertIn('id="voiceLibraryExportSelected"', html)
        self.assertIn('id="voiceLibraryImport"', html)
        self.assertIn("All models", html)

    def test_library_uses_normal_page_scroll_and_does_not_create_a_separate_scroll_pane(self):
        start = self.html.index('id="savedVoiceLibrary"')
        end = self.html.index('</section>', start)
        section = self.html[start:end]
        self.assertNotRegex(section, r'overflow\\s*:\\s*(?:auto|scroll)')
        css_start = self.html.rfind("/* Stage D4 — saved Voice Library.")
        self.assertGreaterEqual(css_start, 0)
        css_end = self.html.find("</style>", css_start)
        css = self.html[css_start:css_end]
        self.assertNotRegex(css, r"overflow-y\\s*:\\s*(?:auto|scroll)")
        self.assertNotIn("::-webkit-scrollbar", css)

    def test_adapter_filters_saved_profiles_and_routes_loading_through_canonical_profile_loader(self):
        self.assertIn("function voiceLibrarySavedProfiles()", self.adapter)
        self.assertIn("profile.saved === true", self.adapter)
        self.assertIn("voiceLibraryKindFilter", self.adapter)
        self.assertIn("voiceLibraryModelFilterValue", self.adapter)
        self.assertIn("renderSavedVoiceLibrary()", self.adapter)
        self.assertIn("applySavedVoiceProfile(profile)", self.adapter)
        self.assertIn("invalidateVoicePreview()", self.adapter)
        self.assertIn("call('voice.library.inspect'", self.adapter)
        self.assertIn("call('voice.bundle.choose_import'", self.adapter)
        self.assertIn("call('voice.bundle.import'", self.adapter)
        self.assertIn("call('voice.bundle.export'", self.adapter)
        self.assertIn("call('voice.delete'", self.adapter)

    def test_native_bridge_advertises_every_new_library_command(self):
        commands = (
            "voice.library.inspect",
            "voice.bundle.export",
            "voice.bundle.choose_import",
            "voice.bundle.import",
        )
        for command in commands:
            self.assertIn('"' + command + '": self._', self.host)
            self.assertIn('"' + command + '": True', self.host)
        self.assertIn("def _voice_library_inspect(", self.host)
        self.assertIn("def _voice_bundle_export(", self.host)
        self.assertIn("def _voice_bundle_choose_import(", self.host)
        self.assertIn("def _voice_bundle_import(", self.host)

    def test_library_inspection_and_export_are_read_only_until_the_user_commits_an_action(self):
        inspect = self.host[self.host.index("def _voice_library_inspect"):self.host.index("def _voice_bundle_export")]
        self.assertIn("load_saved_profiles()", inspect)
        self.assertIn("profile_library_record(profile, inspect_assets=True)", inspect)
        self.assertNotIn("save_profiles(", inspect)
        self.assertNotIn("save_state(", inspect)
        exporter = self.host[self.host.index("def _voice_bundle_export"):self.host.index("def _voice_bundle_choose_import")]
        self.assertIn('profile.provider != "qwen-character"', exporter)
        self.assertIn("export_qwen_profiles_bundle(", exporter)
        self.assertIn("QFileDialog.getSaveFileName(", exporter)

    def test_import_preflight_is_separate_from_transactional_commit(self):
        chooser = self.host[self.host.index("def _voice_bundle_choose_import"):self.host.index("def _voice_bundle_import")]
        commit = self.host[self.host.index("def _voice_bundle_import"):self.host.index("def _find_profile")]
        self.assertIn("plan_qwen_profiles_import(", chooser)
        self.assertNotIn("import_qwen_profiles_bundle(", chooser)
        self.assertIn("import_qwen_profiles_bundle(", commit)
        self.assertIn("allow_missing_voicedesign_anchor", commit)
        self.assertIn("resolutions=resolutions", commit)


if __name__ == "__main__":
    unittest.main()
