from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Stage3NarratorSegmentationContracts(unittest.TestCase):
    def test_backend_exposes_source_backed_narrator_segmentation(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('"character.narration.segments.list": self._character_narration_segments_list', host)
        self.assertIn("def _character_narration_segments_list(", host)
        self.assertIn("segment_chapter_speakers(chapter)", host)

    def test_character_studio_displays_narration_as_a_dedicated_speaker_role(self):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        for token in (
            "async function refreshCharacterNarrationSegments()",
            "character.narration.segments.list",
            "function characterNarrationSegmentsForChapter(chapter)",
            "Narrator · Auto",
            "Needs speaker",
            "ryu-narrator-passage",
        ):
            self.assertIn(token, adapter)
