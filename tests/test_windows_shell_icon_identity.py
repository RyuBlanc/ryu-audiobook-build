from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WindowsShellIconIdentityTests(unittest.TestCase):
    def test_main_application_bundles_and_prefers_the_multi_size_ico(self):
        build = (ROOT / "build.py").read_text(encoding="utf-8")
        main = (ROOT / "app/main.py").read_text(encoding="utf-8")
        self.assertIn('f"--add-data={LOGO_ICO};assets"', build)
        self.assertIn('f"--icon={LOGO_ICO}"', build)
        self.assertLess(main.index("ryu_audiobook_logo.ico"), main.index("ryu_audiobook_logo.png"))
        self.assertIn('app.setWindowIcon(app_icon)', main)
        self.assertIn('window.setWindowIcon(app_icon)', main)

    def test_main_application_sets_a_stable_windows_app_user_model_id(self):
        source = (ROOT / "app/main.py").read_text(encoding="utf-8")
        self.assertIn("SetCurrentProcessExplicitAppUserModelID", source)
        self.assertIn('RyuBlanc.RyuAudiobook', source)
        self.assertIn('_set_windows_app_user_model_id("RyuBlanc.RyuAudiobook")', source)

    def test_setup_process_sets_its_own_taskbar_identity_and_application_icon(self):
        source = (ROOT / "installer/html_installer.py").read_text(encoding="utf-8")
        builder = (ROOT / "installer/build_html_installer.py").read_text(encoding="utf-8")
        self.assertIn("SetCurrentProcessExplicitAppUserModelID", source)
        self.assertIn('RyuBlanc.RyuAudiobook.Setup', source)
        self.assertIn('_set_windows_app_user_model_id("RyuBlanc.RyuAudiobook.Setup")', source)
        self.assertIn("app.setWindowIcon(app_icon)", source)
        self.assertIn("self.setWindowIcon(QIcon(str(icon)))", source)
        self.assertIn('f"--icon={LOGO_ICO}"', builder)
        self.assertIn('f"--add-data={LOGO_ICO};assets"', builder)


if __name__ == "__main__":
    unittest.main()
