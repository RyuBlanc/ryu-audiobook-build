from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage3NarratorSegmentationContracts(unittest.TestCase):
    def test_backend_exposes_source_backed_narrator_segmentation(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('"character.narration.segments.list": self._character_narration_segments_list', host)
        self.assertIn("def _character_narration_segments_list(", host)
        self.assertIn("segment_chapter_speakers(chapter)", host)
        self.assertIn('chapter.narrator_passages = [', host)
        self.assertIn('"automatic": True', host)

    def test_character_studio_displays_narration_as_a_dedicated_speaker_role(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "async function refreshCharacterNarrationSegments()",
            "character.narration.segments.list",
            "function characterNarrationSegmentsForChapter(chapter)",
            "Narrator · Auto",
            "Needs speaker",
            "kind === 'needs_speaker_review'",
            "review-' + Number(chapter.number)",
            "ryu-narrator-passage",
        ):
            self.assertIn(token, adapter)


    def test_series_narrator_default_backend_commands_and_project_precedence(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            '"narrator.series.default.get": self._narrator_series_default_get',
            '"narrator.series.default.save": self._narrator_series_default_save',
            '"narrator.series.default.apply": self._narrator_series_default_apply',
            'def _narrator_series_default_get(',
            'def _narrator_series_default_save(',
            'def _narrator_series_default_apply(',
            '"narrator_profile_source": "project_override"',
            'effective = project_profile or default_profile',
        ):
            self.assertIn(token, host)
        for token in ("Series Narrator Default", "Save Series Default", "Reset to Series Default",
                      "narrator.series.default.save", "narrator.project.reset"):
            self.assertIn(token, adapter)
        self.assertNotIn("Apply to This Book", adapter)

    def test_narrator_preview_requires_source_backed_narration_and_reuses_voice_preview(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        self.assertIn('"narrator.preview": self._narrator_preview', host)
        self.assertIn('def _narrator_preview(', host)
        self.assertIn('segment_chapter_speakers(chapter)', host)
        self.assertIn('segment.kind != "narration"', host)
        self.assertIn('"route_character_cast": False', host)
        self.assertIn('id="previewProjectNarrator"', adapter)
        self.assertIn("call('narrator.preview'", adapter)

    def test_new_series_creation_requires_a_saved_previewed_narrator(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "ryuCreateSeriesNarratorSetup",
            "ryuCreateSeriesNarratorProfile",
            "ryuCreateSeriesNarratorSample",
            "Preview Narrator",
            "Play Narrator Preview",
            "narrator.preview",
            "narrator.series.default.save",
            "Preview and listen to the selected saved narrator profile before saving this new series.",
            "narratorPanel.hidden=!createSeries",
        ):
            self.assertIn(token, adapter)

    def test_series_narrator_summary_reader_does_not_require_active_project(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _narrator_series_default_read(")
        end = host.index("    def _narrator_series_default_get(", start)
        reader = host[start:end]
        self.assertNotIn("self._active_project()", reader)
        self.assertIn("_narrator_series_default_read(project, state,", host)
