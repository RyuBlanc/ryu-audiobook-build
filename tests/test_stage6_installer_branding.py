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
        self.assertIn("WizardImageBackColor=none", self.script)
        self.assertIn("WizardSmallImageFile=..\\assets\\ryu_audiobook_logo.png", self.script)
        self.assertIn("WizardSmallImageBackColor=none", self.script)
        self.assertIn("DefaultDialogFontName=Segoe UI", self.script)
        self.assertIn("SetupIconFile=..\\assets\\ryu_audiobook_logo.ico", self.script)
        self.assertNotIn("WizardForm.Color :=", self.script)
        self.assertNotIn("WizardForm.InnerPage.Color :=", self.script)

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
