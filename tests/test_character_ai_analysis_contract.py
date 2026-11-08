from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CharacterAIAnalysisContracts(unittest.TestCase):
    def test_character_worker_uses_existing_book_wide_local_ai_pipeline(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
        end = host.index("\n    def _character_assign(", start)
        worker = host[start:end]
        self.assertIn("from app.ai.brain import AudiobookBrain", worker)
        self.assertIn("brain.analyze_book(", worker)
        self.assertIn("progress=update_ai_progress", worker)
        self.assertIn("brain.close()", worker)
        self.assertIn("source_grounded_fallback", worker)

    def test_ai_dialogue_predictions_are_grounded_in_exact_chapter_source_and_cast(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn("ai_dialogue_by_chapter", host)
        self.assertIn("quote_key not in source_key", host)
        self.assertIn("Local AI book-context analysis:", host)
        self.assertIn("canonical_speaker", host)

    def test_analysis_reports_full_coverage_and_no_silent_suggestion_limit(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
        end = host.index("\n    def _character_assign(", start)
        worker = host[start:end]
        self.assertNotIn("max_suggestions = 3000", worker)
        self.assertIn('"processed_chapters": processed_chapters', worker)
        self.assertIn('"total_chapters": total_chapters', worker)
        self.assertIn('"coverage_complete":', worker)
        self.assertIn('"truncated": False', worker)

    def test_local_ai_book_context_starts_with_user_saved_character_cast(self):
        brain = (ROOT / "app/ai/brain.py").read_text(encoding="utf-8")
        self.assertIn('initial_characters = base_context.get("characters")', brain)
        self.assertIn('bible[name] = dict(row, name=name)', brain)
        self.assertIn('book_context["characters"] = list(bible.values())', brain)


    def test_character_delete_persists_series_exclusion_and_readd_restores_detection(self):
        host = (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = host.index("    def _character_delete(")
        end = host.index("\n    def ", start + 1)
        delete_method = host[start:end]
        create_start = host.index("    def _character_create(")
        create_end = host.index("\n    def ", create_start + 1)
        create_method = host[create_start:create_end]
        worker_start = host.index("    def _character_worker(self, job_id: str, project) -> None:")
        worker_end = host.index("\n    def ", worker_start + 1)
        worker = host[worker_start:worker_end]
        self.assertIn('state["character_detection_exclusions"]', delete_method)
        self.assertIn('"series": selected_series', delete_method)
        self.assertIn("character_detection_exclusion_keys(", worker)
        self.assertIn("excluded_detection_keys", worker)
        self.assertIn("character_detection_exclusions", create_method)
        self.assertIn("excluded_detection_keys", worker)
        self.assertIn("character_detection_exclusion_keys(", worker)
        self.assertIn("character_detection_exclusions", worker)
        self.assertIn("protected_names", worker)


if __name__ == "__main__":
    unittest.main()
