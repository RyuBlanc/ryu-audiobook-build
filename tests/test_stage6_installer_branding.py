"""Stage 6 installer branding and user-data preservation contract tests."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "installer" / "RyuAudiobook.iss"


class InstallerBrandingContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = INSTALLER.read_text(encoding="utf-8")

    def test_setup_wizard_uses_native_dark_mode_and_brand_assets(self):
        self.assertIn("Compression=lzma2/ultra", self.script)
        self.assertIn("SolidCompression=yes", self.script)
        self.assertIn("WizardStyle=modern dark hidebevels includetitlebar", self.script)
        self.assertIn("WizardBackColor=#05060A", self.script)
        self.assertIn("WizardImageFile=..\\assets\\installer_brand_panel.bmp", self.script)
        self.assertIn("WizardSmallImageFile=..\\assets\\ryu_audiobook_logo.bmp", self.script)
        self.assertIn("WizardSmallImageBackColor=#05060A", self.script)
        self.assertIn("DefaultDialogFontName=Segoe UI", self.script)
        self.assertIn("SetupIconFile=..\\assets\\ryu_audiobook_logo.ico", self.script)
        # Native dark styling fixes ordinary labels and controls that the old
        # label-only InitializeWizard color loop left black on dark surfaces.
        self.assertNotIn("WizardForm.Color :=", self.script)
        self.assertNotIn("WizardForm.InnerPage.Color :=", self.script)

    def test_logo_pipeline_builds_native_resolution_transparent_installer_art(self):
        build_script = (ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("source_size = renderer.defaultSize()", build_script)
        self.assertIn('INSTALLER_BRAND_PANEL_PNG = ASSETS / "installer_brand_panel.png"', build_script)
        self.assertIn('LOGO_BMP = ASSETS / "ryu_audiobook_logo.bmp"', build_script)
        self.assertIn('INSTALLER_BRAND_PANEL_BMP = ASSETS / "installer_brand_panel.bmp"', build_script)
        self.assertIn('ImageChops.multiply(rgba.getchannel("A"), clip_mask)', build_script)
        self.assertIn("panel.alpha_composite(", build_script)
        self.assertIn('panel.save(INSTALLER_BRAND_PANEL_PNG, format="PNG", optimize=True)', build_script)
        self.assertIn("Installer brand panel must keep a transparent full-size canvas.", build_script)
        self.assertIn("Installer brand panel BMP must match WizardBackColor.", build_script)

    def test_installer_keeps_the_complete_application_payload(self):
        source_lines = [line for line in self.script.splitlines() if line.strip().startswith("Source:")]
        self.assertEqual(len(source_lines), 1)
        self.assertIn("dist", source_lines[0])
        self.assertIn("recursesubdirs", source_lines[0])
        self.assertIn("Flags: ignoreversion recursesubdirs createallsubdirs", source_lines[0])

    def test_setup_keeps_standard_install_launch_and_shortcut_paths(self):
        self.assertIn('DefaultDirName={autopf}\\Ryu\'s Audiobook', self.script)
        self.assertIn('#define MyAppExeName "Ryu\'s Audiobook.exe"', self.script)
        self.assertIn('Filename: "{app}\\{#MyAppExeName}"', self.script)
        self.assertIn('Flags: nowait postinstall skipifsilent', self.script)
        self.assertIn('Name: "{autodesktop}\\{#MyAppName}"', self.script)

    def test_uninstaller_does_not_delete_user_data(self):
        self.assertIn("User books, voices, models, and settings live under %USERPROFILE%", self.script)
        self.assertIn("[UninstallDelete]", self.script)
        self.assertIn("Deliberately do not remove user data outside {app}.", self.script)
        self.assertNotIn("Type: filesandordirs; Name: \"{userprofile}", self.script)


if __name__ == "__main__":
    unittest.main()
