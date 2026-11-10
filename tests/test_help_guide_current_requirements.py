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
        html = (ROOT / "assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
        help_start = html.index('<section class="page" id="help">')
        help_end = html.index("</main>", help_start)
        cls.original_guide = html[help_start:help_end]

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

    def test_original_detailed_seven_stage_help_guide_is_preserved(self):
        self.assertIn("root.children.length && String(root.textContent || '').trim()", self.guide)
        self.assertIn("preserved-static-guide", self.guide)
        for topic in (
            "Learn Ryu's Audiobook",
            "From book file to finished audiobook",
            "How to create an audiobook",
            "Import Studio",
            "Chapter Studio",
            "Voice Studio",
            "Character Studio",
            "Pronunciation Studio",
            "Sound Design",
            "Production Studio",
            "What every menu is for",
            "Qwen3 Voice Studio",
            "I want to…",
            "Your first successful audiobook",
            "Recovery flow",
            "Quality checklist",
            "Frequently asked questions",
        ):
            self.assertIn(topic, self.original_guide)

    def test_original_help_explains_the_current_narrator_only_gate(self):
        self.assertIn("Narrator-only audiobook generation (GEN-07)", self.guide)
        self.assertIn("zero saved character voice-profile assignments", self.guide)
        self.assertIn("normal cast-aware rules apply", self.guide)
        self.assertIn("zero valid character voice profiles are configured", self.original_guide)
        self.assertIn("unresolved dialogue must be reviewed or assigned", self.original_guide)

    def test_original_qwen_help_documents_model_sizes_and_private_runtime_verification(self):
        self.assertIn("Auto (hardware-aware), 0.6B, or 1.7B", self.original_guide)
        self.assertIn("isolated Qwen runtime self-test", self.original_guide)
        self.assertIn("explicit GPU selection must report failure", self.original_guide)

    def test_qwen_help_distinguishes_adapter_detection_from_verified_inference(self):
        self.assertIn("real inference reports that device", self.guide)
        self.assertIn("compute backend can be Automatic", self.guide)


if __name__ == "__main__":
    unittest.main()
