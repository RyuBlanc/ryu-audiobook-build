from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CurrentHelpGuideRequirements(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        adapter = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")
        start = adapter.index("function renderHelpGuide()")
        end = adapter.index("\n  function ", start + 1)
        cls.guide = adapter[start:end]

    def test_gen07_explains_zero_profile_gate_dialogue_routing_and_narrator_requirement(self):
        for phrase in (
            "Narrator-only audiobook generation (GEN-07)",
            "zero saved character voice-profile assignments",
            "including quoted and dash-led dialogue",
            "missing narrator profiles continue to block generation",
            "normal cast-aware rules apply",
        ):
            self.assertIn(phrase, self.guide)

    def test_character_studio_help_matches_live_chapter_and_saved_profile_controls(self):
        for phrase in (
            "left chapter list in both Manual and AI review",
            "AI pending queue is filtered to the selected chapter",
            "choose a saved Voice Studio profile in the review panel",
            "Edit Character also lets you change the saved profile",
            "Quoted or dash-led dialogue remains in Needs Speaker Review",
        ):
            self.assertIn(phrase, self.guide)

    def test_background_jobs_help_explains_safe_character_analysis_cancellation(self):
        self.assertIn("Character Analysis can be cancelled at a safe inference or chapter boundary", self.guide)
        self.assertIn("does not replace the saved cast with partial results", self.guide)

    def test_qwen_help_distinguishes_adapter_detection_from_verified_inference(self):
        self.assertIn("real inference reports that device", self.guide)
        self.assertIn("compute backend can be Automatic", self.guide)


if __name__ == "__main__":
    unittest.main()
