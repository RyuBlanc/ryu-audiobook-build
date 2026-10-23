"""Stage 6 installer branding and user-data preservation contract tests."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "RyuAudiobook.iss"


class InstallerBrandingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = INSTALLER.read_text(encoding="utf-8")

    def test_setup_wizard_uses_premium_v2_dark_gold_palette(self):
        # Native Inno Setup dark styling keeps standard controls (checkboxes,
        # summary memos, dialogs and buttons) readable; test the new UI contract
        # rather than requiring the old label-only color overrides.
        self.assertIn("WizardStyle=modern dark hidebevels includetitlebar", self.script)
        self.assertIn("WizardBackColor=#05060A", self.script)
        self.assertIn("WizardImageFile=..\\assets\\installer_brand_panel.png", self.script)
        self.assertIn("WizardImageBackColor=#05060A", self.script)
        self.assertIn("WizardSmallImageFile=..\\assets\\ryu_audiobook_logo.png", self.script)
        self.assertIn("WizardSmallImageBackColor=#05060A", self.script)
        self.assertIn("DefaultDialogFontName=Segoe UI", self.script)
        self.assertIn("SetupIconFile=..\\assets\\ryu_audiobook_logo.ico", self.script)
        self.assertNotIn("WizardForm.Color :=", self.script)
        self.assertNotIn("WizardForm.InnerPage.Color :=", self.script)

    def test_logo_render_keeps_native_resolution_and_original_transparency(self):
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("source_size = renderer.defaultSize()", build_script)
        self.assertIn("roundedBrandTile", build_script)
        self.assertIn("ImageChops.multiply(alpha, clip_mask)", build_script)
        self.assertIn("mask_scale = 4", build_script)
        self.assertIn("Image.Resampling.LANCZOS", build_script)
        self.assertIn("remove_neutral_white_matte", build_script)
        self.assertIn("neutral_near_white", build_script)
        self.assertIn("final_alpha = original_alpha", build_script)
        self.assertIn("required_ico_sizes", build_script)
        self.assertIn("icon_file.ico.sizes()", build_script)
        self.assertIn("icon_file.ico.getimage(icon_size)", build_script)
        self.assertIn("missing_sizes = required_ico_sizes - icon_sizes", build_script)
        self.assertIn("alpha_min > 16", build_script)
        self.assertIn("alpha_max < 128", build_script)
        self.assertIn("visible_pixels < pixel_count * 0.20", build_script)
        self.assertIn("alpha_histogram = icon_alpha.histogram()", build_script)
        self.assertIn("icon_alpha.getextrema()", build_script)
        self.assertIn("Application logo canvas corners must remain fully transparent.", build_script)
        self.assertNotIn("QImage(1024, 1024", build_script)

        # The main window and legacy Import control must prefer the PNG asset,
        # retaining SVG only as a source-checkout fallback.
        for relative_path in ("app/main.py", "app/ui/workflow.py"):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertLess(
                source.index("ryu_audiobook_logo.png"),
                source.index("ryu_audiobook_logo.svg"),
            )

    def test_setup_keeps_install_paths_and_selectable_shortcuts(self):
        self.assertIn(r"DefaultDirName={autopf}\Ryu's Audiobook", self.script)
        self.assertIn('#define MyAppExeName "Ryu\'s Audiobook.exe"', self.script)
        self.assertIn("OutputBaseFilename=Ryu's Audiobook Setup Payload", self.script)
        self.assertIn(r'Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon', self.script)
        self.assertIn(r'Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon', self.script)
        self.assertIn('Name: "startmenuicon"; Description: "Create a Start menu shortcut"', self.script)
        self.assertNotIn("[Run]", self.script)

    def test_delivered_installer_uses_reference_style_html_and_real_inno_engine(self):
        html = (ROOT / "installer" / "launcher.html").read_text(encoding="utf-8")
        launcher = (ROOT / "installer" / "launcher.py").read_text(encoding="utf-8")
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "build-windows.yml").read_text(encoding="utf-8")

        self.assertIn("--red:#ed174f", html)
        self.assertIn("--gold:#f1bf64", html)
        self.assertIn("grid-template-columns:285px 1fr", html)
        self.assertIn('src="../assets/ryu_audiobook_logo.png"', html)
        self.assertIn("new QWebChannel", html)
        self.assertIn("bridge.startInstall(JSON.stringify(options))", html)
        self.assertNotIn("setInterval(", html)

        self.assertIn("QWebEngineView", launcher)
        self.assertIn("payload/Ryu's Audiobook Setup Payload.exe", launcher)
        self.assertIn('"/VERYSILENT"', launcher)
        self.assertIn("subprocess.Popen(", launcher)
        self.assertIn("required_install_bytes", launcher)
        self.assertIn("app_exe.is_file()", launcher)
        self.assertIn("logo_png.is_file()", launcher)

        self.assertIn("def write_installer_manifest()", build_script)
        self.assertIn("INSTALLER_MANIFEST_FILE.write_text", build_script)
        self.assertIn("required_install_bytes", build_script)
        self.assertIn("--onefile", workflow)
        self.assertIn("installer\\\\launcher.html;installer", workflow)
        self.assertIn("installer\\\\launcher.py", workflow)
        self.assertIn("Ryu's Audiobook Setup Payload.exe", workflow)

    def test_uninstaller_does_not_delete_user_data(self):
        self.assertIn("User books, voices, models, and settings live under %USERPROFILE%", self.script)
        self.assertIn("[UninstallDelete]", self.script)
        self.assertIn("Deliberately do not remove user data outside {app}.", self.script)
        self.assertNotIn("Type: filesandordirs; Name: \"{userprofile}", self.script)


if __name__ == "__main__":
    unittest.main()
