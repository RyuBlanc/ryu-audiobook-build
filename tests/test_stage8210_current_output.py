"""Stage 8.2.10 regressions for current-output validity during generation."""
from pathlib import Path
import unittest


class Stage8210CurrentOutputTests(unittest.TestCase):
    def test_generation_hides_previous_output_until_new_book_is_validated(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        self.assertIn('"output_path": None, "generation_target_path": str(output)', source)
        self.assertIn('"status": "generating"', source)
        self.assertIn('output_text = str(payload.get("output_path") or state.get("output_path") or state.get("generation_target_path") or "").strip()', source)

    def test_player_does_not_treat_generation_target_as_completed_output(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = source.index("    def _player_get_active(")
        end = source.index("    def _settings_save(", start)
        method = source[start:end]
        self.assertIn('state.get("output_path") or ""', method)
        self.assertNotIn('state.get("generation_target_path")', method)

    def test_successful_generation_is_the_only_path_that_publishes_current_output(self):
        source = Path("app/ui/premium_v2_host.py").read_text(encoding="utf-8")
        start = source.index("    def _generation_finished(")
        end = source.index("    def _production_preview(", start)
        method = source[start:end]
        self.assertIn('if success:', method)
        self.assertIn('"output_path": str(actual)', method)
        self.assertIn('"output_path": None, "generation_target_path": str(output)', source)
