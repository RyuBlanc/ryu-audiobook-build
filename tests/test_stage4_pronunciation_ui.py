"""Stage 4 Step 1: real Dictionary UI contract tests."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "assets/frontend/ryu_audiobook_premium_v2.html").read_text(encoding="utf-8")
ADAPTER = (ROOT / "assets/frontend/premium_v2_backend_adapter.js").read_text(encoding="utf-8")


class PronunciationDictionaryUiTests(unittest.TestCase):
    def test_dictionary_is_the_only_pronunciation_management_view(self):
        start = HTML.index('<section class="page" id="pronunciation">')
        end = HTML.index('<section class="page" id="sound">', start)
        section = HTML[start:end]
        self.assertIn("id=\"pronDictionaryBody\"", section)
        self.assertNotIn("data-pron-tab", section)
        self.assertNotIn("Review terms", section)
        self.assertNotIn("Voice test matrix", section)

    def test_required_table_columns_have_exact_order_and_six_columns(self):
        start = HTML.index('<table class="dictionary-table"', HTML.index('id="pronunciation"'))
        end = HTML.index("</thead>", start)
        headings = re.findall(r"<th(?=[ >])[^>]*>(.*?)</th>", HTML[start:end], re.I | re.S)
        self.assertEqual(["S.No", "Written", "Pronounce as", "Audio Preview", "Options", "Enable"], headings)

    def test_pronunciation_screen_has_saved_profile_search_scope_origin_and_bulk_controls(self):
        start = HTML.index('<section class="page" id="pronunciation">')
        end = HTML.index('<section class="page" id="sound">', start)
        section = HTML[start:end]
        for control_id in (
            "pronSearchAdvanced", "pronScopeFilter", "pronOriginFilter",
            "pronPreviewProfile", "deleteSelectedPron", "pronunciationGlobalToggle",
            "pronAiSuggestions", "pronEntryModal"
        ):
            with self.subTest(control_id=control_id):
                self.assertIn(f'id="{control_id}"', section)

    def test_hard_coded_pronunciation_sample_terms_are_not_shipped(self):
        self.assertNotIn("const pronRoot=document.getElementById('pronunciation');", HTML)
        self.assertNotIn("let terms=[{word:'Rimuru'", HTML)
        self.assertNotIn("Testing '+terms[currentTerm].word", HTML)

    def test_adapter_searches_full_backend_records_and_renders_provenance_and_scopes(self):
        self.assertIn("call('pronunciation.list')", ADAPTER)
        self.assertIn("function renderPronunciationRows()", ADAPTER)
        self.assertIn("term.origin", ADAPTER)
        self.assertIn("term.scope_type", ADAPTER)
        self.assertIn("data-pron-enabled", ADAPTER)
        self.assertIn("data-pron-audio-play", ADAPTER)
        self.assertIn("apply_pronunciation_rules:false", ADAPTER)
        self.assertIn("_bypass_pronunciation_dictionary", (ROOT / "app/ui/premium_v2_host.py").read_text(encoding="utf-8"))
        self.assertIn("pronunciationSelectionKeys", ADAPTER)
        self.assertIn("data-pron-ai-scope", ADAPTER)
        self.assertIn("call('pronunciation.delete_many'", ADAPTER)
        self.assertIn("call('pronunciation.settings.save'", ADAPTER)
        self.assertIn("await monitorJob(started.job_id", ADAPTER)
        self.assertIn("project.get_active", ADAPTER)
        self.assertIn("pronAnalysisStatus", HTML)

    def test_production_and_pronunciation_studio_use_the_same_global_toggle(self):
        self.assertIn('id="pronunciationGlobalToggle"', HTML)
        self.assertIn('id="productionPronunciationToggle"', HTML)
        self.assertIn("pronunciation.settings.save", ADAPTER)
        self.assertIn("pronunciation.settings.get", ADAPTER)


if __name__ == "__main__":
    unittest.main()
