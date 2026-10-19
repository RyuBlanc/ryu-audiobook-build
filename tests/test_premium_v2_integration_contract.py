from pathlib import Path
import re
import unittest
from bs4 import BeautifulSoup


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
        soup = BeautifulSoup(self.html, "html.parser")
        destinations = [button.get("data-page") for button in soup.select("button.nav-btn[data-page]")]
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
        self.assertIn('"project.open": True', self.host)
        self.assertIn('"chapter.list": True', self.host)
        self.assertIn('"chapter.update": True', self.host)
        # New commands must point to real handlers; never preserve the old
        # "not connected" placeholders as release requirements.
        for command, handler in {
            "import.start": "_import_start",
            "voice.list": "_voice_list",
            "voice.select": "_voice_select",
            "voice.preview": "_voice_preview",
            "voice.save": "_voice_save",
            "voice.import_reference": "_voice_import_reference",
            "character.analyze": "_character_analyze",
            "pronunciation.save": "_pronunciation_save",
            "production.generate_book": "_production_generate_book",
            "job.list": "_job_list",
            "history.list": "_history_list",
            "sound.catalog": "_sound_catalog",
        }.items():
            self.assertIn(f'"{command}": self.{handler}', self.host)
        self.assertIn('"project.create": False', self.host)
        self.assertIn('"production.generate_book": True', self.host)
        self.assertIn('"voice.save": True', self.host)
        self.assertIn('"voice.import_reference": True', self.host)
        self.assertIn("Confirm that you have permission", self.host)
        self.assertIn("def _voice_save(", self.host)
        self.assertIn('if provider_name == "chatterbox" and not voice_id:', self.host)
        self.assertIn("voice_id = name", self.host)
        self.assertIn("def _voice_import_reference(", self.host)
        self.assertIn("def _generation_finished(", self.host)
        self.assertIn("def _import_worker(", self.host)
        self.assertIn("not_connected", self.host)

    def test_authoritative_html_remains_presentation_source_and_adapter_owns_backend_calls(self):
        # The approved HTML stays visually authoritative and free of injected bridge edits.
        self.assertIn("<title>Ryu's Audiobook · Dragon Studio</title>", self.html)
        self.assertNotIn("window.ryuBackend", self.html)
        for control in ("browseBtn", "saveChapter", "saveProfile", "analyzeCharacters", "startGenerate"):
            self.assertRegex(self.html, rf'id="{re.escape(control)}"')
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn("call('project.list')", adapter)
        self.assertIn("call('chapter.list')", adapter)
        self.assertIn("call('chapter.update'", adapter)
        self.assertIn("call('import.start'", adapter)
        self.assertIn("call('voice.save'", adapter)
        self.assertIn("call('character.analyze'", adapter)
        self.assertIn("call('production.generate_book'", adapter)

    def test_backend_adapter_is_loaded_and_bundled(self):
        adapter = ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js"
        self.assertTrue(adapter.is_file())
        script = adapter.read_text(encoding="utf-8")
        for command in (
            "project.list", "project.open", "import.choose_file", "import.start", "chapter.update",
            "voice.list", "voice.save", "voice.import_reference", "voice.preview",
            "character.analyze", "character.assign", "pronunciation.list",
            "pronunciation.save", "pronunciation.analyze", "production.preview",
            "production.generate_book", "player.get_active", "job.list", "job.pause", "job.resume",
            "job.cancel", "settings.save", "sound.catalog", "sound.import", "sound.assign", "sound.save_manifest",
        ):
            self.assertIn(command, script)
        self.assertIn('adapter_path = frontend_path().with_name("premium_v2_backend_adapter.js")', self.host)
        self.assertIn('adapter_path.read_text(encoding="utf-8")', self.host)
        self.assertIn("premium_v2_backend_adapter.js", self.build)
        self.assertIn("function preparePreviewPlayback(job)", script)
        self.assertIn("previewAudio.play()", script)
        self.assertIn("previewAudio.pause()", script)
        self.assertIn("lengthGroup?.querySelector('.seg button.active')", script)
        self.assertIn("duration_seconds:Number(duration)", script)
        self.assertIn("function openPlayer()", script)
        self.assertIn("playerAudio.play()", script)

    def test_frontend_is_packaged_and_selected_by_desktop_entrypoint(self):
        self.assertIn("ryu_audiobook_premium_v2.html", self.build)
        self.assertIn("PremiumV2Window", self.main)
        self.assertIn("frontend_path().is_file()", self.main)


if __name__ == "__main__":
    unittest.main()
