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
        self.assertIn("WizardForm.Color := $000F0A09;", self.script)
        self.assertIn("WizardForm.MainPanel.Color := $001A130F;", self.script)
        self.assertIn("WizardForm.PageNameLabel.Font.Color := $006AB0D6;", self.script)
        self.assertIn("WizardForm.Font.Name := 'Segoe UI';", self.script)
        self.assertIn("SetupIconFile=..\\assets\\ryu_audiobook_logo.ico", self.script)

    def test_setup_keeps_standard_install_launch_and_shortcut_paths(self):
        self.assertIn('DefaultDirName={autopf}\\Ryu\'s Audiobook', self.script)
        self.assertIn('Filename: "{app}\\Ryu\'s Audiobook.exe"', self.script)
        self.assertIn('Flags: nowait postinstall skipifsilent', self.script)
        self.assertIn('Name: "{autodesktop}\\{#MyAppName}"', self.script)

    def test_uninstaller_does_not_delete_user_data(self):
        self.assertIn("User books, voices, models, and settings live under %USERPROFILE%", self.script)
        self.assertIn("[UninstallDelete]", self.script)
        self.assertIn("Deliberately do not remove user data outside {app}.", self.script)
        self.assertNotIn("Type: filesandordirs; Name: \"{userprofile}", self.script)


if __name__ == "__main__":
    unittest.main()
