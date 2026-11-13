from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from app.core.character_identity import character_identity_key

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

    def test_qwen_voice_design_preview_model_selection_matches_production_preferences(self):
        from unittest.mock import patch
        from app.ui.native_character_studio import _qwen_voice_design_preview_model_kinds

        for preference, expected_base in (("0.6b", "base-0.6b"), ("1.7b", "base-1.7b")):
            with self.subTest(preference=preference), patch(
                "app.ui.native_character_studio.get_qwen_model_preference",
                return_value=preference,
            ):
                self.assertEqual(
                    _qwen_voice_design_preview_model_kinds(),
                    ("design-1.7b", expected_base),
                )

        with (
            patch("app.ui.native_character_studio.get_qwen_model_preference", return_value="auto"),
            patch("app.ui.native_character_studio.best_voice_design_kind", return_value="design-1.7b"),
            patch("app.ui.native_character_studio.best_long_form_clone_kind", return_value="base-0.6b"),
        ):
            self.assertEqual(
                _qwen_voice_design_preview_model_kinds(),
                ("design-1.7b", "base-0.6b"),
            )

    def test_native_character_qwen_design_audition_keeps_the_saved_identity_locked_profile(self):
        panel = (ROOT / "app/ui/native_character_studio.py").read_text(encoding="utf-8")
        start = panel.index("    def test_voice_profile(")
        end = panel.index("    def _play_character_preview(", start)
        method = panel[start:end]
        self.assertIn("_qwen_voice_design_preview_model_kinds()", method)
        self.assertIn("if not model_installed(kind)", method)
        self.assertIn("if not model_installed(base_kind)", method)
        self.assertIn("preview_profile = profile", method)
        self.assertNotIn('qwen_mode="design-preview"', method)
        self.assertNotIn("replace(profile", method)
        self.assertIn("VoicePreviewWorker(preview_profile, sample_text, output, 10)", method)

    def test_voice_studio_assignment_choices_keep_same_named_series_identities_separate(self):
        from app.ui.voice_page import _voice_assignment_targets

        targets = _voice_assignment_targets(
            [
                {"name": "Mira", "series": "Series One", "aliases": ["Mira One"]},
                {"name": "Mira", "series": "Series Two", "aliases": ["Mira Two"]},
                {"name": "Ren", "series": "Series One"},
            ],
            "Series One",
        )
        self.assertEqual(
            [item["label"] for item in targets],
            ["Mira — Series One", "Mira — Series Two", "Ren"],
        )
        self.assertEqual(
            {(item["name"], item["series"]) for item in targets},
            {("Mira", "Series One"), ("Mira", "Series Two"), ("Ren", "Series One")},
        )

    def test_voice_studio_character_assignment_uses_selected_series_and_canonical_writer(self):
        from unittest.mock import patch
        from app.ui.voice_page import VoicePage
        from app.tts.voice_profile import VoiceProfile

        with tempfile.TemporaryDirectory() as temporary:
            preview = Path(temporary) / "preview.wav"
            preview.write_bytes(b"valid preview")
            folder = Path(temporary) / "book"
            folder.mkdir()
            saved = VoiceProfile("Mira Qwen", "qwen-character", "Ryan", qwen_profile_id="mira-profile")
            first = {"name": "Mira", "series": "Series One", "voice": "Old One"}
            second = {"name": "Mira", "series": "Series Two", "voice": "Old Two"}
            cast = SimpleNamespace(
                rows=[first, second], _series_name=lambda: "Series One",
                _save_cast=Mock(), _refresh_labels=Mock(),
            )
            generation = SimpleNamespace(_load_voice_cast_summary=Mock(), _refresh_readiness=Mock())
            window = SimpleNamespace(
                project=SimpleNamespace(title="Series One"), voice_cast=cast, generation=generation,
            )
            page = SimpleNamespace(
                _profile_from_ui=lambda: saved, last_preview=preview,
                _preview_profile_signature=("saved",), _voice_profile_signature=lambda _profile: ("saved",),
                _active_project_folder=lambda: folder, status=Mock(), window=lambda: window,
                _refresh_assignment_actions=Mock(),
            )
            with (
                patch("app.ui.voice_page.load_saved_profiles", return_value=[saved]),
                patch("app.ui.voice_page.load_state", return_value={"series_name": "Series One", "voice_cast": {}}),
                patch("app.ui.voice_page.QInputDialog.getItem", return_value=("Mira — Series Two", True)),
            ):
                VoicePage.assign_to_character(page)

            self.assertEqual(first["voice"], "Old One")
            self.assertEqual(second["voice"], saved.name)
            cast._save_cast.assert_called_once_with(update_voice=True)
            cast._refresh_labels.assert_called_once()
            generation._load_voice_cast_summary.assert_called_once()
            generation._refresh_readiness.assert_called_once()
            self.assertIn("[Series Two]", page.status.setText.call_args.args[0])

    def test_voice_studio_character_assignment_persists_through_scoped_fallback_without_cast_page(self):
        from unittest.mock import patch
        from app.ui.voice_page import VoicePage
        from app.tts.voice_profile import VoiceProfile

        with tempfile.TemporaryDirectory() as temporary:
            preview = Path(temporary) / "preview.wav"
            preview.write_bytes(b"valid preview")
            folder = Path(temporary) / "book"
            folder.mkdir()
            saved = VoiceProfile("Mira Qwen", "qwen-character", "Ryan", qwen_profile_id="mira-profile")
            window = SimpleNamespace(project=SimpleNamespace(title="Series One"), generation=None)
            page = SimpleNamespace(
                _profile_from_ui=lambda: saved, last_preview=preview,
                _preview_profile_signature=("saved",), _voice_profile_signature=lambda _profile: ("saved",),
                _active_project_folder=lambda: folder, status=Mock(), window=lambda: window,
                _refresh_assignment_actions=Mock(),
            )
            state = {
                "series_name": "Series One", "voice_cast": {},
                "voice_cast_character_roster": [
                    {"name": "Mira", "series": "Series One"},
                    {"name": "Mira", "series": "Series Two"},
                ],
            }
            persisted = {}
            with (
                patch("app.ui.voice_page.load_saved_profiles", return_value=[saved]),
                patch("app.ui.voice_page.load_state", return_value=state),
                patch("app.ui.voice_page.save_state", side_effect=lambda _folder, value: persisted.update(value)),
                patch("app.ui.voice_page.sync_characters"),
                patch("app.ui.voice_page.QInputDialog.getItem", return_value=("Mira — Series Two", True)),
            ):
                VoicePage.assign_to_character(page)

            self.assertEqual(
                persisted["voice_cast_identity_assignments"],
                {character_identity_key("Mira", "Series Two"): saved.name},
            )
            self.assertNotIn("Mira", persisted["voice_cast"])
            self.assertEqual(
                {item["series"] for item in persisted["voice_cast_character_roster"]},
                {"Series One", "Series Two"},
            )

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
