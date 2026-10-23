"""Regression coverage for live Dashboard data and selected audiobook playback."""
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest import mock

from app.chapters.detector import Chapter
from app.core.project import create_project
from app.core.state import load_state
from app.ui.premium_v2_host import PremiumV2Bridge, _parse_audio_chapter_metadata


ROOT = Path(__file__).resolve().parents[1]


class DashboardLiveDataTests(unittest.TestCase):
    def _create_project(self, library: Path, title: str) :
        source = library.parent / (title.replace(" ", "_") + ".txt")
        source.write_text("Source for " + title, encoding="utf-8")
        return create_project(title, source, [
            Chapter(1, "Chapter 1", "Non-empty chapter."),
            Chapter(2, "Chapter 2", ""),
        ])

    def test_project_summary_uses_saved_cover_voice_and_preparation_data(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            with mock.patch("app.core.project.library_root", return_value=library):
                project = self._create_project(library, "Slime Vol 2")

            cover = project.folder / "custom-cover.png"
            cover.write_bytes(b"image-file-placeholder")
            output = project.folder / "Slime Vol 2.m4b"
            output.write_bytes(b"audio-placeholder")
            state = {
                "status": "completed",
                "output_path": str(output),
                "cover_path": str(cover),
                "author": "Author",
                "narrator": "Amy",
                "voice_profile": "Amy",
                "characters": [
                    {"name": "Mira", "voice_profile": "Mira Voice"},
                    {"name": "Rimuru"},
                    {"name": "Shuna", "assigned_voice_profile": "Shuna Voice"},
                ],
                "voice_cast": {
                    "Mira": "Mira Voice",
                    "Shuna": "Shuna Voice",
                    "Rimuru": "",
                    "Narrator": "Amy",
                },
                "completed_chapters": [1],
                "last_edited_chapter_number": 2,
                "modified_at": "2026-10-23T00:00:00+00:00",
            }
            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            with mock.patch("app.ui.premium_v2_host.list_projects", return_value=[project]):
                with mock.patch("app.ui.premium_v2_host.load_state", return_value=state):
                    summary = bridge._project_list({})[0]

            self.assertEqual(summary["title"], "Slime Vol 2")
            self.assertEqual(summary["narrator"], "Amy")
            portable_cover = project.folder / "assets" / "cover.png"
            self.assertEqual(summary["cover_path"], str(portable_cover.resolve()))
            self.assertTrue(portable_cover.is_file())
            self.assertEqual(portable_cover.read_bytes(), cover.read_bytes())
            self.assertEqual(summary["chapter_count"], 2)
            self.assertEqual(summary["prepared_percent"], 65)
            self.assertEqual(summary["character_voice_count"], 2)
            self.assertEqual(summary["character_count"], 3)
            self.assertTrue(summary["character_analysis_done"])
            self.assertTrue(summary["source_exists"])
            self.assertTrue(summary["output_configured"])
            self.assertEqual(summary["last_edited_chapter_number"], 2)
            self.assertTrue(summary["completed"])
            self.assertEqual(summary["output_path"], str(output.resolve()))

    def test_legacy_epub_cover_is_discovered_and_persisted_into_project_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            source = base / "Legacy Book.epub"
            image_bytes = b"embedded-cover-image"
            with zipfile.ZipFile(source, "w") as epub:
                epub.writestr(
                    "META-INF/container.xml",
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                    '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                    '</rootfiles></container>',
                )
                epub.writestr(
                    "OEBPS/content.opf",
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                    '<manifest><item id="front-cover" href="images/front-cover.png" '
                    'media-type="image/png" properties="cover-image"/></manifest></package>',
                )
                epub.writestr("OEBPS/images/front-cover.png", image_bytes)

            with mock.patch("app.core.project.library_root", return_value=library):
                project = create_project(
                    "Legacy Book", source, [Chapter(1, "Chapter 1", "Readable source text.")]
                )

            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            summary = bridge._project_summary(project)
            saved_cover = project.folder / "assets" / "cover.png"
            state = load_state(project.folder)

            self.assertEqual(summary["cover_path"], str(saved_cover.resolve()))
            self.assertEqual(saved_cover.read_bytes(), image_bytes)
            self.assertTrue(state["cover_detection_attempted"])
            self.assertEqual(state["cover_path"], str(saved_cover.resolve()))

    def test_analyzed_book_without_characters_is_not_penalized_for_voice_cast(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            with mock.patch("app.core.project.library_root", return_value=library):
                project = self._create_project(library, "Narrator Only Book")
            project.chapters[1].text = "Second chapter has readable text."
            project.save()
            output = project.folder / "configured-output.m4b"
            state = {
                "status": "imported",
                "narrator": "Amy",
                "voice_profile": "Amy",
                "output_path": str(output),
                "character_analysis": {"dialogue_total": 0, "unassigned_dialogue": 0},
                "characters": [],
                "voice_cast": {},
            }
            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            with mock.patch("app.ui.premium_v2_host.load_state", return_value=state):
                summary = bridge._project_summary(project)

            self.assertTrue(summary["character_analysis_done"])
            self.assertEqual(summary["character_count"], 0)
            self.assertEqual(summary["character_voice_count"], 0)
            self.assertEqual(summary["prepared_percent"], 90)

    def test_player_position_saves_to_correct_project_without_changing_modified_time(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            with mock.patch("app.core.project.library_root", return_value=library):
                project = self._create_project(library, "Resume Me")
            original_state = {
                "modified_at": "2026-01-01T00:00:00+00:00",
                "playback_position_seconds": 10,
            }
            from app.core.state import save_state
            save_state(project.folder, original_state)
            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            with mock.patch("app.ui.premium_v2_host.list_projects", return_value=[project]):
                result = bridge._player_position_save({
                    "folder": str(project.folder),
                    "position_seconds": 123.45,
                })
            state = load_state(project.folder)
            self.assertTrue(result["saved"])
            self.assertEqual(result["position_seconds"], 123.45)
            self.assertEqual(state["playback_position_seconds"], 123.45)
            self.assertEqual(state["modified_at"], "2026-01-01T00:00:00+00:00")

    def test_narrator_metadata_alone_does_not_count_as_selected_tts_voice(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            with mock.patch("app.core.project.library_root", return_value=library):
                project = self._create_project(library, "Metadata Only Narrator")
            output = project.folder / "configured-output.m4b"
            state = {
                "status": "imported",
                "narrator": "Amy",
                "output_path": str(output),
            }
            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            with mock.patch("app.ui.premium_v2_host.load_state", return_value=state):
                summary = bridge._project_summary(project)
            self.assertEqual(summary["narrator"], "Amy")
            self.assertFalse(summary["narrator_voice_configured"])
            self.assertEqual(summary["prepared_percent"], 35)

    def test_docx_embedded_image_is_used_when_thumbnail_and_named_cover_are_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            source = base / "Book with embedded cover.docx"
            image_bytes = b"first-embedded-docx-image"
            with zipfile.ZipFile(source, "w") as docx:
                docx.writestr("word/media/image1.png", image_bytes)
                docx.writestr("word/document.xml", "<w:document/>")

            with mock.patch("app.core.project.library_root", return_value=library):
                project = create_project(
                    "Book with embedded cover", source,
                    [Chapter(1, "Chapter 1", "Readable source text.")]
                )
            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            summary = bridge._project_summary(project)
            saved_cover = project.folder / "assets" / "cover.png"
            state = load_state(project.folder)

            self.assertEqual(summary["cover_path"], str(saved_cover.resolve()))
            self.assertEqual(saved_cover.read_bytes(), image_bytes)
            self.assertTrue(state["cover_detection_attempted"])

    def test_embedded_audio_chapter_metadata_is_parsed_into_seek_boundaries(self):
        probe_output = """
  Chapter #0:0: start 0.000000, end 102.500000
    Metadata:
      title           : Chapter 1 · Beginning
  Chapter #0:1: start 102.500000, end 245.250000
    Metadata:
      title           : Chapter 2 · Journey
"""
        chapters = _parse_audio_chapter_metadata(probe_output)
        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]["number"], 1)
        self.assertEqual(chapters[0]["title"], "Chapter 1 · Beginning")
        self.assertEqual(chapters[0]["start_seconds"], 0)
        self.assertEqual(chapters[0]["end_seconds"], 102.5)
        self.assertEqual(chapters[1]["start_seconds"], 102.5)
        self.assertEqual(chapters[1]["end_seconds"], 245.25)

    def test_player_resolves_requested_audiobook_not_active_editor_project(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            library = base / "library"
            with mock.patch("app.core.project.library_root", return_value=library):
                first = create_project("Book A", self._source(library, "Book A"), [Chapter(1, "A", "Book A text.")])
                second = create_project("Book B", self._source(library, "Book B"), [Chapter(1, "B", "Book B text.")])
            output_a = first.folder / "Book A.m4b"
            output_b = second.folder / "Book B.m4b"
            output_a.write_bytes(b"audio A")
            output_b.write_bytes(b"audio B")
            states = {
                str(first.folder): {"status": "completed", "output_path": str(output_a), "narrator": "Voice A"},
                str(second.folder): {"status": "completed", "output_path": str(output_b), "narrator": "Voice B"},
            }
            bridge = PremiumV2Bridge.__new__(PremiumV2Bridge)
            bridge.settings = mock.Mock()
            bridge.settings.value.side_effect = lambda _key, default=None: default
            with mock.patch("app.ui.premium_v2_host.list_projects", return_value=[first, second]):
                with mock.patch("app.ui.premium_v2_host.load_state", side_effect=lambda folder: states[str(folder)]):
                    selected = bridge._player_get_active({"folder": str(second.folder)})

            self.assertEqual(selected["title"], "Book B")
            self.assertEqual(selected["output_path"], str(output_b.resolve()))
            self.assertEqual(selected["narrator"], "Voice B")

    @staticmethod
    def _source(library: Path, title: str) -> Path:
        source = library.parent / (title.replace(" ", "_") + ".txt")
        source.write_text("Source for " + title, encoding="utf-8")
        return source

    def test_frontend_binds_dashboard_cards_and_delays_mini_player(self):
        adapter = (ROOT / "assets" / "frontend" / "premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("async function refreshDashboardHero", adapter)
        self.assertIn("function refreshDashboardGeneration", adapter)
        self.assertIn("function renderAudiobookLibrary", adapter)
        self.assertIn("function refreshDashboardFlow", adapter)
        self.assertIn("refreshDashboardFlow(dashboardProject)", adapter)
        self.assertIn("Boolean(String(project.voice_profile || '').trim())", adapter)
        self.assertIn("const progressLine = [...card.querySelectorAll('.job-line')][2]", adapter)
        self.assertIn("hero.querySelector('.meta-row > span:first-child')", adapter)
        self.assertIn("hero.querySelector('.meta-row > span:nth-child(2)')", adapter)
        self.assertIn("function clearAudiobookPlayerDisplay", adapter)
        self.assertIn("function renderSelectedAudiobook(data)", adapter)
        self.assertIn("const playSelectedAudiobook = () =>", adapter)
        self.assertIn("function bindAudiobookPlayerControls()", adapter)
        self.assertIn("function jumpPlayerChapter(direction)", adapter)
        self.assertIn("playerAudio.currentTime = duration *", adapter)
        self.assertIn("persistPlayerPosition(false, false, audioFolder, audio)", adapter)
        self.assertIn("call('player.position.save'", adapter)
        self.assertIn("call('settings.save', {player_rate:rate})", adapter)
        self.assertIn("call('settings.save', {player_volume:playerVolume})", adapter)
        self.assertIn('"player.position.save": self._player_position_save', host)
        self.assertIn("def _parse_audio_chapter_metadata", host)
        self.assertIn("data-play-project-folder", adapter)
        self.assertIn(".mini-cover,.book-cover,.project-cover", adapter)
        self.assertIn("if (!playerAudio || !playerAudio.src) clearAudiobookPlayerDisplay()", adapter)
        self.assertIn("button.dataset.continueProjectFolder", adapter)
        self.assertIn("button.dataset.playProjectFolder", adapter)
        self.assertIn("const runAction = async fn =>", adapter)
        self.assertIn("void runAction(async () =>", adapter)
        self.assertIn("call('player.get_active', {folder})", adapter)
        self.assertIn("miniDock.classList.add('hidden')", adapter)
        self.assertIn("function syncMiniPlayer", adapter)
        self.assertIn("window.__ryuDashboardProjectTimer", adapter)
        self.assertIn("if (dashboardPageActive()) refreshProjects().catch(() => {})", adapter)
        self.assertIn('voice_cast = state.get("voice_cast")', host)
        self.assertIn("extract_embedded_cover(source_for_cover, project.folder)", host)
        cover_art = (ROOT / "app" / "documents" / "cover_art.py").read_text(encoding="utf-8")
        self.assertIn("embedded_images = [", cover_art)
        self.assertIn("character_voice_ratio = (", host)
        generation = (ROOT / "app" / "ui" / "generation_page.py").read_text(encoding="utf-8")
        self.assertIn("persist_project_cover(selected, self.project_folder)", generation)


if __name__ == "__main__":
    unittest.main()
