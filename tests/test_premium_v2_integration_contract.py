from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "assets" / "frontend" / "ryu_audiobook_premium_v2.html"
HOST = ROOT / "app" / "ui" / "premium_v2_host.py"
MAIN = ROOT / "app" / "main.py"
BUILD = ROOT / "build.py"


class PremiumV2IntegrationContractTests(unittest.TestCase):
    """Static release guards for the embedded Premium V2 frontend and bridge."""

    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.host = HOST.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.build = BUILD.read_text(encoding="utf-8")

    def test_authoritative_html_has_all_fifteen_destinations(self):
        self.assertTrue(HTML.is_file())
        destinations = re.findall(r'data-page="([^"]+)"', self.html)
        self.assertEqual(
            destinations,
            ["dashboard", "library", "import", "chapters", "voices", "characters",
             "pronunciation", "sound", "generate", "player", "history", "models",
             "performance", "settings", "help"],
        )
        for page in destinations:
            self.assertRegex(self.html, rf'<section[^>]+id="{re.escape(page)}"')

    def test_embedded_host_uses_local_html_and_qt_webchannel(self):
        self.assertIn("QWebEngineView", self.host)
        self.assertIn("QWebChannel", self.host)
        self.assertIn("QUrl.fromLocalFile", self.host)
        self.assertIn("qrc:///qtwebchannel/qwebchannel.js", self.host)
        self.assertIn("JavascriptCanOpenWindows, False", self.host)
        self.assertIn("def dispatch(", self.host)

    def test_only_real_bridge_commands_are_advertised_as_connected(self):
        self.assertIn('"app.get_info": True', self.host)
        self.assertIn('"project.list": True', self.host)
        self.assertIn('"settings.get": True', self.host)
        self.assertIn('"project.create": False', self.host)
        self.assertIn('"production.generate_book": False', self.host)
        self.assertIn("not_connected", self.host)

    def test_dashboard_and_library_query_real_project_records(self):
        self.assertIn("ryu-premium-v2-backend-binding", self.html)
        self.assertIn("window.ryuBackend.invoke('project.list')", self.html)
        self.assertIn("window.ryuPremiumProjects", self.html)
        self.assertIn("job service is connected", self.html)
        self.assertIn("integration pending", self.html)

    def test_frontend_is_packaged_and_selected_by_desktop_entrypoint(self):
        self.assertIn("ryu_audiobook_premium_v2.html", self.build)
        self.assertIn("PremiumV2Window", self.main)
        self.assertIn("frontend_path().is_file()", self.main)


if __name__ == "__main__":
    unittest.main()
