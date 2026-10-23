"""Regression coverage for live Dashboard data and selected audiobook playback."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from app.chapters.detector import Chapter
from app.core.project import create_project
from app.ui.premium_v2_host import PremiumV2Bridge


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
            self.assertEqual(summary["cover_path"], str(cover.resolve()))
            self.assertEqual(summary["chapter_count"], 2)
            self.assertEqual(summary["prepared_percent"], 50)
            self.assertEqual(summary["character_voice_count"], 2)
            self.assertEqual(summary["last_edited_chapter_number"], 2)
            self.assertTrue(summary["completed"])
            self.assertEqual(summary["output_path"], str(output.resolve()))

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
        self.assertIn("async function refreshDashboardHero", adapter)
        self.assertIn("function refreshDashboardGeneration", adapter)
        self.assertIn("function renderAudiobookLibrary", adapter)
        self.assertIn("button.dataset.continueProjectFolder", adapter)
        self.assertIn("button.dataset.playProjectFolder", adapter)
        self.assertIn("const runAction = async fn =>", adapter)
        self.assertIn("void runAction(async () =>", adapter)
        self.assertIn("call('player.get_active', {folder})", adapter)
        self.assertIn("miniDock.classList.add('hidden')", adapter)
        self.assertIn("function syncMiniPlayer", adapter)
        self.assertIn("window.__ryuDashboardProjectTimer", adapter)
        self.assertIn("if (dashboardPageActive()) refreshProjects().catch(() => {})", adapter)
        host = (ROOT / "app" / "ui" / "premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('voice_cast = state.get("voice_cast")', host)


if __name__ == "__main__":
    unittest.main()
