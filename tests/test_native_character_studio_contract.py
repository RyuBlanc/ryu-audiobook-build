from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeCharacterStudioContractTests(unittest.TestCase):
    def test_native_character_tabs_render_live_project_chapters(self):
        panel = (ROOT / "app/ui/native_character_studio.py").read_text(encoding="utf-8")
        cast = (ROOT / "app/ui/voice_cast_page.py").read_text(encoding="utf-8")
        self.assertIn("class NativeCharacterDialoguePanel(QWidget)", panel)
        self.assertIn("QTextBrowser", panel)
        self.assertIn("dialogue_segments(chapter)", panel)
        self.assertIn('getattr(chapter, "dialogue_assignments", [])', panel)
        self.assertIn('self.view_tabs.addTab(self.dialogue_panel.manual_tab, "Character assigning")', cast)
        self.assertIn('self.view_tabs.addTab(self.dialogue_panel.ai_tab, "Analyze Book (AI)")', cast)
        self.assertNotIn("QWebEngineView", panel)

    def test_assignments_are_exactly_persisted_and_feed_learning_memory(self):
        panel = (ROOT / "app/ui/native_character_studio.py").read_text(encoding="utf-8")
        self.assertIn("source[start:end] != exact", panel)
        self.assertIn("project.save()", panel)
        self.assertIn("record_assignment_feedback(", panel)
        self.assertIn("remove_assignment_feedback(", panel)
        self.assertIn("character_dialogue_skips", panel)
        self.assertIn("learning_examples=learning_index", panel)
        self.assertIn("source_grounded_speaker_for_continuity", panel)

    def test_series_and_saved_voice_profile_flow_are_live(self):
        panel = (ROOT / "app/ui/native_character_studio.py").read_text(encoding="utf-8")
        cast = (ROOT / "app/ui/voice_cast_page.py").read_text(encoding="utf-8")
        self.assertIn("class NativeCharacterRecordDialog", panel)
        self.assertIn("Audio profile", panel)
        self.assertIn("series_names", panel)
        self.assertIn("grouped.setdefault(series, []).append(row)", cast)
        self.assertIn('"series": str(row.get("series") or default_series)', cast)
        self.assertIn("Test assigned sentence", cast)
        self.assertIn("VoicePreviewWorker(preview_profile, sample_text, output, 10)", panel)

    def test_assigned_sentence_preview_uses_real_synthesis_and_player(self):
        panel = (ROOT / "app/ui/native_character_studio.py").read_text(encoding="utf-8")
        self.assertIn("self._player.setSource(QUrl.fromLocalFile(path))", panel)
        self.assertIn("self._player.play()", panel)

    def test_dialogue_link_route_avoids_qt_numeric_host_normalization(self):
        from PySide6.QtCore import QUrl
        from app.ui.native_character_studio import _decode_dialogue_link, _dialogue_link

        rendered = _dialogue_link(1, 34, 47)
        parsed = QUrl(rendered)
        self.assertEqual(rendered, "dialogue://chapter/1/34/47")
        self.assertEqual(parsed.host(), "chapter")
        self.assertEqual(_decode_dialogue_link(parsed), (1, 34, 47))

        # Keep links from an already-open legacy panel readable as well.
        legacy = QUrl("dialogue://1/34/47")
        self.assertEqual(legacy.host(), "0.0.0.1")
        self.assertEqual(_decode_dialogue_link(legacy), (1, 34, 47))


if __name__ == "__main__":
    unittest.main()
